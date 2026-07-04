#!/usr/bin/env python3
r"""
KB pickle trust boundary (harness remediation W2d).

``pickle.load`` deserializes arbitrary objects, so a KB pickle that does not
match what was published can execute code at load time. The two runtime
unpicklers (``search/retrieval_stack.py`` bm25.pkl,
``enhanced_graph_query.py`` knowledge_graph_enhanced.gpickle) used to load
whatever bytes sat in KB/ with no check.

THREAT MODEL — what this defends, and what it does NOT.
  This is defense-in-depth against TRANSPORT and SUPPLY-CHAIN corruption of
  the KB pickles as they travel the distribution path:
    * a corrupted / truncated / substituted DOWNLOAD — caught at fetch time by
      the release-zip sha256 (scripts/fetch_vector_db.py) before extraction;
    * a poisoned build-CACHE restore — caught at LOAD time here, because the
      restored bytes are re-hashed against a git-committed pin that lives in a
      different trust domain than the cache.
  It does NOT defend against a local adversary who can already write your
  ``KB/`` folder: such an attacker can also forge ``kb_receipt.json``, and
  write access to the install directory means the machine is already
  compromised (they could edit the server code itself). The value is catching
  a bad artifact that arrived through the distribution channel — not stopping
  local RCE. Treat this as a corruption/integrity guard, not a local sandbox.

``verify_pickle_bytes`` hashes the exact bytes that will be unpickled (read
once — no hash-then-reopen TOCTOU window) and requires a match against one of
two anchors, in order:

  1. **Receipt** — ``<kb_root>/kb_receipt.json``, written by a trusted local
     producer at a moment the content was known-good: ``fetch_vector_db.py``
     right after the zip-level sha256 verification, ``kb_build`` when it
     stages a maintainer-built KB, or ``scripts/receipt_kb.py`` when a
     maintainer explicitly blesses an existing KB. Checked first so a
     deliberate local rebuild wins over the release pin.
  2. **Pinned release manifest** — ``scripts/vector_db_release.json``'s
     ``artifact_sha256`` map (git-committed, code-reviewed — a separate trust
     domain from the KB directory itself). This is the anchor for the default
     flow: a fetched release KB verifies with no receipt at all, including a
     CI cache restore where only the artifacts (never a sidecar) are cached.

  No anchor match -> REFUSE to unpickle. Callers degrade loudly but keep the
  server up: bm25 -> dense-only retrieval, gpickle -> graph features off.

Escape hatch: ``TD_BUILDER_TRUST_KB=1`` skips verification with a LOUD
warning — for maintainers iterating on KB internals where writing a receipt
per edit is friction. Never set it in a deployment.

Import pattern: the two guard sites load this module file-relative via
importlib (registered as ``td_kb_integrity``), because both of them are
themselves exec'd standalone via spec_from_file_location and cannot rely on
package-relative imports or ambient sys.path.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

RECEIPT_NAME = "kb_receipt.json"
RECEIPT_SCHEMA = 1
TRUST_ENV = "TD_BUILDER_TRUST_KB"

# The artifacts the runtime unpickles. Receipt writers hash whichever of
# these exist under the KB root; the verifier looks the loaded file up by
# its kb_root-relative posix path.
PROTECTED_ARTIFACTS = (
    "knowledge_graph_enhanced.gpickle",
    "lexical_index/bm25.pkl",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def trust_override_active() -> bool:
    return (os.environ.get(TRUST_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


class Verdict:
    """Outcome of a load-time integrity check.

    Deliberately NOT a dataclass: this module is exec'd via
    spec_from_file_location, and @dataclass resolves cls.__module__ through
    sys.modules — a loader that execs before registering would crash here.
    """

    def __init__(self, ok: bool, anchor: str, reason: str):
        self.ok = ok
        self.anchor = anchor    # "receipt" | "manifest" | "trust-env" | ""
        self.reason = reason    # actionable detail when ok=False

    def __bool__(self) -> bool:  # allows `if verdict:` at call sites
        return self.ok

    def __repr__(self) -> str:
        return f"Verdict(ok={self.ok}, anchor={self.anchor!r}, reason={self.reason!r})"


# -- receipt side -------------------------------------------------------------

def _load_receipt(kb_root: Path) -> Optional[dict]:
    rp = Path(kb_root) / RECEIPT_NAME
    if not rp.exists():
        return None
    try:
        data = json.loads(rp.read_text(encoding="utf-8"))
    except Exception:
        return {"__malformed__": True}
    if not isinstance(data, dict) or not isinstance(data.get("artifacts"), dict):
        return {"__malformed__": True}
    # Each entry value must itself be a dict ({"sha256":..., "size":...}). A bare
    # scalar (e.g. {"artifacts": {"...gpickle": "deadbeef"}}) would slip past the
    # guards above and then raise AttributeError at entry.get("sha256") in
    # verify_pickle_bytes — flag the whole receipt malformed so the caller
    # returns a clean refuse-verdict instead of crashing the loader.
    if any(not isinstance(v, dict) for v in data["artifacts"].values()):
        return {"__malformed__": True}
    return data


def write_receipt(kb_root: Path, source: str,
                  artifacts: Optional[Iterable[str]] = None,
                  extra: Optional[Dict[str, str]] = None) -> Optional[Path]:
    """Hash the protected artifacts under ``kb_root`` and write kb_receipt.json.

    ``source`` records WHO blessed the content ("fetch_vector_db", "kb_build",
    "receipt_kb", ...) — provenance for humans reading the file, not a trust
    input. Returns the receipt path, or None when no protected artifact exists
    (nothing to protect -> no receipt; an empty receipt would just be noise).
    Existing receipts are replaced wholesale: a receipt describes the KB as it
    is NOW, not a history.
    """
    kb_root = Path(kb_root)
    rels = list(artifacts) if artifacts is not None else list(PROTECTED_ARTIFACTS)
    entries: Dict[str, dict] = {}
    for rel in rels:
        p = kb_root / rel
        if p.exists():
            entries[Path(rel).as_posix()] = {
                "sha256": sha256_file(p),
                "size": p.stat().st_size,
            }
    if not entries:
        return None
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "source": source,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifacts": entries,
    }
    if extra:
        receipt.update(extra)
    rp = kb_root / RECEIPT_NAME
    rp.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return rp


# -- manifest side ------------------------------------------------------------

def _find_release_manifest(kb_root: Path) -> Optional[Path]:
    """Locate scripts/vector_db_release.json for the standard <repo>/KB layout.

    Walk a couple of levels up from the KB root so eval's --kb <repo>/KB and
    the release layout both resolve; a KB parked outside any repo simply has
    no manifest anchor (the receipt path covers it).
    """
    kb_root = Path(kb_root).resolve()
    for base in (kb_root.parent, kb_root.parent.parent):
        cand = base / "scripts" / "vector_db_release.json"
        if cand.exists():
            return cand
    return None


def _manifest_pin(kb_root: Path, rel_posix: str) -> Optional[str]:
    mp = _find_release_manifest(kb_root)
    if mp is None:
        return None
    try:
        pins = json.loads(mp.read_text(encoding="utf-8")).get("artifact_sha256") or {}
    except Exception:
        return None
    v = pins.get(rel_posix)
    return v.lower() if isinstance(v, str) else None


# -- the check ----------------------------------------------------------------

def verify_pickle_bytes(data: bytes, artifact_path: Path, kb_root: Path) -> Verdict:
    """Decide whether ``data`` (the exact bytes about to be unpickled, already
    read from ``artifact_path``) is trusted for ``kb_root``.

    Order: trust-env override -> receipt entry -> pinned release manifest ->
    refuse. Mismatch against an anchor that HAS an entry refuses immediately
    (a "changed after receipt" message is more actionable than "unreceipted");
    a missing entry falls through to the next anchor.
    """
    artifact_path = Path(artifact_path)
    kb_root = Path(kb_root)
    try:
        rel = artifact_path.resolve().relative_to(kb_root.resolve()).as_posix()
    except ValueError:
        rel = artifact_path.name  # artifact outside kb_root: match by basename keys

    if trust_override_active():
        print(f"[kb_integrity] WARNING: {TRUST_ENV} is set - loading {rel} WITHOUT "
              f"integrity verification. Unset it unless you are actively rebuilding the KB.",
              file=sys.stderr)
        return Verdict(True, "trust-env", "")

    actual = sha256_bytes(data)
    fix_hint = (
        "Fix: re-run `python scripts/fetch_vector_db.py` after deleting the file "
        "(re-fetches the pinned release), or `python scripts/receipt_kb.py` to bless "
        f"a KB you built yourself, or set {TRUST_ENV}=1 to bypass (NOT recommended)."
    )

    receipt = _load_receipt(kb_root)
    if receipt is not None:
        if receipt.get("__malformed__"):
            return Verdict(False, "", f"{RECEIPT_NAME} at {kb_root} is malformed. {fix_hint}")
        entry = receipt["artifacts"].get(rel)
        if entry is not None:
            expected = str(entry.get("sha256", "")).lower()
            if actual == expected:
                return Verdict(True, "receipt", "")
            return Verdict(
                False, "",
                f"sha256 mismatch for {rel} vs {RECEIPT_NAME} (expected {expected[:16]}..., "
                f"got {actual[:16]}...) - the file changed AFTER it was receipted. "
                f"REFUSING to unpickle. {fix_hint}")
        # receipt exists but doesn't cover this artifact -> fall through to manifest

    pinned = _manifest_pin(kb_root, rel)
    if pinned is not None:
        if actual == pinned:
            return Verdict(True, "manifest", "")
        return Verdict(
            False, "",
            f"sha256 mismatch for {rel} vs the pinned release manifest "
            f"(expected {pinned[:16]}..., got {actual[:16]}...) - the file does not match "
            f"the published KB release (corrupted download, poisoned cache, or a stale/rebuilt "
            f"KB without a receipt). REFUSING to unpickle. {fix_hint}")

    return Verdict(
        False, "",
        f"no integrity anchor for {rel}: no {RECEIPT_NAME} entry under {kb_root} and no "
        f"artifact_sha256 pin in scripts/vector_db_release.json. REFUSING to unpickle "
        f"an unverified file. {fix_hint}")


def load_verified_pickle(artifact_path: Path, kb_root: Path):
    """Read -> verify -> unpickle in one call. Returns (obj, Verdict).

    On refusal returns (None, verdict) WITHOUT unpickling; the caller owns the
    degrade path (dense-only / graph-off) and the loud logging.
    """
    import pickle
    artifact_path = Path(artifact_path)
    data = artifact_path.read_bytes()
    verdict = verify_pickle_bytes(data, artifact_path, kb_root)
    if not verdict.ok:
        return None, verdict
    return pickle.loads(data), verdict
