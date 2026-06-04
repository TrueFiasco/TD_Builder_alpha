# Codex Init - TouchBuilder

## Purpose
This file is the boot guide for Codex to use the TouchBuilder system inside
C:\TD_Projects\META_AGENTIC_TOOL. It is written so that if this is the only
file loaded, Codex can still:
- Understand available tools and experts
- Choose the right workflow (offline by default, live optional)
- Build a strong, creative TouchDesigner project end-to-end
- Avoid known pitfalls and apply workarounds

Primary interface: Claude Desktop MCP (preferred). CLI is a fallback for
batch work or scripting.


## Environment Assumptions
- Repo root: C:\TD_Projects\META_AGENTIC_TOOL
- TouchDesigner: C:\Program Files\Derivative\TouchDesigner.2025.31760
- TD version: 2025.31760
- TD WebServer port: 9981 (optional, for live mode)
- Anthropic API key is set in the environment used by Claude Desktop

Default strategy and KB mode:
- Strategy: V2 (balanced quality vs cost)
- Expertise mode: compact=true (default for KB queries)


## MCP Tool Map (36 tools)

### Core Tools (17)
| Tool                      | When to use | Output |
|---------------------------|-------------|--------|
| spawn_engineer            | Knowledge extraction (types: snippet_extractor, workflow_analyzer, concept_generator, knowledge_validator, data_source_auditor) | JSON |
| spawn_expert              | Expert generation (design, GLSL, python, critique) | YAML output |
| hybrid_search             | Open-ended TD questions | Ranked docs + notes |
| get_operator_info         | Exact operator details | Operator spec |
| query_graph               | Relationships, params, family, related ops | Graph results |
| list_pop_operators        | POP operator list | Names |
| find_operator_examples    | Real usage networks for an operator | Examples |
| find_operator_combination | Multi-op usage examples | Examples |
| find_parameter_usage      | Valid parameter values | Usage stats |
| find_similar_networks     | Pattern-similar networks | Examples |
| get_parameter_detail      | Full param description + options | Param spec |
| get_network_patterns      | Common chains and best practices | Patterns |
| td_build_project          | Build .tox from JSON | .tox output |
| td_validate               | 5-stage validation pipeline | Validation report |
| td_convert                | Format conversion (builder/extended/canonical) | Converted JSON |
| td_compact_expertise      | Compact event log to YAML | YAML |
| get_expert_prompt         | Inspect expert prompt text | Prompt text |

### TD Live Tools (19) - require TD running with WebServer
| Tool                      | When to use | Output |
|---------------------------|-------------|--------|
| capture_top_output        | Visual proof of TOP output | Image |
| get_top_info              | Resolution, format, GPU info | Metadata |
| get_cook_errors           | All cook errors | Errors |
| get_error_summary         | Error counts by severity | Summary |
| capture_network_layout    | Network topology snapshot | Image |
| get_python_exceptions     | Python exceptions | Errors |
| capture_op_viewer         | Capture any operator | Image |
| get_td_info               | Check TD connectivity | Server info |
| get_td_nodes              | List nodes under path | Nodes |
| get_td_node_parameters    | Inspect params live | Params |
| create_td_node            | Create operator | Node info |
| update_td_node_parameters | Update params live | Status |
| delete_td_node            | Delete operator | Status |
| execute_python_script     | Run Python in TD | Output |
| exec_node_method          | Call node method | Result |
| get_td_node_errors        | Per-node error check | Errors |
| get_td_classes            | List TD Python classes | Class list |
| get_td_class_details      | Class details | Help data |
| get_td_module_help        | Python help() for module | Help text |


## Expert Roster (12)
Use spawn_expert to call these experts. They output YAML.

| Expert                  | When to use |
|-------------------------|-------------|
| td_designer             | Network design and operator graph |
| network_builder         | JSON finalization, buildability checks |
| td_glsl_expert          | GLSL shader code and uniforms |
| td_python_expert        | Python scripts for DAT/CHOP automation |
| ui_expert               | UI/control panel design |
| critic                  | Quality review and score |
| cg_expert               | Technical rendering strategy |
| creative_expert         | Visual style, mood, palette, motion |
| creative_orchestrator   | Multi-expert coordination |
| format_reverse_engineer | .toe/.tox format research |
| summary_generator       | Documentation output |


## Expertise Files (19)
The KB is in meta_agentic/expertise. Use compact mode by default.

Key files:
- td_operators, td_parameters, td_glsl, td_python
- cg_concepts, creative_vision, ui_design_patterns
- palette_expertise, palette_semantic_catalog
- td_network_patterns, td_network_building
- critique_patterns, orchestrator_patterns
- collaborative_workflow, prebuilt_solution_expert
- td_problems, td_file_formats

Compact vs full:
- compact=true: fast, low-context, default
- compact=false: deep-dive on specific params only


## Default Workflow (Offline)
Use this when TD is not running or live verification is not required.

1) Intake and clarify
- Ask for resolution, fps, audio source, performance constraints.
- Confirm whether palette components are allowed.

2) KB pre-query (compact mode)
- hybrid_search for overall approach
- get_operator_info for exact operator specs
- get_network_patterns for known chains
- find_parameter_usage and get_parameter_detail for tricky params

3) Spawn experts (as needed)
- creative_expert if the user wants strong art direction
- cg_expert for technical approach (especially for GLSL or 3D)
- td_designer to produce the network design JSON
- td_glsl_expert to author or review GLSL code
- td_python_expert if scripting is needed
- ui_expert if a control panel is requested
- critic for quality validation
- network_builder to finalize JSON

