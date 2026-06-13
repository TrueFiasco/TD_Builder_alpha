#!/usr/bin/env python3
"""
Unified Graph Query
Queries BOTH old graph (wiki docs) AND enhanced graph (examples)
Ensures we find all available data
"""

import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict


class UnifiedGraphQuery:
    """
    Queries both knowledge sources:
    1. Old graph (td_knowledge_graph.gpickle) - Wiki documentation with ALL operators
    2. Enhanced graph (td_knowledge_graph_enhanced.gpickle) - Real examples with network topology
    """

    def __init__(self,
                 graphrag_json_path: str = "./td_graphrag.json",
                 enhanced_graph_path: str = "./td_knowledge_graph_enhanced.gpickle",
                 enriched_wiki_path: str = "./kb_pipeline/data/wiki_docs/td_universal_parsed_enriched.json"):

        print("[INIT] Loading Unified Graph Query...")

        # Load wiki documentation directly from JSON (no networkx needed!)
        self.wiki_data = {}
        self.wiki_loaded = False

        # Also load enriched wiki (with ground truth params)
        self.enriched_wiki = {}
        self.enriched_loaded = False

        # B04 indices — populated inside the wiki-load try block if it succeeds.
        # Pre-init here so get_related_operators returns [] cleanly when wiki load fails.
        self.op_id_to_name: Dict[str, str] = {}
        self.op_id_to_family: Dict[str, str] = {}
        self.op_name_to_id: Dict[str, str] = {}
        self.related_to_index: Dict[str, List[str]] = defaultdict(list)
        self.param_to_ops: Dict[str, List[str]] = defaultdict(list)
        self.universal_params: Set[str] = set()

        try:
            print("  Loading wiki documentation (td_graphrag.json)...")
            import json
            with open(graphrag_json_path, 'r', encoding='utf-8') as f:
                graphrag = json.load(f)

            # Index operators and their parameters
            nodes = graphrag['graph']['nodes']
            edges = graphrag['graph']['edges']

            # Build operator index
            operator_nodes = {n['id']: n for n in nodes if n.get('type') == 'operator'}
            parameter_nodes = {n['id']: n for n in nodes if n.get('type') == 'parameter'}

            # Build parameter relationships
            for op_id, op_node in operator_nodes.items():
                op_props = op_node.get('properties', {})
                params = {}

                # Find parameters connected to this operator
                param_edges = [e for e in edges if e['from'] == op_id and e['type'] == 'has_parameter']

                for edge in param_edges:
                    param_id = edge['to']
                    if param_id in parameter_nodes:
                        param_props = parameter_nodes[param_id].get('properties', {})
                        param_code = param_props.get('code', param_id)
                        params[param_code] = {
                            'code': param_code,
                            'display_name': param_props.get('display_name', param_code),
                            'section': param_props.get('section', 'Unknown'),
                            'description': param_props.get('description', '')
                        }

                op_name = op_props.get('name', op_id)
                self.wiki_data[op_name.lower()] = {
                    'operator_name': op_name,
                    'family': op_props.get('family', 'Unknown'),
                    'description': op_props.get('description', ''),
                    'parameters': params
                }

            # B04 — build operator/param indices for get_related_operators.
            # Source A: related_to edges (wiki cross-references).
            # Source B: has_parameter edges (already iterated above per-operator —
            # we re-scan once here to build the cross-op param→ops index).
            for op_id, op_node in operator_nodes.items():
                op_props = op_node.get('properties', {})
                self.op_id_to_name[op_id] = op_props.get('name', op_id)
                self.op_id_to_family[op_id] = op_props.get('family', 'Unknown')
            self.op_name_to_id = {
                name.lower(): op_id for op_id, name in self.op_id_to_name.items()
            }

            for edge in edges:
                etype = edge.get('type')
                if etype == 'related_to' and edge.get('from') != edge.get('to'):
                    self.related_to_index[edge['from']].append(edge['to'])
                elif etype == 'has_parameter':
                    param_id = edge.get('to')
                    if param_id in parameter_nodes:
                        code = parameter_nodes[param_id].get('properties', {}).get('code')
                        if code:
                            self.param_to_ops[code].append(edge['from'])

            # Universal-param filter: any param code on > 50% of ops is "noise"
            # (think `bypass`, `active`, `pulse` — shared everywhere, not meaningful for similarity).
            threshold = max(1, len(operator_nodes) // 2)
            self.universal_params = {
                code for code, op_ids in self.param_to_ops.items()
                if len(set(op_ids)) > threshold
            }

            self.wiki_loaded = True
            print(f"    [OK] Wiki documentation loaded: {len(self.wiki_data)} operators")
            print(f"    [OK] Cross-op indices: {len(self.related_to_index)} ops with related_to, "
                  f"{len(self.param_to_ops)} param codes, "
                  f"{len(self.universal_params)} universal-noise codes")
        except Exception as e:
            print(f"    [WARNING] Could not load wiki documentation: {e}")
            print("    Will use enhanced graph only")

        # Load enriched wiki docs (with ground truth params)
        try:
            import json
            from pathlib import Path
            enriched_path = Path(enriched_wiki_path)
            if not enriched_path.is_absolute():
                enriched_path = Path(__file__).parent / enriched_wiki_path

            if enriched_path.exists():
                print(f"  Loading enriched wiki (ground truth params)...")
                with open(enriched_path, 'r', encoding='utf-8') as f:
                    enriched_data = json.load(f)

                # Index by operator name
                for op in enriched_data.get('operators', []):
                    name = op.get('name', '')
                    if name:
                        params = {}
                        for p in op.get('parameters', []):
                            code = p.get('code', '')
                            if code:
                                params[code] = p
                        self.enriched_wiki[name.lower()] = {
                            'operator_name': name,
                            'family': op.get('family', ''),
                            'summary': op.get('summary', ''),
                            'parameters': params
                        }

                self.enriched_loaded = True
                enrichment_meta = enriched_data.get('metadata', {}).get('enrichment', {})
                print(f"    [OK] Enriched wiki loaded: {len(self.enriched_wiki)} operators, +{enrichment_meta.get('params_added', 0)} params from ground truth")
        except Exception as e:
            print(f"    [INFO] Enriched wiki not loaded: {e}")

        # Load enhanced graph (examples with network topology)
        print("  Loading enhanced graph (real examples)...")
        spec = importlib.util.spec_from_file_location("enhanced_graph_query", str(Path(__file__).parent / "enhanced_graph_query.py"))
        enh_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(enh_module)
        self.enhanced_graph_query = enh_module.EnhancedGraphQuery(enhanced_graph_path)
        print(f"    [OK] Enhanced graph loaded: {len(self.enhanced_graph_query.nodes)} nodes")

        print("[OK] Unified Graph Query ready!\n")

    @property
    def nodes(self):
        """Return nodes from enhanced graph (for compatibility)"""
        return self.enhanced_graph_query.nodes

    @property
    def edges(self):
        """Return edges from enhanced graph (for compatibility)"""
        return self.enhanced_graph_query.edges

    def get_operator_info(self, operator_name: str) -> Optional[Dict]:
        """
        Get comprehensive operator info from ALL sources:
        1. Wiki documentation (graphrag)
        2. Enriched wiki (with ground truth params)
        3. Enhanced graph (real examples)
        """
        result = {
            'operator_name': operator_name,
            'wiki_data': None,
            'enriched_data': None,
            'example_data': None,
            'has_wiki_docs': False,
            'has_enriched': False,
            'has_examples': False
        }

        # Get from wiki documentation (comprehensive parameter list)
        # Try multiple name variations
        if self.wiki_loaded:
            try:
                # Try exact match first
                wiki_info = self.wiki_data.get(operator_name.lower())

                # Try with space + family suffix (e.g., "speed chop")
                if not wiki_info:
                    # Common family suffixes
                    for suffix in [' CHOP', ' TOP', ' SOP', ' MAT', ' DAT', ' COMP', ' POP']:
                        variant = (operator_name + suffix).lower()
                        wiki_info = self.wiki_data.get(variant)
                        if wiki_info:
                            break

                # Try removing CHOP/TOP/etc suffix (e.g., "speedchop" -> "speed chop")
                if not wiki_info:
                    for suffix in ['chop', 'top', 'sop', 'mat', 'dat', 'comp', 'pop']:
                        if operator_name.lower().endswith(suffix):
                            base = operator_name[:-len(suffix)]
                            variant = (base + ' ' + suffix.upper()).lower()
                            wiki_info = self.wiki_data.get(variant)
                            if wiki_info:
                                break

                if wiki_info:
                    result['wiki_data'] = wiki_info
                    result['has_wiki_docs'] = True
            except Exception as e:
                print(f"Warning: Could not query wiki data: {e}")

        # Get from enriched wiki (has ground truth params)
        if self.enriched_loaded:
            try:
                # Try same name variations as wiki
                enriched_info = self.enriched_wiki.get(operator_name.lower())

                if not enriched_info:
                    for suffix in [' CHOP', ' TOP', ' SOP', ' MAT', ' DAT', ' COMP', ' POP']:
                        variant = (operator_name + suffix).lower()
                        enriched_info = self.enriched_wiki.get(variant)
                        if enriched_info:
                            break

                if not enriched_info:
                    for suffix in ['chop', 'top', 'sop', 'mat', 'dat', 'comp', 'pop']:
                        if operator_name.lower().endswith(suffix):
                            base = operator_name[:-len(suffix)]
                            variant = (base + ' ' + suffix.upper()).lower()
                            enriched_info = self.enriched_wiki.get(variant)
                            if enriched_info:
                                break

                if enriched_info:
                    result['enriched_data'] = enriched_info
                    result['has_enriched'] = True
            except Exception as e:
                print(f"Warning: Could not query enriched wiki: {e}")

        # Get from enhanced graph (real examples)
        try:
            example_info = self.enhanced_graph_query.get_operator_info(operator_name)
            if example_info:
                result['example_data'] = example_info
                result['has_examples'] = True
        except Exception as e:
            print(f"Warning: Could not query enhanced graph: {e}")

        # Merge the results
        if result['has_wiki_docs'] or result['has_enriched'] or result['has_examples']:
            merged = self._merge_operator_info(result)
            return merged

        return None

    def _merge_operator_info(self, result: Dict) -> Dict:
        """Merge wiki data + enriched wiki + example data into unified response"""
        merged = {}

        # Use example data as base (has the newer structure)
        if result['example_data']:
            merged = result['example_data'].copy()

        # Add wiki data
        if result['wiki_data']:
            wiki = result['wiki_data']

            # Merge parameters (wiki has comprehensive parameter list)
            if 'parameters' in wiki:
                # Old graph has detailed parameters
                merged['wiki_parameters'] = wiki['parameters']
                merged['wiki_parameter_count'] = len(wiki['parameters'])

            # Add other wiki metadata
            if 'description' in wiki:
                merged['wiki_description'] = wiki['description']

            if 'python_api' in wiki:
                merged['wiki_python_api'] = wiki['python_api']

            if 'related_operators' in wiki:
                merged['wiki_related_operators'] = wiki['related_operators']

        # Add enriched wiki data (ground truth params)
        if result.get('enriched_data'):
            enriched = result['enriched_data']

            if 'parameters' in enriched:
                # Merge with existing wiki params, enriched takes precedence
                existing_params = merged.get('wiki_parameters', {})
                enriched_params = enriched['parameters']

                # Combine: start with wiki, add/update from enriched
                all_params = {**existing_params, **enriched_params}
                merged['wiki_parameters'] = all_params
                merged['wiki_parameter_count'] = len(all_params)

                # Count how many came from ground truth
                gt_params = [p for p in enriched_params.values() if p.get('source') == 'ground_truth']
                merged['ground_truth_param_count'] = len(gt_params)

            # td_graphrag.json operator nodes carry no `description` property,
            # so wiki['description'] is always ''. Fall back to enriched summary.
            # mcp_server.py compact mode (line 1400) reads `summary`, so surface
            # the text under both keys.
            if enriched.get('summary'):
                if not merged.get('wiki_description'):
                    merged['wiki_description'] = enriched['summary']
                if not merged.get('summary'):
                    merged['summary'] = enriched['summary']

        # Add data source flags
        merged['has_wiki_docs'] = result['has_wiki_docs']
        merged['has_enriched'] = result.get('has_enriched', False)
        merged['has_examples'] = result['has_examples']

        # BUG-019 FIX: Ensure top-level name and family are always set
        merged['name'] = result.get('operator_name', merged.get('operator_name', ''))
        merged['family'] = (result.get('wiki_data') or {}).get('family',
                           (result.get('example_data') or {}).get('family', ''))

        return merged

    def get_operator_parameters(self, operator_name: str) -> Optional[Dict[str, Any]]:
        """Return the parameter dict for an operator (extractor over get_operator_info).

        Output shape: {param_code: {code, display_name, type, section, description,
        default, menuNames, menuLabels, range, source, ...}} — same shape as
        get_operator_info(...)['wiki_parameters']. Returns {} when the operator is
        known but has no parameter records; None when the operator is unknown.
        """
        info = self.get_operator_info(operator_name)
        if info is None:
            return None
        return info.get('wiki_parameters') or {}

    def _resolve_op_id(self, operator_name: str) -> Optional[str]:
        """Map an operator name to its td_graphrag op-id, trying common name variants.

        Mirrors the name-resolution ladder in get_operator_info (exact match,
        then with family suffix, then stripping a concatenated family suffix).
        """
        needle = operator_name.lower()
        op_id = self.op_name_to_id.get(needle)
        if op_id:
            return op_id
        for suffix in [' CHOP', ' TOP', ' SOP', ' MAT', ' DAT', ' COMP', ' POP']:
            op_id = self.op_name_to_id.get((operator_name + suffix).lower())
            if op_id:
                return op_id
        for suffix in ['chop', 'top', 'sop', 'mat', 'dat', 'comp', 'pop']:
            if operator_name.lower().endswith(suffix):
                base = operator_name[:-len(suffix)]
                op_id = self.op_name_to_id.get((base + ' ' + suffix.upper()).lower())
                if op_id:
                    return op_id
        return None

    def get_related_operators(self, operator_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return operators related to operator_name via three blended signals.

        Sources combined:
          - 'mentioned_together'    — `related_to` edges in td_graphrag.json (wiki cross-refs)
          - 'shared_parameters'     — operators that share non-universal parameter codes
          - 'co_occurs_in_examples' — operators that appear in the same example networks

        Output per entry: {name, family, sources: [...], scores: {...}}.
        Ranking: descending by len(sources), then by max(scores.values()).
        Returns [] for unknown operators (rather than None).
        """
        if not self.wiki_loaded:
            return []

        target_id = self._resolve_op_id(operator_name)
        if target_id is None:
            return []

        candidates: Dict[str, Dict[str, Any]] = {}

        # Source A — wiki cross-references
        for rid in self.related_to_index.get(target_id, []):
            if rid == target_id:
                continue
            entry = candidates.setdefault(rid, {"sources": set(), "scores": {}})
            entry["sources"].add("mentioned_together")
            entry["scores"]["mentioned_together"] = entry["scores"].get("mentioned_together", 0) + 1

        # Source B — shared parameters (excluding universal-noise params)
        target_params = {
            code for code, op_ids in self.param_to_ops.items()
            if target_id in op_ids and code not in self.universal_params
        }
        overlap_counts: Dict[str, int] = defaultdict(int)
        for code in target_params:
            for op_id in self.param_to_ops.get(code, []):
                if op_id != target_id:
                    overlap_counts[op_id] += 1
        for op_id, count in overlap_counts.items():
            if count >= 2:  # need ≥2 shared non-universal params to count
                entry = candidates.setdefault(op_id, {"sources": set(), "scores": {}})
                entry["sources"].add("shared_parameters")
                entry["scores"]["shared_parameters"] = count

        # Source C — example co-occurrence (best-effort; A and B already work)
        try:
            target_name = self.op_id_to_name[target_id]
            examples = self.enhanced_graph_query.find_examples_by_operator(target_name, limit=50)
            co_occur_counts: Dict[str, int] = defaultdict(int)
            for ex in examples:
                for op in ex.get('operators', []):
                    op_type = op.get('type', '')
                    co_op_name = op_type.split(':')[-1] if ':' in op_type else op_type
                    co_op_id = self._resolve_op_id(co_op_name)
                    if co_op_id and co_op_id != target_id:
                        co_occur_counts[co_op_id] += 1
            # Filter: drop operators that co-occur with > 50% of queried examples (utility ops).
            co_threshold = max(2, len(examples) // 2)
            for op_id, count in co_occur_counts.items():
                if count >= 2 and count < co_threshold:
                    entry = candidates.setdefault(op_id, {"sources": set(), "scores": {}})
                    entry["sources"].add("co_occurs_in_examples")
                    entry["scores"]["co_occurs_in_examples"] = count
        except Exception:
            pass

        ranked = sorted(
            candidates.items(),
            key=lambda kv: (len(kv[1]["sources"]), max(kv[1]["scores"].values(), default=0)),
            reverse=True,
        )

        return [
            {
                "name":    self.op_id_to_name.get(op_id, op_id),
                "family":  self.op_id_to_family.get(op_id, "Unknown"),
                "sources": sorted(entry["sources"]),
                "scores":  entry["scores"],
            }
            for op_id, entry in ranked[:limit]
        ]

    def find_examples_by_operator(
        self,
        operator_name: str,
        limit: int = 10,
        family: Optional[str] = None,
    ) -> List[Dict]:
        """Find real examples (from enhanced graph only).

        B24 — optional `family` disambiguates bare names. Forwarded to
        EnhancedGraphQuery.find_examples_by_operator unchanged.
        """
        return self.enhanced_graph_query.find_examples_by_operator(
            operator_name, limit, family=family,
        )

    def find_examples_by_operator_combination(self, operators: List[str],
                                              require_connection: bool = True,
                                              limit: int = 10) -> List[Dict]:
        """Find examples with operator combinations (from enhanced graph only)"""
        return self.enhanced_graph_query.find_examples_by_operator_combination(
            operators, require_connection, limit
        )

    def find_parameter_usage(self, operator_type: str, parameter_name: str,
                            limit: int = 10) -> List[Dict]:
        """Find parameter usage examples (from enhanced graph only)"""
        return self.enhanced_graph_query.find_parameter_examples(operator_type, parameter_name, limit)

    def get_network_patterns(self, min_frequency: int = 2) -> List[Dict]:
        """Get common network patterns (from enhanced graph only)"""
        return self.enhanced_graph_query.get_network_patterns(min_frequency)

    def find_similar_networks(self, example_id: str, limit: int = 5) -> List[Dict]:
        """Find similar network structures via shared NetworkPattern membership.

        Delegates to EnhancedGraphQuery.find_similar_patterns — the previous call
        to find_similar_networks raised AttributeError because that name does not
        exist on EnhancedGraphQuery.
        """
        return self.enhanced_graph_query.find_similar_patterns(example_id, limit)

    def search_by_text(self, query: str, limit: int = 10) -> List[Dict]:
        """Search by text content (from enhanced graph only)"""
        return self.enhanced_graph_query.search_by_text(query, limit)

    def get_operators_by_family(self, family: str) -> List[Dict]:
        """
        Get all operators in a family from BOTH sources
        Returns more comprehensive list than enhanced graph alone
        """
        operators = set()
        results = []

        # Get from wiki documentation (comprehensive list)
        if self.wiki_loaded:
            try:
                for op_name_lower, op_data in self.wiki_data.items():
                    if op_data.get('family', '').upper() == family.upper():
                        op_name = op_data['operator_name']
                        operators.add(op_name)
                        results.append({
                            'name': op_name,
                            'source': 'wiki',
                            'data': op_data
                        })
            except Exception as e:
                print(f"Warning: Could not query wiki data by family: {e}")

        # Get from enhanced graph (real examples)
        try:
            enh_ops = self.enhanced_graph_query.get_operators_by_family(family)
            if enh_ops:
                for op in enh_ops:
                    op_name = op.get('name', op.get('operator_name'))
                    if op_name and op_name not in operators:
                        operators.add(op_name)
                        results.append({
                            'name': op_name,
                            'source': 'examples',
                            'data': op
                        })
        except Exception as e:
            print(f"Warning: Could not query enhanced graph by family: {e}")

        return results


def main():
    """Test unified query"""
    import sys

    unified = UnifiedGraphQuery()

    if len(sys.argv) < 2:
        print("\nTest queries:")
        print('  python unified_graph_query.py "speed"')
        print('  python unified_graph_query.py "analyze"')
        return

    operator = sys.argv[1]

    print(f"\n{'='*70}")
    print(f"QUERYING: {operator}")
    print(f"{'='*70}\n")

    # Get operator info from both sources
    info = unified.get_operator_info(operator)

    if not info:
        print(f"[ERROR] Operator '{operator}' not found in either source")
        return

    print(f"[OK] Operator: {info['operator_name']}")
    print(f"  Has wiki docs: {info['has_wiki_docs']}")
    print(f"  Has examples: {info['has_examples']}")
    print()

    # Show wiki parameters
    if 'wiki_parameters' in info:
        print(f"Wiki Parameters ({info['wiki_parameter_count']}):")
        for param_name, param_info in list(info['wiki_parameters'].items())[:10]:
            print(f"  • {param_name}")
        if info['wiki_parameter_count'] > 10:
            print(f"  ... and {info['wiki_parameter_count'] - 10} more")
        print()

    # Show example parameters
    if 'common_parameters' in info:
        print(f"Example Parameters ({len(info['common_parameters'])}):")
        for param_name, values in list(info['common_parameters'].items())[:5]:
            print(f"  • {param_name}: {values[:3]}")
        print()

    # Show example count
    if 'example_count' in info:
        print(f"Real Examples: {info['example_count']}")

    print()


if __name__ == '__main__':
    main()
