#!/usr/bin/env python3
"""
Merge docs, snippet semantics, and palette semantics into a single knowledge graph.

Inputs (defaults can be overridden via CLI):
- Docs JSON (td_universal_parsed.json) with operators/classes/concepts.
- Semantic JSON dirs for snippets and palette (formats unchanged).

Outputs:
- graph/td_knowledge_graph_merged.gpickle
- graph/td_knowledge_graph_merged.json
- index/operator_index.json (operator -> semantic/lossless paths, summaries)
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Any

import networkx as nx

KB_ROOT = Path(r"C:\TD_Projects\kb_pipeline")
DEFAULT_DOCS = Path(r"C:\TD_Projects\Learn\OfflineHelp\https.docs.derivative.ca\td_universal_parsed.json")
DEFAULT_SNIPPET_SEM = KB_ROOT / "data" / "snippets" / "semantic"
DEFAULT_PALETTE_SEM = KB_ROOT / "data" / "palette_semantic"


def load_docs(doc_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load operators from td_universal_parsed.json"""
    if not doc_path.exists():
        return {}
    with open(doc_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ops = {}
    for op in data.get("operators", []):
        name = op.get("name")
        if not name:
            continue
        ops[name.lower()] = {
            "name": name,
            "summary": op.get("summary", ""),
            "family": op.get("family"),
            "python_class": op.get("python_class"),
            "concepts": op.get("concepts", []),
            "file": op.get("file"),
        }
    return ops


def iter_semantic_files(sem_dir: Path):
    for path in sem_dir.glob("*_semantic.json"):
        yield path


def add_doc_nodes(G: nx.Graph, docs: Dict[str, Dict[str, Any]]):
    for key, meta in docs.items():
        node_id = f"op::{meta['name']}"
        G.add_node(
            node_id,
            type="operator",
            name=meta["name"],
            summary=meta.get("summary", ""),
            family=meta.get("family"),
            python_class=meta.get("python_class"),
            concepts=meta.get("concepts", []),
            source="docs",
        )


def add_semantic_examples(G: nx.Graph, sem_dir: Path, source_label: str, operator_index: Dict):
    for sem_path in iter_semantic_files(sem_dir):
        with open(sem_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        op_type = data.get("operator_type") or sem_path.stem.replace("_semantic", "")
        op_node = f"op::{op_type}"
        if op_node not in G:
            G.add_node(op_node, type="operator", name=op_type, source=source_label)

        examples = data.get("examples", [])
        lossless_path = None  # lossless JSON may exist, but isn't required for graph building

        operator_index.setdefault(op_type, {"semantic": [], "lossless": [], "source": []})
        operator_index[op_type]["semantic"].append(str(sem_path))
        if lossless_path:
            operator_index[op_type]["lossless"].append(lossless_path)
        if source_label not in operator_index[op_type]["source"]:
            operator_index[op_type]["source"].append(source_label)

        for ex in examples:
            ex_name = ex.get("example_name") or ex.get("name") or sem_path.stem
            ex_id = f"ex::{op_type}::{ex_name}"
            G.add_node(
                ex_id,
                type="example",
                operator_type=op_type,
                name=ex_name,
                topic=ex.get("topic"),
                source=source_label,
            )
            G.add_edge(ex_id, op_node, type="example_of")

            # Add operators within example as lightweight nodes; connect to example
            for op in ex.get("operators", []):
                op_name = op.get("name")
                op_type_full = op.get("type")
                op_node_id = f"node::{op_type}::{op_name}"
                G.add_node(
                    op_node_id,
                    type="example_operator",
                    name=op_name,
                    op_type=op_type_full,
                    params=op.get("parameters", {}),
                    source=source_label,
                )
                G.add_edge(ex_id, op_node_id, type="contains")

            # Add connections as edges between example_operator nodes
            for conn in ex.get("connections", []):
                from_name = conn.get("from")
                to_name = conn.get("to")
                if from_name and to_name:
                    from_id = f"node::{op_type}::{from_name}"
                    to_id = f"node::{op_type}::{to_name}"
                    if from_id in G and to_id in G:
                        G.add_edge(from_id, to_id, type="connection", input_index=conn.get("to_input"))


def save_graph(G: nx.Graph, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    gpickle_path = out_dir / "td_knowledge_graph_merged.gpickle"
    json_path = out_dir / "td_knowledge_graph_merged.json"
    try:
        nx.write_gpickle(G, gpickle_path)
    except AttributeError:
        import pickle
        with open(gpickle_path, "wb") as f:
            pickle.dump(G, f)
    # Lightweight JSON export
    data = {
        "nodes": [
            {"id": n, **{k: v for k, v in G.nodes[n].items()}}
            for n in G.nodes
        ],
        "edges": [
            {"source": u, "target": v, **{k: v2 for k, v2 in G.edges[u, v].items()}}
            for u, v in G.edges
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved graph: {gpickle_path}")
    print(f"Saved graph JSON: {json_path}")


def main():
    parser = argparse.ArgumentParser(description="Build merged TD knowledge graph.")
    parser.add_argument("--docs", type=Path, default=DEFAULT_DOCS, help="Path to td_universal_parsed.json")
    parser.add_argument("--snippets", type=Path, default=DEFAULT_SNIPPET_SEM, help="Directory of snippet semantic JSONs")
    parser.add_argument("--palette", type=Path, default=DEFAULT_PALETTE_SEM, help="Directory of palette semantic JSONs")
    parser.add_argument("--out", type=Path, default=KB_ROOT / "graph", help="Output directory for graph files")
    parser.add_argument("--index_out", type=Path, default=KB_ROOT / "index" / "operator_index.json", help="Output path for operator index")
    args = parser.parse_args()

    G = nx.Graph()

    docs = load_docs(args.docs)
    add_doc_nodes(G, docs)

    operator_index: Dict[str, Dict[str, Any]] = {}

    if args.snippets.exists():
        add_semantic_examples(G, args.snippets, source_label="snippets", operator_index=operator_index)
    if args.palette.exists():
        add_semantic_examples(G, args.palette, source_label="palette", operator_index=operator_index)

    save_graph(G, args.out)

    args.index_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.index_out, "w", encoding="utf-8") as f:
        json.dump(operator_index, f, indent=2)
    print(f"Saved operator index: {args.index_out}")


if __name__ == "__main__":
    main()
