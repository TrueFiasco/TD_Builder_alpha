# TD Assistant Unified KB + Builder Tool Contract

This folder defines the TD assistant "contract": skills, prompts, schemas, and workflows used with the unified knowledge base in `C:\TD_Projects\kb_pipeline`.

## Runtime paths (defaults)
- TouchDesigner bin: `C:\Program Files\Derivative\TouchDesigner\bin`
  - `toeexpand.exe`
  - `toecollapse.exe`
- Unified KB:
  - Graph: `C:\TD_Projects\kb_pipeline\graph\td_knowledge_graph_simple.json`
  - Vector (numpy): `C:\TD_Projects\kb_pipeline\vector_db` (`vector_index.json` + `embeddings.npy`)
  - Vector (Chroma, optional): `C:\TD_Projects\kb_pipeline\vector_db_chroma` (collection `td_unified`)
  - Operator index: `C:\TD_Projects\kb_pipeline\index\operator_index.json`

## Non-negotiables
- Do not invent TouchDesigner parameter names or operator types; all outputs must be grounded by evidence (docs, snippets, palette).
- Lossless JSON and Semantic JSON formats are stable contracts; do not mutate their schemas.
- Any "deliver a project file" workflow MUST end with a successful `toecollapse.exe` producing a loadable `.toe`/`.tox`.
- Any "generate python" workflow MUST generate a Text DAT script that is runnable in TouchDesigner and produces the described network.

## Conversion Operators (CRITICAL)
Operators that convert between data families (`*to*` pattern) require **explicit source parameters** - wire connections alone do NOT configure them.

| Operator | Required Param | Example |
|----------|---------------|---------|
| `soptoCHOP` | `sop` | `"sop": "sphere1"` or `"sop": "op('sphere1')"` |
| `choptoTOP` | `chop` | `"chop": "null1"` + optionally `dataformat`, `rchan`, `gchan`, `bchan` |
| `datToCHOP` | `dat` | `"dat": "table1"` |
| `topToCHOP` | `top` | `"top": "moviefilein1"` |
| `choptoSOP` | `chop` | `"chop": "noise1"` |
| `choptoDAT` | `chop` | `"chop": "null1"` |
| `soptoDAT` | `sop` | `"sop": "grid1"` |

**Before using any conversion operator**: Query `td_assistant` for the operator snippet to learn required parameters and see real usage examples.

## Single-entrypoint (recommended)
The assistant should expose a single MCP tool (or one primary tool) that can:
- Retrieve evidence (graph + vector DB)
- Produce structured plans (`TDNetworkSpec`)
- Produce build artifacts (expanded `.toe.dir` + `.toc`, or TD Text DAT python)
- Validate outputs (expand/collapse sanity checks)

See `workflows/` for process contracts and `schemas/` for request/response formats.
