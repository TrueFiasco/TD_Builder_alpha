#!/usr/bin/env python3
r"""Export local feedback records into one redacted bundle for a GitHub issue.

STANDALONE CLI — deliberately NOT an MCP tool (adding a tool would rotate the 17-tool
P01b inventory and its hash). Reads the opt-in JSONL records written by
``MCP/feedback.py`` (``~/.td_builder/feedback/`` by default), defensively
re-redacts every record, writes a Markdown report + the redacted raw JSONL into one
``.zip`` in the current directory, and prints where it landed.

Local only: this script makes ZERO network calls (it imports no socket/HTTP module).
Nothing is uploaded — the user decides whether to attach the bundle.

    py -3.11 scripts/export_feedback.py [--since YYYY-MM-DD] [--last N]
                                        [--dir DIR] [--out PATH]

Review the bundle before attaching it to an issue.
"""

import argparse
import io
import json
import os
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Reuse the recorder's dir resolution + redaction (MCP/ is the shared home).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "MCP"))
try:
    import feedback  # noqa: E402
except Exception as exc:  # pragma: no cover - only if the layout is broken
    print(f"export_feedback: could not import MCP/feedback.py ({exc})", file=sys.stderr)
    sys.exit(2)


def _load(records_dir: Path):
    headers, calls = [], []
    for f in sorted(records_dir.glob("*.jsonl")):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("kind") == "session_header":
                    headers.append(feedback.redact_record(obj))
                else:
                    obj["_source"] = f.name
                    calls.append(feedback.redact_record(obj))
        except OSError:
            continue
    return headers, calls


def _filter(calls, since: str, last: int):
    if since:
        calls = [c for c in calls if str(c.get("ts", "")) >= since]
    calls.sort(key=lambda c: str(c.get("ts", "")))
    if last and last > 0:
        calls = calls[-last:]
    return calls


def _summary_md(headers, calls) -> str:
    by_tool = Counter(c.get("tool", "?") for c in calls)
    by_outcome = Counter(c.get("outcome", "unknown") for c in calls)
    events = [c for c in calls if c.get("event_type")]
    lines = []
    lines.append("# TD Builder feedback bundle")
    lines.append("")
    lines.append(f"- generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- records: {len(calls)}  |  sessions: {len(headers)}")
    lines.append("")
    if headers:
        lines.append("## Environment identity")
        for h in headers:
            ident = h.get("identity", {})
            lines.append(f"- {h.get('server','?')}: " + ", ".join(
                f"{k}={ident.get(k)}" for k in
                ("server_version", "kb_manifest_version", "kb_sha",
                 "tool_inventory_hash", "instructions_hash", "platform", "python")
                if ident.get(k) is not None))
        lines.append("")
    lines.append("## Outcomes")
    for k, v in by_outcome.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Calls by tool")
    for k, v in by_tool.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("")
    if events:
        lines.append("## Troubleshooting events")
        for c in events:
            desc = c.get("description") or ""
            lines.append(f"- [{c.get('ts','?')}] {c.get('tool','?')} "
                         f"{c.get('event_type')}: {desc}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bundle local feedback records for an issue report.")
    ap.add_argument("--dir", help="feedback records dir (default: the recorder's dir)")
    ap.add_argument("--since", default="", help="only records with ts >= this (YYYY-MM-DD)")
    ap.add_argument("--last", type=int, default=0, help="keep only the N most recent records")
    ap.add_argument("--out", help="output .zip path (default: ./td_builder_feedback_<UTC>.zip)")
    args = ap.parse_args(argv)

    records_dir = Path(args.dir).expanduser() if args.dir else feedback.feedback_dir()
    if not records_dir.exists():
        print(f"No feedback records found at {records_dir}. "
              "Is TD_FEEDBACK_ENABLED set? Nothing to export.")
        return 1

    headers, calls = _load(records_dir)
    calls = _filter(calls, args.since, args.last)
    if not calls:
        print(f"No records matched (dir={records_dir}, since={args.since!r}, last={args.last}).")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out).expanduser() if args.out else Path.cwd() / f"td_builder_feedback_{stamp}.zip"
    report = _summary_md(headers, calls)
    jsonl = "\n".join(json.dumps(c, ensure_ascii=False) for c in calls) + "\n"
    header_jsonl = "\n".join(json.dumps(h, ensure_ascii=False) for h in headers) + "\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("REPORT.md", report)
        z.writestr("records.jsonl", jsonl)
        z.writestr("sessions.jsonl", header_jsonl)
    out.write_bytes(buf.getvalue())

    print(f"Wrote {out}  ({len(calls)} records, {len(headers)} session headers).")
    print("Review the bundle before attaching it to an issue. "
          "Nothing was uploaded — this tool makes no network calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
