# Workflow: build_project

Build a working TouchDesigner project file or an in-TD script from the unified knowledge base.

## Defaults
- TouchDesigner bin: `C:\Program Files\Derivative\TouchDesigner\bin`
  - `toeexpand.exe`
  - `toecollapse.exe`

## Inputs
- User goal (natural language)
- Build mode:
  - `deliver_toe`: produce a `.toe` (requires `builder_json`)
  - `deliver_tox`: produce a `.tox` (requires `builder_json`)
  - `deliver_python`: produce Text DAT python (requires `builder_python`)
  - Optionally: both deliver_toe + deliver_python

## Steps (contract)
1) Retrieve evidence from unified KB
   - Search vector DB for relevant operator summaries and example patterns.
   - Query graph for example networks and operator relationships.
2) Synthesize plan
   - Produce `TDNetworkSpec` grounded by evidence.
   - Choose a template (if producing `.toe/.tox`).
3) Build
   - If `deliver_python`:
     - Emit `TDTextDatScript` (see `skills/builder_python.md`)
   - If `deliver_toe` or `deliver_tox`:
     - Expand template (or start from an existing expanded dir).
     - Apply changes using the lossless JSON intermediate when possible.
     - Produce updated expanded dir + `.toc`.
     - Collapse using `toecollapse.exe <base_name>` (NOT the directory).
4) Validate
   - Expand the output `.toe/.tox` again with `toeexpand.exe`.
   - Structural checks:
     - required operators exist
     - required connections exist
     - key parameters are set
5) Return deliverables
   - File paths + commands used
   - Evidence pack (docs + examples used)

## Failure handling
- If collapse fails: keep expanded output and `.toc` for debugging; report exact stderr.
- If parameters invalid: remove only the invalid assignments and retry; never invent replacements.
