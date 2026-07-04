"""Bless, audit, or pin an existing KB's pickled artifacts (W2d trust boundary).

The runtime refuses to unpickle `KB/lexical_index/bm25.pkl` and
`KB/knowledge_graph_enhanced.gpickle` unless their sha256 matches either
`KB/kb_receipt.json` or the `artifact_sha256` pins in
`scripts/vector_db_release.json` (see MCP/server_core/kb_integrity.py).
Fetched release KBs match the pins automatically; `fetch_vector_db.py` and the
`kb_build` pipeline write receipts for the KBs they produce. This script covers
everything else:

  python scripts/receipt_kb.py                 # bless <repo>/KB: write kb_receipt.json
  python scripts/receipt_kb.py --kb <path>     # bless a KB elsewhere
  python scripts/receipt_kb.py --check         # report each artifact's verdict, write nothing
  python scripts/receipt_kb.py --print-pins    # emit the artifact_sha256 JSON for a release

Run the default form ONLY for a KB whose content you trust (you built it, or
you extracted it from a bundle you verified) - the receipt IS the trust
statement the runtime believes.

`--print-pins` is the release-publishing hook: paste its output into
scripts/vector_db_release.json when pinning a new KB release zip.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _kb_integrity():
    mod = sys.modules.get("td_kb_integrity")
    if mod is None:
        p = REPO_ROOT / "MCP" / "server_core" / "kb_integrity.py"
        spec = importlib.util.spec_from_file_location("td_kb_integrity", str(p))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["td_kb_integrity"] = mod
        spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="Bless/audit/pin a KB's pickled artifacts")
    ap.add_argument("--kb", default=str(REPO_ROOT / "KB"),
                    help="KB root to operate on (default: <repo>/KB)")
    ap.add_argument("--check", action="store_true",
                    help="verify each artifact against receipt/pins and report; write nothing")
    ap.add_argument("--print-pins", action="store_true",
                    help="print the artifact_sha256 JSON block for scripts/vector_db_release.json")
    args = ap.parse_args()

    ki = _kb_integrity()
    kb = Path(args.kb)
    present = [rel for rel in ki.PROTECTED_ARTIFACTS if (kb / rel).exists()]
    if not present:
        print(f"No pickled artifacts found under {kb} - nothing to do.")
        return 1

    if args.print_pins:
        pins = {rel: ki.sha256_file(kb / rel) for rel in present}
        print(json.dumps({"artifact_sha256": pins}, indent=2))
        return 0

    if args.check:
        worst = 0
        for rel in present:
            p = kb / rel
            verdict = ki.verify_pickle_bytes(p.read_bytes(), p, kb)
            if verdict.ok:
                print(f"OK       {rel}  (anchor: {verdict.anchor})")
            else:
                worst = 2
                print(f"REFUSED  {rel}\n         {verdict.reason}")
        return worst

    rp = ki.write_receipt(kb, source="receipt_kb")
    print(f"Wrote {rp} covering: {', '.join(present)}")
    print("The runtime will now trust these exact bytes. Re-run this after any deliberate rebuild.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
