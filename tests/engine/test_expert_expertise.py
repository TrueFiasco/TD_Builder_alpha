"""Round-4 #3 (first slice) — wire the dormant expertise YAMLs into the experts.

Each expert's config.yaml declares `expertise_inputs:` (curated YAML knowledge), but no code
ever read them — get_expert_prompt returned only the phase .md. load_expert_prompt now also
loads those declared YAMLs and appends them (size-capped) so the curated knowledge actually
reaches the expert. Tested via the loaded server module.

Candidate-8 fix (2026-07): three experts (network_builder, td_glsl_expert,
td_python_expert) declared their YAMLs under a different `expertise:` schema the loader
never read — silently starved (loader returned ""). Their configs were migrated to
`expertise_inputs`; the roster-wide test below is the schema-drift guard that keeps any
expert from starving silently again.
"""
import pytest


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


def test_every_roster_expert_gets_expertise_injected(server):
    """Schema-drift guard: every expert in AVAILABLE_EXPERTS must yield a non-empty
    expertise block. An expert whose config declares its YAMLs under any key other
    than `expertise_inputs` starves silently (the loader returns "") — exactly what
    happened to network_builder / td_glsl_expert / td_python_expert."""
    for name in server.AVAILABLE_EXPERTS:
        block = server._load_expert_expertise(name)
        assert block, (
            f"{name}: _load_expert_expertise returned empty — config.yaml must "
            "declare curated YAMLs under `expertise_inputs` (path + purpose)")
        assert "## Curated expertise" in server.load_expert_prompt(name, "build"), name


@pytest.mark.parametrize("expert,first_yaml,content_key", [
    ("network_builder", "td_network_building.yaml", "build_rules"),
    ("td_glsl_expert", "td_glsl.yaml", "builtin_uniforms"),
    ("td_python_expert", "td_python.yaml", "referencing"),
])
def test_formerly_starved_expert_gets_yaml_content(server, expert, first_yaml, content_key):
    """The three migrated experts: their domain YAML's name AND an actual body key must
    reach the prompt (proves content injection, not just the section header)."""
    p = server.load_expert_prompt(expert, "build")
    assert isinstance(p, str) and not p.startswith("ERROR"), p[:200]
    assert first_yaml in p, f"{expert}: {first_yaml} not injected"
    assert content_key in p, f"{expert}: expected key {content_key!r} from {first_yaml}"
