"""Repro for the self-review finding: expand_toe_file(mode='summary') enumerates every
glslPOP Create-Attributes / Vectors sequence param verbatim, blowing the token budget
(one glslPOP emitted ~50 rows; a real .tox returned 100k+ chars).

The summary should COLLAPSE long repeated sequence families (attrN*, vecN*, samplerN*…)
to a single representative + an explicit omitted-count marker — never silently truncate,
and never harm small 2-value params (fromrange1/2). Unit-tests the pure helper via the
loaded server module (the `server` fixture), so it's fast and KB-light.
"""


def test_collapse_seq_params_collapses_long_families_keeps_small_ones(server):
    collapse = getattr(server, "_collapse_seq_params", None)
    assert callable(collapse), "_collapse_seq_params not defined on server module"

    params = [{"name": "outputattrs", "value": "P", "mode": "constant"}]
    for i in range(8):  # a long Create-Attributes sequence
        params.append({"name": f"attr{i}name", "value": f"a{i}", "mode": "constant"})
        params.append({"name": f"attr{i}type", "value": "float", "mode": "constant"})
    # a small 2-value param family that must be preserved untouched
    params += [
        {"name": "fromrange1", "value": 0, "mode": "constant"},
        {"name": "fromrange2", "value": 1, "mode": "constant"},
    ]

    out = collapse(params)
    names = [p.get("name") for p in out]

    # plain scalar param preserved
    assert "outputattrs" in names
    # first block of each long family kept as a representative; later indices dropped
    assert "attr0name" in names and "attr0type" in names
    assert "attr7name" not in names and "attr5type" not in names
    # an explicit collapsed marker carries the omitted count (no silent truncation)
    markers = [p for p in out if p.get("collapsed")]
    assert markers, f"no collapsed marker emitted: {out}"
    assert all("omitted" in m.get("note", "") or m.get("collapsed") for m in markers)
    # small 2-member family is NOT collapsed
    assert "fromrange1" in names and "fromrange2" in names
    # net result is meaningfully smaller than the raw list
    assert len(out) < len(params)


def test_collapse_seq_params_noop_when_short(server):
    collapse = getattr(server, "_collapse_seq_params", None)
    assert callable(collapse)
    params = [
        {"name": "tx", "value": 1, "mode": "constant"},
        {"name": "ty", "value": 2, "mode": "constant"},
        {"name": "vec0name", "value": "uScale", "mode": "constant"},
        {"name": "vec0valuex", "value": 1.5, "mode": "constant"},
    ]
    out = collapse(params)
    # nothing long enough to collapse -> unchanged
    assert [p["name"] for p in out] == [p["name"] for p in params]
