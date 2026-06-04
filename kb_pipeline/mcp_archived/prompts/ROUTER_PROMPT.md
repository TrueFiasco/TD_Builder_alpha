# Prompt: TD Assistant Router (Cheap Model)

## Task
Classify the user request and choose the workflow + tools to run.

## Inputs
- `user_request` (string)

## Output (strict JSON)
Return exactly:
```json
{
  "intent": "lookup|explain|compare|design_network|build_project|debug_project|kb_maintenance",
  "recommended_workflow": "retrieve_only|retrieve_then_explain|retrieve_then_design|build_python|build_json|audit_kb",
  "preferred_sources": ["docs", "snippets", "palette"],
  "must_use_builder_rigor": false,
  "missing_info_questions": []
}
```

## Routing rules
- If the user asks “what is X / list parameters / how do I …” → retrieval workflows.
- If the user asks to “make a network / build a project”:
  - Prefer `build_python` unless they explicitly require `.toe/.tox` output.
  - If `.toe/.tox` output is required, set `must_use_builder_rigor=true` and choose `build_json` (template + expand/collapse).
- Prefer sources:
  - `docs` for parameter definitions and operator facts
  - `snippets` for real-world usage patterns
  - `palette` for “use this component” and production-ready building blocks
- If the request is under-specified, ask 1–3 focused questions in `missing_info_questions`.

