# ORCHESTRATOR LOG - Cliff's World Build Session

## Session Started: 2024-12-29

---

## SYSTEM UNDERSTANDING

### Available MCP Tools (36 Total)

#### Knowledge & Search (9 tools)
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `hybrid_search` | Semantic + graph search | Open-ended questions about TD |
| `get_operator_info` | Full operator details | Need parameter specs |
| `query_graph` | Graph queries (params, related, family) | Exploring operator relationships |
| `list_pop_operators` | POP operator listing | Particle system work |
| `find_operator_examples` | Real usage examples | How do others use this op? |
| `find_operator_combination` | Multi-op examples | What connects well together? |
| `find_parameter_usage` | Parameter value mining | What values work for this param? |
| `find_similar_networks` | Pattern matching | Alternative approaches |
| `get_network_patterns` | Common chains | Best practices |

#### Building & Validation (5 tools)
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `td_build_project` | JSON → .toe/.tox | Final build step |
| `td_validate` | 5-stage validation | Before building |
| `td_convert` | Format conversion | Layer transitions |
| `td_compact_expertise` | Expertise log compaction | Workflow optimization |
| `get_parameter_detail` | Deep param info | Need options/ranges |

#### Agents & Experts (3 tools)
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `spawn_expert` | 11 expert types | Complex creative/technical work |
| `spawn_engineer` | 5 engineer types | Knowledge extraction |
| `get_expert_prompt` | Get expert instructions | Manual expert execution |

**Expert Types Available:**
- `td_designer` - Network specification
- `network_builder` - JSON finalizer
- `td_glsl_expert` - GLSL shader code
- `td_python_expert` - Python automation
- `ui_expert` - UI/control panels
- `critic` - Quality review
- `cg_expert` - Technical graphics
- `creative_expert` - Artistic vision
- `creative_orchestrator` - Multi-expert coordination
- `format_reverse_engineer` - File format expert
- `summary_generator` - Documentation

#### Visual Feedback (7 tools)
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `capture_top_output` | Screenshot TOP | Verify visual output |
| `get_top_info` | TOP metadata | Check resolution/format |
| `get_cook_errors` | All cook errors | Debugging |
| `get_error_summary` | Error counts by severity | Quick health check |
| `capture_network_layout` | Network topology | Verify structure |
| `get_python_exceptions` | Python errors | Script debugging |
| `capture_op_viewer` | Universal viewer | Any operator type |

#### TD Live CRUD (13 tools)
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `get_td_info` | Server info | Verify connection |
| `get_td_nodes` | List nodes | Navigate structure |
| `get_td_node_parameters` | Node params | Inspect live state |
| `create_td_node` | Create operator | Build in running TD |
| `update_td_node_parameters` | Update params | Modify live |
| `delete_td_node` | Delete operator | Cleanup |
| `execute_python_script` | Run Python | Complex operations |
| `exec_node_method` | Call node method | Specific actions |
| `get_td_node_errors` | Node errors | Per-node debugging |
| `get_td_classes` | TD Python classes | API exploration |
| `get_td_class_details` | Class details | API reference |
| `get_td_module_help` | Python help | Documentation |

---

## PROJECT: CLIFF'S WORLD - Multi-Scene Infinite Tunnel System

### Concept
A showcase demonstrating LLM-orchestrated TouchDesigner development:
- Multiple infinite tunnel scenes with shared camera/path control
- Seamless blending between visually distinct tunnels
- Audio-reactive using AA (audioAnalysis) palette component
- Concept-level parameters (mood, energy, chaos) instead of raw shader uniforms

### Why This Showcases LLM Capabilities
1. **GLSL Generation** - Custom shaders via td_glsl_expert
2. **Palette Integration** - Using audioAnalysis from palette
3. **Parameter Abstraction** - Concept→parameter mapping via expressions
4. **Scene Management** - Multiple coordinated scenes
5. **Visual Feedback Loop** - Capture/verify/iterate

