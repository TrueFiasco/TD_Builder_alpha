#!/usr/bin/env python3
"""
Enhanced GraphRAG Query Engine
Uses the new enhanced knowledge graph with ExampleNetwork, OperatorInstance, etc.
"""

import json
import pickle
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from collections import defaultdict


def _kb_integrity():
    """File-relative import of server_core/kb_integrity.py (W2d trust boundary).

    This module is itself exec'd standalone via spec_from_file_location
    (unified_graph_query / unified_search / hybrid_search all do so), so
    package-relative imports are unavailable; resolve the sibling by path and
    memoize under a distinctive key.
    """
    import importlib.util
    mod = sys.modules.get("td_kb_integrity")
    if mod is None:
        p = Path(__file__).resolve().parent / "kb_integrity.py"
        spec = importlib.util.spec_from_file_location("td_kb_integrity", str(p))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["td_kb_integrity"] = mod
        spec.loader.exec_module(mod)
    return mod


# Family suffixes recognised by the op-type normalizer. Order matters — longer
# suffixes (COMP, CHOP) must be tried before shorter ones (POP, MAT). This list
# is shared by find_examples_by_operator_combination (B20+B21) and
# find_examples_by_operator (B24 family disambiguation).
_OP_FAMILIES: Tuple[str, ...] = ("COMP", "CHOP", "TOP", "SOP", "MAT", "DAT", "POP")

# Operator type-bases that are ubiquitous plumbing rather than meaningful structure.
# A NetworkPattern whose operators are ALL drawn from this set is treated as noise by
# get_network_patterns (Round-4 #7) — e.g. a bare "null + out" pattern that appears in
# almost every network and tells you nothing.
_UNIVERSAL_PATTERN_OPS: frozenset = frozenset({"null", "out", "in", "select"})


def _normalize_op_type_for_filter(name: str) -> Tuple[Optional[str], str]:
    """Normalise an operator type spec to (family_or_None, type_base_lower).

    Accepts every shape users actually type — bare names, colon-form,
    family-suffixed, space-separated wiki form:

      'constant'        -> (None,  'constant')   # match any family
      'TOP:constant'    -> ('TOP', 'constant')   # match TOP:constant only
      'constantTOP'     -> ('TOP', 'constant')   # suffixed form (B21)
      'noise CHOP'      -> ('CHOP', 'noise')     # space-separated wiki form

    family is the upper-case family token or None when the user gave a bare
    name. type_base is lower-cased to keep the substring match consistent
    with the legacy lax behavior.
    """
    s = (name or "").strip()
    if not s:
        return None, ""
    if ":" in s:
        fam, t = s.split(":", 1)
        fam = fam.strip().upper()
        # W5.1 — `ALL:<type>` is explicit cross-family. Same behavior as a bare
        # name (family=None) but the caller has signed off on the ambiguity, so
        # the bare-name rejection in find_examples_by_operator_combination skips it.
        if fam == "ALL":
            return None, t.strip().lower()
        return (fam or None), t.strip().lower()
    for fam in _OP_FAMILIES:
        # Space-separated wiki form, e.g. 'noise CHOP'. Also strip INTERNAL spaces so a
        # multi-word wiki name ('SOP to CHOP') matches the space-free node-name convention
        # ('soptoCHOP'); this fixes get_operator_info + find_operator_examples for EVERY
        # multi-word operator name, not just the named converters.
        if s.endswith(" " + fam):
            return fam, s[: -(len(fam) + 1)].strip().lower().replace(" ", "")
        # Concatenated suffix, e.g. 'noiseCHOP'
        if s.endswith(fam) and len(s) > len(fam):
            return fam, s[: -len(fam)].lower()
    return None, s.lower()


