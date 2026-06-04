# p01_beating_heart_glsltop - result

fix_iterations: 4

## Compile
Vertex: Compiled Successfully | Pixel: Compiled Successfully | warnings(): empty | errors(): empty | cook errors: none | python exceptions: none

## Render sanity (1280x1280; heart_phase=0.34, beat_amplitude=1.0; no clip; 3/4 cam, FOV 38)
pixel mean=0.34283, std=0.16072 (min 0.082, max 0.945) -> NOT flat; structure present.

## Self-assessment
- Builds and renders live; recognizable heart morphology + 3-point studio lighting.
- NOT photorealistic (smooth clay look) and NOT anatomically exact - SDF approximation.
- Cutaway not shown in hero frame (clip disabled); set e.g. clip_z=(-2,0) to slice.
- Valve leaflets are static annuli (no open/close animation).
- Fix-iterations: (1-2) MCP exec-scope quirks in my setup scripts; (3) Constants page won't declare floats; (4) UI pages don't auto-declare uniforms -> declarations restored in source.

HUMAN VERDICT: ____
