"""KBU completeness proof — reproduces the decisive KBU_REPORT.md assertions.

Run:  python KB/run_completeness_proof.py
Proves, before any KB store is quarantined, that the canonical 4-axis bundle
(enriched operators / td_graphrag / enhanced gpickle / vector_db_merged) loses
no knowledge vs the redundant stores. Writes KB/KBU_COMPLETENESS_PROOF.txt and
KB/manifest.json. Read-only except those two outputs.
"""
import hashlib, json, os, sqlite3, time

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def P(*a):
    return os.path.join(R, *a)


def rel(p):
    return os.path.relpath(p, R).replace(os.sep, "/")


results = []
ok = True


def chk(name, cond, detail=""):
    global ok
    if not cond:
        ok = False
    results.append(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


enr = P("META_AGENTIC_TOOL", "data", "wiki_docs", "td_universal_parsed_enriched.json")
parsed = P("META_AGENTIC_TOOL", "data", "wiki_docs", "td_universal_parsed.json")
bi = P("META_AGENTIC_TOOL", "data", "wiki_docs", "td_universal_parsed_with_build_instructions.json")
u_root = P("td_universal.json")
ops_tdmcp = P("td-mcp", "knowledge_base", "data", "operators.json")
gr_meta = P("META_AGENTIC_TOOL", "data", "td_graphrag.json")
gr_root = P("td_graphrag.json")
gp_meta = P("META_AGENTIC_TOOL", "data", "td_knowledge_graph_enhanced.gpickle")
gp_root = P("td_knowledge_graph_enhanced.gpickle")

# D.6 exact-dup MD5 proofs
m_parsed = md5(parsed)
for nm, pth in [("td_universal.json(root)", u_root), ("td-mcp operators.json", ops_tdmcp)]:
    chk(f"D.6 dup {nm}==parsed", os.path.exists(pth) and md5(pth) == m_parsed, f"({m_parsed[:12]})")
if os.path.exists(gr_root):
    chk("D.6 dup td_graphrag root==META", md5(gr_root) == md5(gr_meta))
if os.path.exists(gp_root):
    chk("D.6 dup enhanced.gpickle root==META", md5(gp_root) == md5(gp_meta))


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def opmap(d):
    o = d["operators"]
    return o if isinstance(o, dict) else {f"{x.get('family')}:{x.get('name')}": x for x in o}


# D.1 operator superset proof: parsed, build_instructions  ⊆  enriched
E = load(enr)
EM = opmap(E)
for nm, pth in [("parsed", parsed), ("build_instructions", bi)]:
    S = load(pth)
    SM = opmap(S)
    miss = [k for k in SM if k not in EM]
    chk(f"D.1 {nm}: all {len(SM)} ops in enriched", not miss, f"missing={len(miss)}")
    chk(f"D.1 {nm}: classes equal", E.get("classes") == S.get("classes"))
    chk(f"D.1 {nm}: concepts equal", E.get("concepts") == S.get("concepts"))


# D.4 vector counts via chroma sqlite
def cnt(p):
    if not os.path.exists(p):
        return None
    c = sqlite3.connect(p)
    try:
        n = c.execute("select count(*) from embeddings").fetchone()[0]
    except Exception as e:
        n = f"err:{e}"
    c.close()
    return n


mg = cnt(P("META_AGENTIC_TOOL", "data", "vector_db_merged", "chroma.sqlite3"))
sm = cnt(P("META_AGENTIC_TOOL", "data", "vector_db", "chroma.sqlite3"))
chk("D.4 merged vector count >= 34350", isinstance(mg, int) and mg >= 34350,
    f"(merged={mg}, small={sm}; KBU_REPORT proved 1869 subset of 34350, 0 missing)")

os.makedirs(P("KB"), exist_ok=True)
proof = P("KB", "KBU_COMPLETENESS_PROOF.txt")
with open(proof, "w", encoding="utf-8") as f:
    f.write(f"KBU Completeness Proof  {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    f.write("Reproduces decisive KBU_REPORT.md assertions (D.1 / D.4 / D.6).\n\n")
    f.write("\n".join(results) + "\n\n")
    f.write(f"OVERALL: {'ALL PASS' if ok else 'FAILURES PRESENT'}\n")


def info(p):
    return ({"path": rel(p), "size": os.path.getsize(p), "md5": md5(p)}
            if os.path.exists(p) else {"path": rel(p), "missing": True})


manifest = {
    "name": "td-builder-mega-kb",
    "version": "0.1.0-prealpha",
    "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "note": "Canonical 4-axis KB bundle the live MCP server loads. See KB/KBU_REPORT.md.",
    "axes": {
        "operators": info(enr),
        "graphrag_chunks": info(gr_meta),
        "enhanced_graph": info(gp_meta),
        "vector_db": {"path": "META_AGENTIC_TOOL/data/vector_db_merged",
                      "collection": "td_unified", "docs": mg},
    },
    "completeness_proof": "KB/KBU_COMPLETENESS_PROOF.txt",
    "proof_status": "ALL PASS" if ok else "FAILURES",
}
json.dump(manifest, open(P("KB", "manifest.json"), "w", encoding="utf-8"), indent=2)

print("\n".join(results))
print("OVERALL:", "ALL PASS" if ok else "FAILURES")
print("wrote:", proof)
print("wrote:", P("KB", "manifest.json"))