4) Validate
- Run td_validate on the JSON before building.

5) Build
- Run td_build_project to produce a .tox.
- If a .toe is required, use td_convert or the configured build pipeline.

6) Summarize
- summary_generator to create human-friendly documentation.


## Live Mode Workflow (Optional)
Requires TD running and mcp_webserver_base.tox loaded.

1) Check connection
- get_td_info

2) Build or load network
- Use td_build_project for .tox or build live with create_td_node.

3) Configure and validate
- update_td_node_parameters for known-safe params
- execute_python_script for complex ops or data table filling
- get_error_summary and get_cook_errors

4) Visual proof
- capture_top_output or capture_op_viewer
- capture_network_layout for structure proof


## Known Limitations

### All Major Bugs Fixed (as of Dec 2024)
The following issues have been resolved and require no workarounds:
- Container children and internal connections (BUG-002, BUG-011)
- Table DAT data population (BUG-012)
- Conversion operator parameters (BUG-013)
- COMP input wiring (BUG-003)
- Parameter name mapping (BUG-001)
- Palette embedding (BUG-004)
- Format converter nodes vs operators key (BUG-020)
- get_operator_info missing fields (BUG-019)

### Minor Caveats (No Blockers)
- BASIC mode .parm format: prefer LOSSLESS mode for best round-trip fidelity
- Composite TOP operand: use string names ("add", "multiply") not integers
- Some menu params need integers, others strings - KB documents which

### Deferred (Low Priority)
- Performance profiling for very large networks (1000+ ops)


## Epic Demo Target (Default Showcase)
Audio-reactive GLSL tunnel (2D/3D hybrid) at 1920x1080, 60 fps.

Goals:
- Show GLSL uniform wiring from CHOPs
- Use audio analysis (palette component)
- Use feedback + post for motion trails
- Keep operator count reasonable (8-15 ops)

Suggested network structure (conceptual):
- /project1
  - /audio (container)
    - audioDeviceIn CHOP
    - audioAnalysis palette (or audioSpect + math + filter)
    - select CHOPs: bass, mid, high, energy
  - /visual (container)
    - GLSL TOP (tunnel shader)
    - feedback TOP
    - level TOP (trail decay)
    - composite TOP (optional glow)
    - null TOP (out)
  - /output
    - out TOP

GLSL essentials:
- Use uTime and uAudio uniforms
- Keep shader stable for 60 fps
- If no inputs are connected, avoid uTD2DInfos access


## Validation Checklist
Offline:
- td_validate passes all 5 stages
- operator types resolved and families explicit
- parameter values match KB usage

Live:
- get_error_summary shows no errors
- capture_top_output looks correct at 1080p


## Intake Questions to Ask the User
- What is the audio source? (mic, file, line-in)
- Desired resolution and fps?
- Any GPU or performance limits?
- Do you want a control UI or minimal network?
- Do you want palette components or only native ops?
- Any style references, color palette, or mood keywords?


## Operational Defaults
- Strategy: V2
- Expertise: compact=true
- Offline-first; live mode only when needed
- Use critic before final build
- Prefer explicit families for ambiguous operators


## Fallback Plan (No API or Live TD)
- Use KB tools only (no expert spawning)
- Manually construct JSON by following td_network_patterns
- Validate with td_validate
- Build with td_build_project


## Notes for Self
- Always query KB before inventing params or operators
- If a parameter is unclear, use find_parameter_usage + get_parameter_detail
- If a build fails, check td_validate output before editing JSON
- Use summary_generator to produce a clear handoff for the user

## Recent Session Notes (2025-12-30)
- Session report: C:\TD_Projects\META_AGENTIC_TOOL\SESSION_REPORT.md
- Project root: C:\TD_Projects\META_AGENTIC_TOOL\output\tunnel_demo
- TD live control via WebServer /api/td/server/exec (PowerShell Invoke-RestMethod); TD is currently closed so the server is offline
- Shaders updated: shaders/tunnel_c_organic.glsl, tunnel_d_scifi.glsl, tunnel_e_aaa.glsl
- control_ui params: Audiogain, Energygain, Trail, Glow, Speed, Twist, Lookahead, Camblend, Fog
- control_ui/out1 outputs: audio_gain, energy_gain, trail, glow, speed, twist, lookahead, camblend, fog
- Palette Audio Analysis provides: energy, low, mid, high, kick, snare, rythm
- DEBUG_UV macro is set to 0 in tunnel_c/d/e (use 1 for UV/banding debug)
- Current focus: tunnel_shader_d (inside/outside), secondary tube flipping, and camera path alignment under twist
- tunnel_d_scifi.glsl changes:
  - Added forward declaration for pathDeriv to fix compile error
  - Added pathFrame() (noise-free) and use it for pathDeriv for a more stable frame
  - tunnelCoords uses world XY (no frame rotation) with twist applied in qTwist
  - Secondary tube uses twist-rotated offset and qTwist for distance
  - Reduced smooth union strength (smin k=0.06)
  - Normal flip uses dot(n, rd) instead of inside flag
  - SecondaryOffset noise slowed (lower freq, smaller angle variance)
- Pending: camera roll fix for twist (rotate right/up by twistCam) added to file but not pushed to TD yet
- Text DATs are not syncfile: reload by copying file contents into /project1/tunnel_shader_d/tunnel_glsl and /project1/tunnel_shader_d1/tunnel_glsl, then toggle glsl1.pixeldat to recompile
- /project1/tunnel_shader_d1 (outside) sometimes disappears; verify /project1/tunnel_shader_d1/out1 exists before capture
