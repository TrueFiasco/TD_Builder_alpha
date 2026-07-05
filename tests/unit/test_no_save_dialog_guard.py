"""Static-invariant guard for the live TD WebServer service modules.

The pre-mutation restore point (``api_service._ensure_session_restore_point``) must
NEVER raise a TouchDesigner modal dialog: the WebServer DAT's ``onHTTPRequest`` runs
on TD's single main thread, so any modal freezes the whole live connection with no
timeout rescue (that is why the fix uses a pure filesystem copy — ``_snapshot_toe`` —
and never ``project.save()``).

This is a REGRESSION TRIPWIRE over COMMITTED SOURCE. It fails if a maintainer
reintroduces a dialog-capable call anywhere in the td-webserver modules:
  - ``<...>.project.save(...)`` — no-arg save increments (and can pop an overwrite
    modal if the increment target exists); ``save(<path>)`` is Save-As (rebinds).
  - a ``ui`` / ``td.ui`` file/message dialog (``messageBox`` / ``chooseFile`` /
    ``chooseFolder``).

LIMITS (documented on purpose): AST matches the literal source spelling only. It does
NOT catch aliased forms (``p = td.project; p.save()``), ``getattr(x, 'save')()``, or
arbitrary user scripts run via ``exec_python_script``. Runtime safety comes from
``_ensure_session_restore_point`` no longer touching ``td.project`` plus the
filesystem-only ``_snapshot_toe`` primitive — this test just keeps the source honest.

Pattern mirrors the AST source-scan in ``tests/unit/test_output_budgets.py``. No
TouchDesigner, KB, or ML deps — it only reads and parses text.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "MCP" / "td-webserver" / "modules"
API_SERVICE = MODULES / "mcp" / "services" / "api_service.py"

# ``ui``/``td.ui`` methods that pop a blocking modal. Exact names only — do NOT add
# ``openFile``/``folderDialog`` (not real TD ``ui`` methods → dead clauses).
_DIALOG_METHODS = {"messageBox", "chooseFile", "chooseFolder"}


def _module_files() -> list[Path]:
    files = sorted(MODULES.rglob("*.py"))
    assert files, f"no service modules found under {MODULES}"
    return files


def _is_project_save(call: ast.Call) -> bool:
    """True for ``<...>.project.save(...)``.

    Exact ``attr == "save"`` so ``top.saveByteArray(...)`` (capture_service) does NOT
    match, and the receiver must be ``.project`` so the ``td.project`` dict-VALUE in
    exec_python_script's globals (not a call) does not match either.
    """
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == "save"
        and isinstance(f.value, ast.Attribute)
        and f.value.attr == "project"
    )


def _receiver_is_ui(value: ast.AST) -> bool:
    """Receiver resolves to bare ``ui`` or ``td.ui`` — required, so an unrelated
    ``obj.messageBox(...)`` does not false-trip."""
    if isinstance(value, ast.Name) and value.id == "ui":
        return True
    return isinstance(value, ast.Attribute) and value.attr == "ui"


def _is_ui_dialog(call: ast.Call) -> bool:
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr in _DIALOG_METHODS
        and _receiver_is_ui(f.value)
    )


def test_no_project_save_or_ui_dialog_in_service_modules():
    """No committed td-webserver source may call ``project.save()`` or a ``ui`` dialog
    — both can raise a TD modal that hangs the single-threaded WebServer DAT."""
    offenders: list[str] = []
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _is_project_save(node):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno} project.save(...)")
            elif _is_ui_dialog(node):
                offenders.append(
                    f"{path.relative_to(REPO)}:{node.lineno} ui.{node.func.attr}(...)"
                )
    assert not offenders, (
        "dialog-capable call(s) in td-webserver service modules — these can hang the "
        "WebServer thread; route saves through the filesystem-only _snapshot_toe:\n  "
        + "\n  ".join(offenders)
    )


def _only_call(src: str) -> ast.Call:
    """Parse a one-expression snippet and return its Call node."""
    return ast.parse(src, mode="eval").body  # type: ignore[return-value]


def test_project_save_matcher_has_teeth():
    """The matcher fires on real project.save() forms and ignores the look-alikes,
    so the tripwire above cannot be defeated by a rename or false-trip on saveByteArray."""
    assert _is_project_save(_only_call("td.project.save()"))
    assert _is_project_save(_only_call("td.project.save(path)"))
    assert _is_project_save(_only_call("self.td.project.save()"))
    # Negatives that MUST NOT match:
    assert not _is_project_save(_only_call("top.saveByteArray(ext)"))   # capture_service
    assert not _is_project_save(_only_call("obj.save()"))               # not on .project
    assert not _is_project_save(_only_call("shutil.copyfile(a, b)"))    # the sanctioned primitive


def test_ui_dialog_matcher_has_teeth():
    """Fires on ui/td.ui dialogs, ignores unrelated same-named methods."""
    assert _is_ui_dialog(_only_call("ui.messageBox('t', 'm')"))
    assert _is_ui_dialog(_only_call("td.ui.chooseFile()"))
    assert _is_ui_dialog(_only_call("td.ui.chooseFolder()"))
    # Negatives:
    assert not _is_ui_dialog(_only_call("dialog.messageBox()"))   # receiver isn't ui
    assert not _is_ui_dialog(_only_call("ui.panel()"))            # not a dialog method


def _find_func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {API_SERVICE}")


def _assigns_project_attr(func: ast.FunctionDef) -> list[int]:
    """Lines of any ``<...>.project.<attr> = ...`` assignment target (a rebind)."""
    def is_project_attr_target(t: ast.AST) -> bool:
        return (
            isinstance(t, ast.Attribute)
            and isinstance(t.value, ast.Attribute)
            and t.value.attr == "project"
        )

    hits: list[int] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        else:
            continue
        for t in targets:
            for sub in ast.walk(t):
                if is_project_attr_target(sub):
                    hits.append(node.lineno)
    return hits


def test_restore_point_does_not_rebind_project():
    """Structural no-rebind: neither ``_ensure_session_restore_point`` nor
    ``_snapshot_toe`` assigns to ``td.project.*`` (name/folder/path). Only
    ``project.save(path)`` rebinds and we don't call it — this also forbids a direct
    attribute rebind."""
    tree = ast.parse(API_SERVICE.read_text(encoding="utf-8"))
    for fn in ("_ensure_session_restore_point", "_snapshot_toe"):
        hits = _assigns_project_attr(_find_func(tree, fn))
        assert not hits, f"{fn} assigns td.project.* (rebind) at lines {hits}"
