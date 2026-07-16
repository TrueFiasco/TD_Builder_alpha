"""W7 — user-component engine units (kb_build/user_components.py).

Hermetic: no KB queries, no chromadb/sentence-transformers (those imports are
lazy inside the ingest functions this module never calls), no TD binary — runs
in the KB-free CI lane. Covers: the .cparm mini-parser (Δ7), build_entry
(harvest stamp + G6 + semantic fields + parameter descriptions), the semantic
hash, block-row shapes, registry atomicity, the commit lockfile, and the
commit_specs fail-fast paths (containment / overwrite / confirm_shadow / G6).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from kb_build import user_components as uc  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _skeleton(*, wrapper=False, subcompname=None, cparm=None, parm_values=None,
              contained=("CHOP:lfo", "CHOP:math")):
    """Fabricated parse_component output (no toeexpand)."""
    sk = {
        "manifest": {
            "inputs": [{"name": "in1", "op_type": "CHOP:in"}],
            "outputs": [{"name": "chansOut", "op_type": "CHOP:out"},
                        {"name": "valueOut", "op_type": "CHOP:out"}],
            "families": {"CHOP": 4},
            "operator_count": 5,
            "connection_count": 3,
            "interface_path": "/myComp",
            "wrapper": wrapper,
            "summary": "",
        },
        "inner_type": "COMP:base",
        "subcompname": subcompname,
        "contained_operators": sorted(contained),
        "interface_files": {"cparm": cparm, "parm_values": dict(parm_values or {})},
    }
    pars, warns = uc.custom_parameters_from_skeleton(sk)
    sk["custom_parameters"] = pars
    sk["parse_warnings"] = warns
    return sk


CPARM = """?
pages 2 Main About
772804865 Gain Gain 1 1 0 0 1 1 4 0 1.5 "" Main 0
-1374678769 Blend "Blend Mode" 1 1 0 0 1 1 1 0 0 over Main 4097 3 over Over add Add screen Screen 1
772804880 File "File Path" 1 1 0 0 1 1 1 2 0 "app.samplesFolder + '/x.mp4'" "" Main 2
772804869 Reset Reset 1 1 0 0 1 1 1 0 0 "" About 0
?
"""


# ---------------------------------------------------------------------------
# .cparm mini-parser (Δ7)
# ---------------------------------------------------------------------------
def test_cparm_float_menu_string_pulse():
    pages, pars, warns = uc.parse_cparm(CPARM)
    assert pages == ["Main", "About"]
    assert warns == []
    by = {p["name"]: p for p in pars}
    assert by["Gain"] == {"name": "Gain", "label": "Gain", "page": "Main",
                          "type_class": "number", "default": 1.5, "min": 0, "max": 4}
    assert by["Blend"]["type_class"] == "menu"
    assert [m["token"] for m in by["Blend"]["menu"]] == ["over", "add", "screen"]
    assert by["Blend"]["menu"][1]["label"] == "Add"
    assert by["Blend"]["default"] == "over"
    assert by["File"]["type_class"] == "string"
    assert by["File"]["default"] == "app.samplesFolder + '/x.mp4'"
    assert by["Reset"]["type_class"] == "pulse"
    assert "default" not in by["Reset"]
    # stable page-then-order sort
    assert [p["name"] for p in pars] == ["Gain", "Blend", "File", "Reset"]


def test_cparm_two_slot_format_and_enable_expr():
    # moviePlayer-era save format: two trailing string slots + enable expression
    text = ('?\npages 1 Setup\n'
            '772935937 Fade "Fade (sec)" 1 3 0 0 1 1 1 2 0.2 "" "" Setup 1 '
            '"me.par.Mode != \'cut\'"\n?')
    _, pars, warns = uc.parse_cparm(text)
    assert warns == []
    assert pars[0]["default"] == 0.2
    assert pars[0]["min"] == 0 and pars[0]["max"] == 1


def test_cparm_dynamic_menu_source_expressions():
    # scripted menu: <order> <n> <expr>*n tail (observed on device-list menus)
    text = ("?\npages 1 Setup\n"
            "1846677775 Drv Driver 1 1 0 0 1 1 10 2 0 default \"\" Setup 4097 2 "
            "default Default asio ASIO 6 2 op('./devout').par.driver "
            "me.par.Internal\n?")
    _, pars, warns = uc.parse_cparm(text)
    assert warns == []
    assert pars[0]["type_class"] == "menu"
    assert [m["token"] for m in pars[0]["menu"]] == ["default", "asio"]
    assert pars[0]["default"] == "default"


def test_cparm_multi_value_defaults():
    # synthetic RGB color par: repeated (<int> <default> <""×s>) groups
    text = ('?\npages 1 Main\n'
            '772809473 Tint "Tint Color" 1 1 0 0 1 1 1 1 0 0 1 1 1 1 0 0 1 1 1 '
            '0 0.25 "" 0 0.5 "" 0 1 "" Main 3\n?')
    _, pars, warns = uc.parse_cparm(text)
    assert warns == []
    assert pars[0]["type_class"] == "multi"
    assert pars[0]["default"] == [0.25, 0.5, 1]


def test_cparm_menu_with_empty_default_is_silent():
    text = ('?\npages 1 Main\n'
            '772804879 Src "Source Type" 1 1 0 0 1 1 1 2 0 "" "" Main 4097 2 '
            'a A b B 0\n?')
    _, pars, warns = uc.parse_cparm(text)
    assert warns == []
    assert pars[0]["type_class"] == "menu" and "default" not in pars[0]


def test_cparm_unparseable_line_degrades_loudly():
    text = "?\npages 1 Main\n772804865 Broken BrokenLabel 1 2\n?"
    _, pars, warns = uc.parse_cparm(text)
    assert pars == [{"name": "Broken", "label": "BrokenLabel"}]
    assert warns and "Broken" in warns[0]


def test_effective_default_prefers_parm_override():
    sk = _skeleton(cparm=CPARM, parm_values={"Gain": "2.75", "Blend": "screen"})
    by = {p["name"]: p for p in sk["custom_parameters"]}
    assert by["Gain"]["default"] == 2.75          # numeric coercion for number pars
    assert by["Blend"]["default"] == "screen"     # verbatim token override
    assert by["File"]["default"].startswith("app.samplesFolder")  # no override


# ---------------------------------------------------------------------------
# build_entry — stamp, G6, semantic fields, descriptions
# ---------------------------------------------------------------------------
def test_build_entry_shape_and_harvest_stamp():
    sk = _skeleton(cparm=CPARM)
    entry, warns = uc.build_entry(sk, source="project", tox_path="C:/x/myComp.tox",
                                  summary="  A   test comp.  ",
                                  use_cases=["glow", " ", "pulse fx"])
    # structural half (offline_entry) — NAME-SORTED indexes + the stamp that
    # keeps the builder on the strict NAME-authority wiring policy (BUG-3 class)
    assert entry["harvest"]["method"] == "offline_manifest"
    assert [d["in_op"] for d in entry["inputs"]] == ["in1"]
    assert [d["out_op"] for d in entry["outputs"]] == ["chansOut", "valueOut"]
    assert entry["wrapper"] is False and entry["inner_type"] == "COMP:base"
    # semantic half
    assert entry["summary"] == "A test comp."
    assert entry["use_cases"] == ["glow", "pulse fx"]
    assert entry["contained_operators"] == ["CHOP:lfo", "CHOP:math"]
    assert entry["complexity"] == "simple"
    assert [p["name"] for p in entry["custom_parameters"]] == \
        ["Gain", "Blend", "File", "Reset"]
    assert warns == []


def test_build_entry_requires_summary():
    with pytest.raises(uc.UserComponentError) as ei:
        uc.build_entry(_skeleton(), source="project", tox_path="C:/x.tox", summary="  ")
    assert ei.value.kind == "missing_summary"


def test_build_entry_parameter_descriptions_merge_and_warn():
    sk = _skeleton(cparm=CPARM)
    entry, warns = uc.build_entry(
        sk, source="project", tox_path="C:/x.tox", summary="s",
        parameter_descriptions={"Gain": "output gain", "Nope": "ghost"})
    by = {p["name"]: p for p in entry["custom_parameters"]}
    assert by["Gain"]["description"] == "output gain"
    assert "description" not in by["Blend"]
    assert any("Nope" in w for w in warns)


def test_g6_guard_engine_home():
    # relative passes for user/derivative; absolute raises with the actionable text
    uc.relative_path_guard("user", "myComp.tox")
    uc.relative_path_guard("project", "C:/anywhere/myComp.tox")
    for src in ("user", "derivative"):
        with pytest.raises(uc.UserComponentError) as ei:
            uc.relative_path_guard(src, "C:/abs/myComp.tox")
        assert ei.value.kind == "absolute_tox_path"
        assert "must be RELATIVE" in str(ei.value)
    with pytest.raises(uc.UserComponentError):
        uc.build_entry(_skeleton(), source="user", tox_path="C:/abs/x.tox", summary="s")


def test_complexity_buckets():
    assert uc._complexity_bucket(3) == "simple"
    assert uc._complexity_bucket(11) == "moderate"
    assert uc._complexity_bucket(41) == "complex"
    assert uc._complexity_bucket(None) is None


# ---------------------------------------------------------------------------
# semantic hash — the staleness basis (covers par names + descriptions, Δ7)
# ---------------------------------------------------------------------------
def test_semantic_hash_sensitivity():
    sk = _skeleton(cparm=CPARM)
    e1, _ = uc.build_entry(sk, source="project", tox_path="C:/x.tox", summary="s",
                           parameter_descriptions={"Gain": "d1"})
    h1 = uc.semantic_hash_of_entry(e1)
    assert h1 == uc.semantic_hash_of_entry(json.loads(json.dumps(e1)))  # stable
    e2 = json.loads(json.dumps(e1))
    e2["summary"] = "edited"
    assert uc.semantic_hash_of_entry(e2) != h1
    e3 = json.loads(json.dumps(e1))
    e3["custom_parameters"][0]["description"] = "d2"
    assert uc.semantic_hash_of_entry(e3) != h1
    e4 = json.loads(json.dumps(e1))
    e4["custom_parameters"][0]["default"] = 999   # NON-semantic field: no re-ingest
    assert uc.semantic_hash_of_entry(e4) == h1


def test_stack_hash_copy_is_in_lockstep():
    """retrieval_stack carries a COPY of semantic_hash_of_entry (it must not
    import kb_build at runtime) — drift between the two silently breaks the
    staleness guard, so pin them byte-equal here."""
    import importlib.util
    p = REPO / "MCP" / "server_core" / "search" / "retrieval_stack.py"
    spec = importlib.util.spec_from_file_location("rs_for_hash_test", str(p))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    sk = _skeleton(cparm=CPARM)
    entry, _ = uc.build_entry(sk, source="project", tox_path="C:/x.tox", summary="s",
                              parameter_descriptions={"Gain": "d"})
    assert rs._semantic_hash_of_entry(entry) == uc.semantic_hash_of_entry(entry)


# ---------------------------------------------------------------------------
# block rows — user: namespace, meta contract, shadow + custom-par text
# ---------------------------------------------------------------------------
def _entry(**kw):
    sk = _skeleton(cparm=kw.pop("cparm", CPARM))
    entry, _ = uc.build_entry(sk, source="project", tox_path="C:/x/myComp.tox",
                              summary=kw.pop("summary", "A glow pulse generator."),
                              use_cases=kw.pop("use_cases", ["glow"]), **kw)
    return entry


def test_block_rows_shapes_and_namespace():
    rows = uc.component_block_rows("myComp", _entry())
    assert [r["chunk_type"] for r in rows] == \
        ["block_overview", "block_usecase", "block_io"]
    assert rows[0]["id"] == "user:block:mycomp:overview"
    assert rows[1]["id"] == "user:block:mycomp:usecase"
    assert rows[2]["id"] == "user:block:mycomp:io"
    for r in rows:
        assert r["meta"]["type"] == r["chunk_type"]
        assert r["meta"]["__source_store"] == "td_block"
        assert r["meta"]["license_tier"] == "user"
        assert r["meta"]["name"] == "myComp"
    assert rows[1]["parent_chunk"] == rows[0]["id"]
    assert rows[2]["parent_chunk"] == rows[0]["id"]
    assert 'Instantiate via the builder: {"palette": "myComp"}' in rows[0]["text"]


def test_block_io_carries_custom_pars_with_verbatim_menu_tokens():
    rows = uc.component_block_rows("myComp", _entry())
    io = rows[2]["text"]
    assert "Custom parameters:" in io
    assert "menu tokens: over|add|screen" in io       # VERBATIM tokens (Δ7)
    assert "Gain" in io and "default 1.5" in io and "range 0..4" in io
    assert "Set menu parameters by string token" in io


def test_block_io_emitted_for_pars_even_without_contained_ops():
    # template deviation vs shipped §6.4, documented in the engine
    sk = _skeleton(cparm=CPARM, contained=())
    entry, _ = uc.build_entry(sk, source="project", tox_path="C:/x.tox", summary="s")
    rows = uc.component_block_rows("noInv", entry)
    assert [r["chunk_type"] for r in rows] == \
        ["block_overview", "block_usecase", "block_io"]
    # and with neither inventory nor pars, io is omitted (2 rows)
    sk2 = _skeleton(cparm=None, contained=())
    e2, _ = uc.build_entry(sk2, source="project", tox_path="C:/x.tox", summary="s")
    assert [r["chunk_type"] for r in uc.component_block_rows("bare", e2)] == \
        ["block_overview", "block_usecase"]


def test_shadow_sentence_only_when_shadowing():
    e = _entry()
    plain = uc.component_block_rows("myComp", e, shadows_shipped=False)
    shadow = uc.component_block_rows("myComp", e, shadows_shipped=True)
    marker = "Overrides the Derivative palette component of the same name"
    assert marker not in plain[0]["text"]
    assert marker in shadow[0]["text"]


def test_description_reaches_io_text():
    rows = uc.component_block_rows(
        "myComp", _entry(parameter_descriptions={"Blend": "compositing operator"}))
    assert "compositing operator" in rows[2]["text"]


# ---------------------------------------------------------------------------
# registry I/O — atomic upsert, corrupt-registry refusal
# ---------------------------------------------------------------------------
def test_upsert_registry_atomic_and_replaced_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    entry = _entry()
    assert uc.upsert_registry_entry("myComp", entry) is False
    reg = tmp_path / "user_components.json"
    assert reg.is_file() and not reg.with_name(reg.name + ".tmp").exists()
    spec = json.loads(reg.read_text(encoding="utf-8"))
    assert spec["components"]["myComp"]["harvest"]["method"] == "offline_manifest"
    assert uc.upsert_registry_entry("myComp", entry) is True   # replaced


def test_corrupt_registry_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    (tmp_path / "user_components.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(uc.UserComponentError) as ei:
        uc.load_registry()
    assert ei.value.kind == "registry_unreadable"


# ---------------------------------------------------------------------------
# commit lockfile — outside the guarded tree, stale age-out
# ---------------------------------------------------------------------------
def test_commit_lock_location_and_contention(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    lock = uc._lock_path()
    assert lock == tmp_path / ".locks" / "user_index.lock"
    assert "user_index" != lock.parent.name  # OUTSIDE the guarded tree (W2)
    with uc.commit_lock(timeout_s=1.0):
        assert lock.exists()
        with pytest.raises(uc.UserComponentError) as ei:
            with uc.commit_lock(timeout_s=0.3):
                pass
        assert ei.value.kind == "locked"
    assert not lock.exists()


def test_commit_lock_stale_age_out(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    lock = uc._lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999 0\n", encoding="ascii")
    old = time.time() - 2 * uc._LOCK_STALE_S
    os.utime(lock, (old, old))
    with uc.commit_lock(timeout_s=1.0):     # aged out, acquired
        assert lock.exists()
    assert not lock.exists()


# ---------------------------------------------------------------------------
# commit_specs fail-fast paths (all BEFORE any toeexpand — hermetic)
# ---------------------------------------------------------------------------
@pytest.fixture()
def palette(tmp_path, monkeypatch):
    pal = tmp_path / "palette"
    pal.mkdir()
    monkeypatch.setenv("TD_USER_PALETTE_DIR", str(pal))
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path / "user"))
    return pal


def _stub_tox(tmp_path, name="comp.tox"):
    f = tmp_path / name
    f.write_text("stub", encoding="utf-8")
    return str(f)


def test_commit_containment_rejects_separators(palette, tmp_path):
    spec = {"tox_path": _stub_tox(tmp_path), "name": "comp", "summary": "s"}
    res = uc.commit_specs([spec], save_to_palette=True, folder="a/b")
    assert res[0]["ok"] is False and res[0]["error"]["kind"] == "containment"
    res = uc.commit_specs([dict(spec, name="..evil")], save_to_palette=True)
    assert res[0]["ok"] is False and res[0]["error"]["kind"] == "containment"
    assert not any(palette.rglob("*.tox")), "no copy may happen on refusal"


def test_commit_palette_collision_refused_without_overwrite(palette, tmp_path):
    target = palette / "TD_Builder" / "comp.tox"
    target.parent.mkdir(parents=True)
    target.write_text("existing", encoding="utf-8")
    spec = {"tox_path": _stub_tox(tmp_path), "name": "comp", "summary": "s"}
    res = uc.commit_specs([spec], save_to_palette=True)
    assert res[0]["error"]["kind"] == "palette_collision"
    assert "overwrite" in res[0]["error"]["message"]
    assert target.read_text(encoding="utf-8") == "existing"


def test_commit_confirm_shadow_required_for_palette_saves(palette, tmp_path):
    # 'bloom' ships in KB/palette_components.json — a palette-saved shadow of it
    # must be refused without confirm_shadow (owner decision 3); project-source
    # adds warn only (shadows_shipped flag, no refusal at this stage).
    assert "bloom" in uc.shipped_component_names(), "test premise: bloom is shipped"
    spec = {"tox_path": _stub_tox(tmp_path, "bloom.tox"), "summary": "s"}
    res = uc.commit_specs([spec], save_to_palette=True)
    assert res[0]["error"]["kind"] == "shadow_unconfirmed"
    assert res[0]["shadows_shipped"] is True
    assert not any(palette.rglob("*.tox"))


def test_commit_g6_fail_fast_before_parse(palette, tmp_path):
    spec = {"tox_path": _stub_tox(tmp_path), "name": "comp", "summary": "s",
            "source": "user"}
    res = uc.commit_specs([spec])     # no save_to_palette: abs default emitted
    assert res[0]["error"]["kind"] == "absolute_tox_path"
    assert "must be RELATIVE" in res[0]["error"]["message"]