### Architecture Vision
```
/project1 (Cliff's World)
├── /base_control
│   ├── constantCHOP (speed, time_scale)
│   ├── lfoCHOP (camera_path_phase)
│   └── audioAnalysis (palette) → energy, bass, mids, highs
│
├── /data_center
│   ├── selectCHOP (concept_mood: 0-1)
│   ├── selectCHOP (concept_energy: 0-1, from audio)
│   ├── selectCHOP (concept_chaos: 0-1)
│   └── mathCHOP (derived parameters)
│
├── /tunnel_scene_01 (Geometric/Crystal)
│   ├── glslTOP (tunnel_geometry_shader)
│   ├── feedbackTOP
│   └── nullTOP (output)
│
├── /tunnel_scene_02 (Organic/Fluid)
│   ├── glslTOP (tunnel_organic_shader)
│   ├── feedbackTOP
│   └── nullTOP (output)
│
├── /tunnel_scene_03 (Particle/Starfield)
│   ├── glslTOP (tunnel_particle_shader)
│   └── nullTOP (output)
│
├── /scene_blender
│   ├── switchTOP or compositeTOP
│   ├── crossfade logic
│   └── nullTOP (final_output)
│
└── /output
    └── outTOP
```

---

## SESSION LOG

### Entry 1: Initial Research Complete
- Explored META_AGENTIC_TOOL structure
- Identified all 36 MCP tools
- Understood workflow: KB query → Expert spawn → Build → TD Live verify
- Project location: C:\TD_Projects\META_AGENTIC_TOOL\output\cliffs world

### Entry 2: Connection Test - SUCCESS
- [x] Test get_td_info: TD 2025.31760 running
- [x] WebServer on port 9981 responding
- [x] Project has: /project1 (empty), /mcp_webserver_base

### Entry 3: audioAnalysis Palette Research
- Located in `data/palette_lossless/audioAnalysis.json.gz`
- 1216 operators (complex component)
- Key outputs: addLow, addMid, addHigh, Kickdrum, Snaredrum, Rythm
- Decision: Will import as .tox rather than recreating

### Entry 4: Architecture Design

**Simplified MVP Architecture:**
```
/project1
├── /control (containerCOMP)
│   ├── constantCHOP "master_speed" (0.1-2.0)
│   ├── constantCHOP "tunnel_depth"
│   ├── constantCHOP "scene_select" (0, 1, 2)
│   └── lfoCHOP "time_driver"
│
├── /audio (containerCOMP)
│   ├── audiodeviceinCHOP or audiofileinCHOP
│   ├── audiospectrum or custom analysis
│   └── selectCHOP outputs: bass, mids, highs, energy
│
├── /tunnels (containerCOMP)
│   ├── /scene1 (containerCOMP) - Geometric
│   │   ├── glslTOP "tunnel_geo"
│   │   └── nullTOP "out"
│   ├── /scene2 (containerCOMP) - Organic
│   │   ├── glslTOP "tunnel_organic"
│   │   └── nullTOP "out"
│   └── /scene3 (containerCOMP) - Starfield
│       ├── glslTOP "tunnel_stars"
│       └── nullTOP "out"
│
├── /blend (containerCOMP)
│   ├── switchTOP (selects scenes)
│   ├── feedbackTOP (optional trails)
│   └── nullTOP "final_out"
│
└── /output (containerCOMP)
    └── outTOP "display"
```

**Phase 1: Build Base Structure**
1. Create containers via API
2. Set up control CHOPs
3. Simple test shader to verify pipeline

**Phase 2: GLSL Tunnels**
- Delegate to td_glsl_expert for each tunnel style
- Each receives: time, speed, bass, mids, highs, energy

**Phase 3: Audio Integration**
- Import audioAnalysis or build simple analyzer
- Connect to tunnel parameters

**Phase 4: Scene Blending**
- switchTOP with blend
- Time-based or manual scene transitions

### Entry 5: Build Session Complete

**What Was Built:**
- 3 unique GLSL tunnel scenes (Geometric, Organic, Starfield)
- Audio-reactive uniforms (uAudio, uTime)
- Scene blending with selectTOPs and switchTOP
- Speed CHOP for smooth time control
- Auto-cycling LFO for demo mode

**Files Created:**
- tunnel_scene1_audio.jpg - Geometric tunnel (45KB)
- tunnel_scene2_audio.jpg - Organic tunnel (66KB)
- tunnel_scene3_audio.jpg - Starfield tunnel (86KB)
- tunnel_blended_hires.jpg - Final blended output (15KB)

