# alpha_revisions

Proposed changes to the **`C:\TD_builder_alpha`** codebase (outside `tests/`)
that cannot be applied directly from this workflow due to the write boundary
(all writes confined to `C:\TD_builder_alpha\tests\`).

Each `NNN-*.md` is a self-contained, actionable revision proposal: the gap,
the evidence, the exact file/function to change, a concrete patch sketch, and
how to verify. Someone with alpha edit rights reviews and applies them.

**Do not** work around these gaps inside `tests/glsl_eval/` (no wrapper
recipes that hand-add what the tool itself should emit) — fixes belong here as
proposals, applied at the source.
