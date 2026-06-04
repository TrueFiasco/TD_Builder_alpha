# Human-in-the-Loop test session — 04-jun-26

Session run by: Jake (Claude Desktop, td-builder-alpha, Mode 1)
Server: confirm `get_server_info` → script_path contains `TD_builder_alpha`, version `0.1.0-alpha`
TD: live on 127.0.0.1:9981, base `/test`

One row per test prompt. `renders(std)?` = pixel std of the output TOP
(std≈0 = flat/blank render → flag). `HUMAN VERDICT` filled by Jake after review.

| case_id | prompt (short) | build path | compiles? | renders(std)? | fix_iterations | self-assessment | HUMAN VERDICT |
|---|---|---|---|---|---|---|---|
| _example_ | red GLSL TOP | live | yes | yes (0.33) | 0 | looks correct | ____ |
| p01_beating_heart_glsltop | beating heart, controllable uniforms + xyz clip planes + studio render | live (execute_python_script) | yes | yes (std=0.161) | 4 | recognizable stylized heart; not photoreal/anatomically exact; cutaway not in hero frame | ____ |
| p02_heart_v2 | textured myocardium + coronary vessels (oxy/deoxy), functioning valves, LFO->heart_phase | live (execute_python_script) | yes | yes (std=0.201) | 2 | closer to ref; vessels too dense/marbled; cutaway interior unlit; valves+LFO working | ____ |
| p03_heart_v3 | best realistic heart >=30fps (perf-gated SDF, directional coronaries, lit cutaway) | live (execute_python_script) | yes | yes (std=0.197) | 4 | >=30fps at 1280; textured + oxy/deoxy + valves + LFO; coronary tree not as crisp as ref | ____ |
