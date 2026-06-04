"""#2 Retrieval recall / coverage.

Cases auto-generated from operator_types.json: for each sampled operator a
natural-language query whose correct answer is that operator. Drives the real
product path (hybrid_search / get_operator_info tools), not internals.

Metrics: recall@k (did the expected operator appear in top-k), MRR, KB
coverage% (get_operator_info returns real params), and find_similar_networks
coverage% (the documented ~0% W5.3 floor — every pattern added moves it).
Deterministic auto-scoring; the worst-case backlog = missed queries.
"""
from __future__ import annotations

import re

from measure import datasets
from measure.harness import CaseScore, emit

_WS = re.compile(r"\s+")
_K = 10


def _norm(name: str, family: str) -> str:
    n = name.replace("_", " ").strip()
    fu, fl = family.upper(), family.lower()
    if n.upper().endswith(f" {fu}"):
        n = n[: -(len(fu) + 1)].strip()
    elif n.lower().endswith(fl):
        n = n[: -len(fl)]
    return _WS.sub("", n).lower()


def _retrieved_keys(data) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    if not isinstance(data, dict):
        return keys
    for hit in data.get("semantic_results", []) or []:
        if not isinstance(hit, dict):
            continue
        meta = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        fam = (meta.get("family") or "").upper()
        nm = (meta.get("operator_name") or meta.get("name")
              or meta.get("operator") or meta.get("operator_type")
              or hit.get("operator_name") or hit.get("name"))
        if fam and nm:
            keys.append((fam, _norm(str(nm), fam)))
    return keys


def _similar_net_coverage(probe, ops) -> float:
    """Fraction of a few probes where find_similar_networks returns non-empty."""
    probes, nonempty = 0, 0
    for o in ops[:8]:
        ex = probe.call("find_operator_examples",
                        {"operator_name": o["name"].replace("_", " ")})
        ex_id = None
        d = ex.json()
        if isinstance(d, dict):
            lst = d.get("examples") or d.get("results") or []
            if lst and isinstance(lst[0], dict):
                ex_id = lst[0].get("id") or lst[0].get("example_id")
        elif isinstance(d, list) and d and isinstance(d[0], dict):
            ex_id = d[0].get("id") or d[0].get("example_id")
        if not ex_id:
            continue
        probes += 1
        sim = probe.call("find_similar_networks", {"example_id": ex_id})
        sd = sim.json()
        n = len(sd) if isinstance(sd, list) else (
            len(sd.get("results", sd.get("similar", []))) if isinstance(sd, dict) else 0)
        if n > 0:
            nonempty += 1
    return round(nonempty / probes, 4) if probes else 0.0


def run_retrieval(probe, promote: bool = False) -> dict:
    ops = datasets.sample_operators(datasets.RETRIEVAL_PER_FAMILY)
    scores: list[CaseScore] = []
    for o in ops:
        fam, name = o["family"], o["name"]
        pretty = name.replace("_", " ")
        expected = (fam.upper(), _norm(name, fam))
        case = f"{fam}:{name}"

        r = probe.call("hybrid_search",
                       {"query": f"how do I use the {pretty}", "n_results": _K})
        retrieved = _retrieved_keys(r.json())
        rank = next((i + 1 for i, k in enumerate(retrieved) if k == expected), 0)
        recall = 1.0 if rank else 0.0
        mrr = round(1.0 / rank, 4) if rank else 0.0

        info = probe.call("get_operator_info",
                          {"operator_name": pretty, "compact": True})
        cov = 1.0 if (info.ok and isinstance(info.json(), dict)
                      and "not found" not in info.text.lower()) else 0.0

        scores.append(CaseScore(
            case, recall, fam.upper(),
            {"recall_at_k": recall, "mrr": mrr, "kb_coverage": cov},
            f"rank={rank or 'miss'} cov={int(cov)}",
        ))

    sim_cov = _similar_net_coverage(probe, ops)
    return emit("retrieval_recall", scores, promote=promote,
                extra={"similar_net_coverage": sim_cov})


def test_retrieval_recall(probe, promote):
    report = run_retrieval(probe, promote)
    assert report["n"] > 0, "no retrieval cases ran"