**Key Learnings:**
1. Use selectTOP instead of direct null wiring for cross-container references
2. TD GLSL uses `uTDGeneral.time` but better to use custom `uTime` uniform
3. Speed CHOP provides smooth velocity without jumps when changing speed
4. Vec uniforms can have expression-driven values for dynamic input
5. TDOutputSwizzle() required at end of pixel shader
6. Error reporting can be stale - always test with capture

---

## LEARNINGS FOR TEAM

### For PETER (Prompts)
- Expert prompts are in `meta_agentic/experts/{name}/{phase}.md`
- Phases: plan, build, self_improve
- Blackboard sections critical for context passing
- **NEW**: GLSL shaders need `uniform vec4 uName;` declarations
- **NEW**: Always wrap output with `TDOutputSwizzle(vec4(col, 1.0))`
- **NEW**: Use `uTDGeneral.time` or custom `uTime` for animation

### For KYLE (KB)
- 3-layer KB: wiki docs + enriched + enhanced graph
- Compact mode saves context for large queries
- Parameter ground truth in enriched wiki
- **NEW**: audioAnalysis palette has 1216 operators - too complex for inline
- **NEW**: Palette location: `data/palette_lossless/audioAnalysis.json.gz`

### For QUEENIE (QA)
- Visual feedback tools available for verification
- Error summary gives quick health check
- Can capture any operator type with capture_op_viewer
- **NEW**: Test sequence: Create → Set params → Wire → Capture
- **NEW**: Error list can be stale - always verify with capture
- **NEW**: selectTOP is preferred over direct null wiring

### For TERRY (Tools)
- 36 tools now consolidated in single mcp_server.py
- TD Live tools require WebServer running
- Expert spawning needs anthropic API key
- **NEW**: API endpoints discovered:
  - `POST /api/nodes` - Create operator
  - `PATCH /api/nodes/detail` - Update parameters
  - `POST /api/td/server/exec` - Execute Python
  - `POST /api/feedback/capture/top` - Capture screenshot
- **NEW**: Use Python exec for complex wiring and expressions
- **NEW**: Some parameter updates fail via PATCH - use Python instead

---

## QUESTIONS FOR JAKE (To Ask Later)
1. Is audioAnalysis palette component already in the empty toe?
2. Preferred output resolution for final render?
3. Any specific audio source preference (file, mic, etc.)?

---

## TROUBLESHOOTING NOTES

### Issue 1: GLSL Shader Compile Errors
**Symptom**: "The GLSL Shader has compile errors" in error list
**Cause**: Wrong uniform names (e.g., `uTD2DInfos` doesn't exist)
**Solution**: Use `uTDGeneral.time` or custom uniforms via vec params

### Issue 2: Switch Not Receiving Inputs
**Symptom**: "Not enough sources specified" on switchTOP
**Cause**: Direct wiring from nullTOPs in other containers doesn't work
**Solution**: Use selectTOPs to reference cross-container operators

### Issue 3: Small Output Resolution
**Symptom**: Captured images are 256x256 instead of full res
**Cause**: Default resolution on new operators
**Solution**: Set `outputresolution: custom` and specify `resolutionw/h`

### Issue 4: Parameter Update Fails
**Symptom**: PATCH returns validation error
**Cause**: Some parameters (like `chop` reference) can't be set via REST
**Solution**: Use `POST /api/td/server/exec` with Python script

### Issue 5: Audio Reactivity Not Working
**Symptom**: Shader ignores audio input
**Cause**: Vec uniform not declared or CHOP expression not evaluating
**Solution**: Add `uniform vec4 uAudio;` to shader, verify CHOP has values

---

## SESSION SUMMARY

**Project**: Cliff's World - Multi-Scene Audio-Reactive Tunnel System
**Duration**: ~2 hours of iterative development
**Result**: Fully functional TD project with:
- 3 distinct GLSL tunnel scenes
- Audio-reactive shader uniforms
- Smooth scene blending
- Speed-controlled animation
- Auto-cycling demo mode

**What Made This Possible**:
1. TD Live Client providing real-time feedback
2. Python exec for complex operations
3. Iterative troubleshooting with capture verification
4. Jake's guidance on TD best practices (selectTOP, speed CHOP)

**Ready for Demo**: Yes - open in TD, enable audio input, watch scenes blend