class EnhancedGraphQuery:
    """Query engine for enhanced knowledge graph"""

    def __init__(self, graph_path: str = "./td_knowledge_graph_enhanced.gpickle"):
        """Load enhanced knowledge graph"""

        print("[INIT] Loading Enhanced Knowledge Graph...")

        graph_file = Path(graph_path)
        if not graph_file.exists():
            raise FileNotFoundError(f"Enhanced graph not found: {graph_path}")

        # W2d trust boundary: verify the exact bytes against the KB receipt /
        # pinned release manifest BEFORE unpickling (kb_root = the gpickle's
        # directory: the graph sits at the KB root in every supported layout).
        # A refuse verdict — or ANY unexpected error in the check itself —
        # degrades to an EMPTY graph so graph-backed features go dark loudly
        # while the rest of the server (vector search, registry, builders)
        # keeps working. The whole verify+load is wrapped so the integrity
        # check can never take the server down, mirroring the bm25 site.
        # Missing-file behavior (raise above) is unchanged.
        self.integrity_failed = False
        self.integrity_reason = ""
        try:
            graph_bytes = graph_file.read_bytes()
            verdict = _kb_integrity().verify_pickle_bytes(graph_bytes, graph_file, graph_file.parent)
            if verdict.ok:
                self.graph_data = pickle.loads(graph_bytes)
            else:
                self.integrity_failed = True
                self.integrity_reason = verdict.reason
                print(f"[SECURITY] {verdict.reason}", file=sys.stderr)
                print("[SECURITY] Enhanced graph REFUSED (integrity); loading EMPTY graph - "
                      "example/pattern/graph tools will return no results until the KB is "
                      "re-fetched or receipted.", file=sys.stderr)
                self.graph_data = {"nodes": {}, "edges": []}
        except Exception as e:
            self.integrity_failed = True
            self.integrity_reason = f"integrity check error: {e}"
            print(f"[SECURITY] Enhanced graph integrity check errored ({e}); loading EMPTY "
                  "graph - graph tools disabled until the KB is re-fetched or receipted.",
                  file=sys.stderr)
            self.graph_data = {"nodes": {}, "edges": []}

        self.nodes = self.graph_data['nodes']
        self.edges = self.graph_data['edges']

        # Build edge indices for fast lookup
        self._build_edge_indices()

        print(f"  Loaded {len(self.nodes)} nodes, {len(self.edges)} edges")
        print("[OK] Enhanced GraphRAG ready!\n")

    def _build_edge_indices(self):
        """Build indices for fast edge lookup"""

        self.outgoing_edges = defaultdict(list)
        self.incoming_edges = defaultdict(list)
        self.edges_by_type = defaultdict(list)

        for edge in self.edges:
            self.outgoing_edges[edge['from']].append(edge)
            self.incoming_edges[edge['to']].append(edge)
            self.edges_by_type[edge['type']].append(edge)

    def find_examples_by_operator(
        self,
        operator_name: str,
        limit: int = 10,
        family: Optional[str] = None,
    ) -> Union[List[Dict], Dict]:
        """Find examples demonstrating an operator.

        Returns a flat list when the operator resolves to one family — either
        because `family` was supplied, the operator name parsed to a family
        (`'TOP:noise'` / `'noiseTOP'` / `'noise TOP'`), or the bare name only
        matches a single family.

        W5.2 — when a bare name like `'noise'` matches operators across
        multiple families, returns a per-family bucketed dict instead so the
        caller knows to disambiguate:

            {
                "_resolution": "multi-family",
                "_query": "noise",
                "_families": ["CHOP", "MAT", "SOP", "TOP"],
                "results_by_family": {
                    "CHOP": [...examples up to `limit`...],
                    "MAT":  [...],
                    "SOP":  [...],
                    "TOP":  [...],
                },
            }

        B24 (Wave 4) introduced the family-scoped single-family path. Wave 5
        adds the multi-family bucketed branch for bare names.
        """
        # Parse `family:type` / `typeFAMILY` form out of operator_name; explicit
        # `family` kwarg takes precedence when both are supplied.
        parsed_fam, parsed_type = _normalize_op_type_for_filter(operator_name)
        scope_family = (family or parsed_fam or "").strip().upper() or None
        match_needle = parsed_type or operator_name.lower()

        op_nodes = [
            n for n in self.nodes.values()
            if n.get('type') == 'Operator'
            and match_needle in n['name'].lower()
            and (scope_family is None or n.get('family', '').upper() == scope_family)
        ]

        # W5.2 — bare-name match spans multiple families: return bucketed.
        if scope_family is None:
            families_hit = {n.get('family', 'Unknown').upper() for n in op_nodes}
            if len(families_hit) > 1:
                buckets: Dict[str, List[Dict]] = {}
                for op_node in op_nodes:
                    fam = op_node.get('family', 'Unknown').upper()
                    bucket = buckets.setdefault(fam, [])
                    if len(bucket) >= limit:
                        continue
                    bucket.extend(self._collect_examples_for_op(op_node, limit - len(bucket)))
                return {
                    "_resolution": "multi-family",
                    "_query": operator_name,
                    "_families": sorted(families_hit),
                    "results_by_family": {
                        fam: buckets.get(fam, [])[:limit] for fam in sorted(buckets)
                    },
                }

        # Single-family path (scope_family is set, OR bare name matched one family).
        results: List[Dict] = []
        for op_node in op_nodes:
            results.extend(self._collect_examples_for_op(op_node, limit - len(results)))
            if len(results) >= limit:
                break
        return results[:limit]

    def _collect_examples_for_op(self, op_node: Dict, limit: int) -> List[Dict]:
        """Walk DEMONSTRATES edges from an operator node, return enriched examples.

        W5.2 helper, factored out of find_examples_by_operator so the
        multi-family bucketed path can per-bucket-budget without duplicating
        the walk logic.
        """
        out: List[Dict] = []
        if limit <= 0:
            return out
        for edge in self.outgoing_edges.get(op_node['id'], []):
            if edge.get('type') != 'DEMONSTRATES':
                continue
            ex = self.nodes.get(edge['to'])
            if ex and ex.get('is_useful'):
                out.append(self._enrich_example(ex))
                if len(out) >= limit:
                    break
        return out

    def find_examples_by_operator_combination(self, operator_types: List[str],
                                              require_connection: bool = True,
                                              limit: int = 5) -> Union[List[Dict], Dict]:
        """Find examples that use specific operator combinations.

        W5.1 — REJECTS bare names. Each entry in `operator_types` must encode a
        family scope, one of:
          - `'TOP:constant'`  colon-form (family explicit)
          - `'constantTOP'`   suffix-form (family explicit)
          - `'constant TOP'`  space-separated wiki form (family explicit)
          - `'ALL:constant'`  opt-in cross-family (caller acknowledges ambiguity)

        Bare names like `'constant'` previously matched across all families and
        could surface cross-family false-positives silently. The error response
        is self-documenting (carries `rejected` + `accepted_forms`) so callers
        learn the new contract on first failure.
        """

        # W5.1 — validate operator_types before walking the graph.
        errors: List[str] = []
        for raw in operator_types or []:
            if not isinstance(raw, str):
                errors.append(repr(raw))
                continue
            fam, _ = _normalize_op_type_for_filter(raw)
            # _normalize returns (None, ...) for both bare names AND `ALL:foo`.
            # The `ALL:` opt-in is allowed; bare names are not.
            if fam is None and not raw.strip().upper().startswith("ALL:"):
                errors.append(raw)
        if errors:
            return {
                "error": "explicit family required in operator_types (W5.1)",
                "rejected": errors,
                "accepted_forms": [
                    "TOP:constant   — match TOP:constant only",
                    "constantTOP    — same, suffixed form",
                    "constant TOP   — same, space-separated wiki form",
                    "ALL:constant   — explicitly match any family (opt-in)",
                ],
                "hint": (
                    "Bare names like 'constant' matched across every family with the same "
                    "type substring and could surface cross-family false-positives. "
                    "Re-issue the call with one of the accepted forms above."
                ),
            }

        results = []

        for node in self.nodes.values():
            if node['type'] != 'ExampleNetwork':
                continue

            if not node.get('is_useful'):
                continue

            # B20+B21 — match by (family, type) tuples so 'TOP:constant' doesn't
            # spuriously match 'MAT:constant' (B20), and 'feedbackTOP' DOES match
            # 'TOP:feedback' (B21). Bare names (no family) keep the lax substring
            # behavior on the type portion only — backwards-compatible.
            example_pairs = [
                _normalize_op_type_for_filter(op.get('type', ''))
                for op in node.get('operators', [])
            ]
            requested_pairs = [_normalize_op_type_for_filter(rt) for rt in operator_types]

            def _matches(req_fam: Optional[str], req_type: str,
                         ex_fam: Optional[str], ex_type: str) -> bool:
                if req_fam is not None and req_fam != ex_fam:
                    return False
                return bool(req_type) and (req_type in ex_type)

            if all(any(_matches(rf, rt, ef, et) for ef, et in example_pairs)
                   for rf, rt in requested_pairs):

                # If require_connection, check if they're actually connected
                if require_connection and len(operator_types) > 1:
                    if not self._operators_connected(node, operator_types):
                        continue

                results.append(self._enrich_example(node))

                if len(results) >= limit:
                    break

        return results

    def find_parameter_examples(self, operator_type: str, parameter_name: str,
                               limit: int = 10) -> List[Dict]:
        """Find examples showing how a parameter is used"""

        results = []

        # Find all parameter configs matching the criteria
        for node in self.nodes.values():
            if node['type'] != 'ParameterConfig':
                continue

            if parameter_name and parameter_name.lower() not in node['parameter_name'].lower():
                continue

            # Get the operator instance
            instance_id = node['operator_instance']
            instance_node = self.nodes.get(instance_id)

            if not instance_node:
                continue

            # Check if instance matches operator type
            if operator_type and operator_type.lower() not in instance_node['operator_type'].lower():
                continue

            # Get the example
            example_id = instance_node['in_example']
            example_node_id = f"ex:{example_id}"
            example_node = self.nodes.get(example_node_id)

            if example_node and example_node.get('is_useful'):
                result = {
                    'parameter_name': node['parameter_name'],
                    'parameter_value': node['value'],
                    'operator_instance': instance_node['name'],
                    'operator_type': instance_node['operator_type'],
                    'example': self._enrich_example(example_node)
                }
                results.append(result)

                if len(results) >= limit:
                    break

        return results

    def find_similar_patterns(self, example_id: str, limit: int = 5) -> List[Dict]:
        """Find examples similar to `example_id` (Round-4 #5).

        Resolves the example id whether the caller passes the bare id or the `ex:`-prefixed
        node key. Ranks similarity in two passes: (1) examples sharing an IMPLEMENTS_PATTERN
        tag (the sharper signal, but only ~12.6% of examples carry one), then (2) a
        shared-operator-overlap fallback over the rest so the ~87% of untagged examples
        still return useful neighbours instead of []."""
        # Resolve the node key (accept "ex:foo" or "foo").
        resolved_id = None
        candidates = [example_id] if example_id.startswith("ex:") else [f"ex:{example_id}", example_id]
        for cand in candidates:
            if cand in self.nodes:
                resolved_id = cand
                break
        if resolved_id is None:
            return []
        example_node = self.nodes[resolved_id]

        results: List[Dict] = []
        seen: Set[str] = {resolved_id}

        # Pass 1 — shared network pattern (IMPLEMENTS_PATTERN).
        for edge in self.outgoing_edges.get(resolved_id, []):
            if edge.get('type') != 'IMPLEMENTS_PATTERN':
                continue
            for other_edge in self.incoming_edges.get(edge['to'], []):
                if other_edge.get('type') != 'IMPLEMENTS_PATTERN':
                    continue
                oid = other_edge['from']
                if oid in seen:
                    continue
                other = self.nodes.get(oid)
                if other and other.get('is_useful'):
                    seen.add(oid)
                    results.append(self._enrich_example(other))
                    if len(results) >= limit:
                        return results

        # Pass 2 — shared-operator-overlap fallback (uses the dense CONTAINS_OPERATOR data).
        query_ops = self._example_op_types(example_node)
        if query_ops:
            scored: List[Tuple[int, str, Dict]] = []
            for nid, node in self.nodes.items():
                if nid in seen or node.get('type') != 'ExampleNetwork' or not node.get('is_useful'):
                    continue
                overlap = len(query_ops & self._example_op_types(node))
                if overlap > 0:
                    scored.append((overlap, nid, node))
            # Most overlap first; stable by id for determinism.
            scored.sort(key=lambda s: (-s[0], s[1]))
            for _, nid, node in scored:
                if len(results) >= limit:
                    break
                seen.add(nid)
                results.append(self._enrich_example(node))

        return results[:limit]

    def _example_op_types(self, example_node: Dict) -> Set[str]:
        """Set of normalized operator type-bases (e.g. 'noise', 'level') in an example."""
        out: Set[str] = set()
        for op in example_node.get('operators', []):
            _, t = _normalize_op_type_for_filter(op.get('type', ''))
            if t:
                out.add(t)
        return out

    def get_network_patterns(self, min_frequency: int = 5,
                             exclude_universal: bool = True) -> List[Dict]:
        """Get common network patterns (Round-4 #7).

        Two query-time cleanups on top of the raw NetworkPattern nodes:
          - **dedup** repeated pattern signatures (the graph can hold several nodes for the
            same signature) — keep the highest-frequency one, summing example counts;
          - **noise filter** (`exclude_universal`): drop patterns whose operators are ALL
            ubiquitous plumbing (null/in/out/select), which otherwise dominate at high
            `min_frequency`."""
        by_sig: Dict[Any, Dict] = {}

        for node in self.nodes.values():
            if node.get('type') != 'NetworkPattern':
                continue
            if node.get('frequency', 0) < min_frequency:
                continue

            op_types = node.get('operator_types', []) or []
            if exclude_universal and op_types:
                bases = [_normalize_op_type_for_filter(t)[1] for t in op_types]
                if all(b in _UNIVERSAL_PATTERN_OPS for b in bases):
                    continue

            sig = node.get('pattern_signature')
            key = sig if sig is not None else tuple(sorted(op_types))
            entry = {
                'pattern_signature': sig,
                'operator_types': op_types,
                'frequency': node.get('frequency', 0),
                'example_count': len(self.incoming_edges.get(node['id'], [])),
                'canonical_example_id': node.get('canonical_example'),
            }
            prev = by_sig.get(key)
            if prev is None:
                by_sig[key] = entry
            else:
                # Same signature seen again: keep the richer one, accumulate example counts.
                merged_count = prev['example_count'] + entry['example_count']
                keep = entry if entry['frequency'] > prev['frequency'] else prev
                keep['example_count'] = merged_count
                by_sig[key] = keep

        return sorted(by_sig.values(), key=lambda p: p['frequency'], reverse=True)

    def search_by_text(self, query: str, limit: int = 10) -> List[Dict]:
        """Search examples by text (simple keyword matching)"""

        query_lower = query.lower()
        results = []

        for node in self.nodes.values():
            if node['type'] != 'ExampleNetwork':
                continue

            if not node.get('is_useful'):
                continue

            # Search in composite description
            searchable_text = node.get('searchable_text', '')
            if query_lower in searchable_text:
                # Calculate relevance score
                score = searchable_text.count(query_lower)
                results.append((score, self._enrich_example(node)))

        # Sort by relevance
        results.sort(key=lambda x: x[0], reverse=True)

        return [r[1] for r in results[:limit]]

    def get_operator_info(self, operator_name: str) -> Optional[Dict]:
        """Get comprehensive info about an operator (Round-4 #6).

        hybrid_search passes operator DISPLAY names ("Feedback TOP"); the graph's Operator
        nodes are suffixed ("feedbackTOP"). The old plain-substring match failed on that
        (reported "not found in enhanced graph"), so normalise both sides to (family, type)
        first, then fall back to the legacy substring match."""
        req_fam, req_type = _normalize_op_type_for_filter(operator_name)

        op_node = None
        # Pass 1 — normalized (family, type) match.
        if req_type:
            for node in self.nodes.values():
                if node.get('type') != 'Operator':
                    continue
                nf, nt = _normalize_op_type_for_filter(node.get('name', ''))
                if nt == req_type and (req_fam is None or req_fam == nf):
                    op_node = node
                    break
        # Pass 2 — legacy substring fallback (backwards compatible).
        if not op_node:
            for node in self.nodes.values():
                if node.get('type') == 'Operator' and operator_name.lower() in node.get('name', '').lower():
                    op_node = node
                    break

        if not op_node:
            return None

        # Count examples as what find_examples_by_operator will actually serve.
        # Counting raw DEMONSTRATES edges used a different identity key and lied
        # in both directions (Feedback TOP count 0 vs 3 served; GLSL POP count 4
        # vs 0 served). Scope to the resolved node's family so a bare name can't
        # come back as the multi-family bucketed dict.
        served = self.find_examples_by_operator(
            operator_name, limit=50, family=op_node.get('family'))
        if isinstance(served, dict):
            served = [ex for exs in served.get('results_by_family', {}).values() for ex in exs]
        example_count = len(served)

        # Get sample examples
        examples = served[:3]

        # Collect common parameters
        common_params = defaultdict(set)
        for example in examples:
            for op in example.get('operators', []):
                for param_name, param_value in op.get('parameters', {}).items():
                    common_params[param_name].add(str(param_value))

        return {
            'operator_name': op_node['name'],
            'family': op_node['family'],
            'example_count': example_count,
            'has_text_knowledge': op_node.get('has_text_knowledge', False),
            'has_network_knowledge': op_node.get('has_network_knowledge', False),
            'common_parameters': {k: list(v)[:5] for k, v in common_params.items()},
            'sample_examples': examples
        }

    def get_operators_by_family(self, family: str) -> List[Dict]:
        """Return all distinct Operator nodes in a family. Each dict is the raw
        Operator node (carries at least 'name' and 'family'). Backs
        UnifiedGraphQuery.get_operators_by_family / query_graph(family=...)."""
        fam = (family or "").strip().upper()
        if not fam:
            return []
        seen: Set[str] = set()
        out: List[Dict] = []
        for node in self.nodes.values():
            if node.get('type') != 'Operator':
                continue
            if (node.get('family') or '').upper() != fam:
                continue
            name = node.get('name', '')
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(node)
        return out

    def _operators_connected(self, example_node: Dict, operator_types: List[str]) -> bool:
        """Check if specified operators are connected in the example"""

        connections = example_node.get('connections', [])

        if not connections:
            return False

        # Get operator instances of requested types
        instances_by_type = defaultdict(list)
        for op in example_node.get('operators', []):
            for op_type in operator_types:
                if op_type.lower() in op['type'].lower():
                    instances_by_type[op_type].append(op['name'])

        # Check if any instances are connected
        for conn in connections:
            from_name = conn['from']
            to_name = conn['to']

            # Check if this connection links requested operator types
            from_types = [t for t, names in instances_by_type.items() if from_name in names]
            to_types = [t for t, names in instances_by_type.items() if to_name in names]

            if from_types and to_types and from_types[0] != to_types[0]:
                return True

        return False

    def _enrich_example(self, example_node: Dict) -> Dict:
        """Add helpful context to an example"""

        # Count functional operators
        functional_ops = [op for op in example_node.get('operators', [])
                         if 'readMe' not in op['name']]

        # Get key parameters
        key_params = []
        for op in functional_ops:
            for param_name, param_value in op.get('parameters', {}).items():
                if self._is_key_parameter(param_name):
                    key_params.append({
                        'operator': op['name'],
                        'parameter': param_name,
                        'value': param_value
                    })

        return {
            'example_id': example_node['example_id'],
            'operator_type': example_node['operator_type'],
            'label': example_node.get('label', ''),
            'topic': example_node.get('topic', ''),
            'text_explanation': example_node.get('text_explanation', ''),
            'operator_count': len(functional_ops),
            'connection_count': len(example_node.get('connections', [])),
            'operators': example_node.get('operators', []),
            'connections': example_node.get('connections', []),
            'key_parameters': key_params,
            'network_pattern': example_node.get('network_pattern', {}),
            'composite_description': example_node.get('composite_description', '')
        }

    def _is_key_parameter(self, param_name: str) -> bool:
        """Check if parameter is functionally important"""

        key_patterns = {
            'function', 'method', 'type', 'mode', 'operation',
            'file', 'path', 'chop', 'dat', 'top', 'sop',
            'rate', 'speed', 'freq', 'amplitude'
        }

        return any(pattern in param_name.lower() for pattern in key_patterns)

    def get_stats(self) -> Dict:
        """Get graph statistics"""

        stats = {
            'total_nodes': len(self.nodes),
            'total_edges': len(self.edges)
        }

        # Count by node type
        for node in self.nodes.values():
            node_type = node.get('type', 'unknown')
            stats[f'nodes_{node_type}'] = stats.get(f'nodes_{node_type}', 0) + 1

        # Count by edge type
        for edge in self.edges:
            edge_type = edge.get('type', 'unknown')
            stats[f'edges_{edge_type}'] = stats.get(f'edges_{edge_type}', 0) + 1

        return stats
