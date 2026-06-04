"""Optional in-house fuzzy scorer (Inspect-AI `model_graded_qa` idea, local).

Used ONLY for sub-metrics with no hard answer key (retrieval NL relevance,
crosscut message quality). Default is deterministic + free + offline; the LLM
judge is opt-in behind RUN_JUDGE=1 + ANTHROPIC_API_KEY. Targets #1 and #3
never call this — they are pure diffs.
"""
from __future__ import annotations

import os
import re


def judge_enabled() -> bool:
    return bool(os.environ.get("RUN_JUDGE")) and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _heuristic(rubric: str, content: str) -> tuple[float, str]:
    """Cheap lexical proxy: keyword overlap between rubric cues and content."""
    cues = [w for w in re.findall(r"[a-zA-Z]{4,}", rubric.lower())]
    if not cues:
        return 0.5, "no rubric cues; neutral"
    c = content.lower()
    hit = sum(1 for w in set(cues) if w in c)
    score = round(min(1.0, hit / max(1, len(set(cues)))), 4)
    return score, f"heuristic: {hit}/{len(set(cues))} rubric cues present"


def rubric_score(rubric: str, content: str) -> tuple[float, str]:
    """Return (0..1, justification). LLM-graded when enabled, else heuristic."""
    if not judge_enabled():
        return _heuristic(rubric, content)
    try:
        import anthropic  # lazy; only when opted in

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    "Score 0.0-1.0 how well the RESPONSE satisfies the RUBRIC. "
                    "Reply as `<score> | <one-line reason>`.\n\n"
                    f"RUBRIC:\n{rubric}\n\nRESPONSE:\n{content[:4000]}"
                ),
            }],
        )
        text = msg.content[0].text.strip()
        m = re.match(r"\s*([01](?:\.\d+)?)", text)
        score = float(m.group(1)) if m else 0.5
        return round(min(1.0, max(0.0, score)), 4), f"llm: {text[:120]}"
    except Exception as exc:  # noqa: BLE001 - judge must never break a run
        s, why = _heuristic(rubric, content)
        return s, f"llm judge failed ({type(exc).__name__}); {why}"
