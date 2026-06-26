"""Round-4 #3 (first slice) — wire the dormant expertise YAMLs into the experts.

Each expert's config.yaml declares `expertise_inputs:` (curated YAML knowledge), but no code
ever read them — get_expert_prompt returned only the phase .md. load_expert_prompt now also
loads those declared YAMLs and appends them (size-capped) so the curated knowledge actually
reaches the expert. Tested via the loaded server module.
"""


def test_expert_prompt_injects_declared_expertise(server):
    p = server.load_expert_prompt("critic", "build")
    assert isinstance(p, str) and not p.startswith("ERROR"), p[:200]
    assert "## Curated expertise" in p, "declared expertise was not injected"
    # critic's config declares critique_patterns.yaml — its name AND content must appear
    assert "critique_patterns.yaml" in p
    assert "quality_criteria" in p  # an actual key from critique_patterns.yaml


def test_load_expert_expertise_helper(server):
    helper = getattr(server, "_load_expert_expertise", None)
    assert callable(helper), "_load_expert_expertise not defined"
    assert helper("does_not_exist_expert") == ""
    crit = helper("critic")
    assert "critique_patterns.yaml" in crit and "creative_vision.yaml" in crit
