# TouchBuilder Session Report (Codex)

Date: 2025-12-30
Participants: Jake, Codex
Project: C:\TD_Projects\META_AGENTIC_TOOL\output\tunnel_demo
TD WebServer: http://127.0.0.1:9981/api/td/server/exec

Goal
- Audio-reactive GLSL tunnel demo (TouchDesigner Free, 1280x720 @ 60fps)
- Modular .tox: audio_analysis, tunnel_shader, post_fx, control_ui, output
- Multiple tunnel scenes (c/d/e) sharing a single tunnel path and secondary tube
- Camera blend between main tube and secondary tube, plus fog control

Current State
- Using palette Audio Analysis. audio_analysis/out1 channels:
  energy, low, mid, high, kick, snare, rythm
- control_ui custom parameters (uppercase):
  Audiogain, Energygain, Trail, Glow, Speed, Twist, Lookahead, Camblend, Fog
- control_ui/out1 channels:
  audio_gain, energy_gain, trail, glow, speed, twist, lookahead, camblend, fog

Shaders
Files:
- shaders/tunnel_c_organic.glsl
- shaders/tunnel_d_scifi.glsl
- shaders/tunnel_e_aaa.glsl

Uniforms (all three):
- uTime, uAudio (low/mid/high), uEnergy, uTwist, uLook, uCamBlend, uFog, uCamOffset

Path + Secondary Tube
- path() and secondaryOffset() use noise2Path so c/d/e share the same tube layout
- secondary offset is rotated by path angle only (NOT twist) to keep cam alignment
- twist still affects wall deformation, not secondary tube placement

Debug State
- DEBUG_UV is currently enabled in c/d/e (shows U = angle, V = z)
- User requested solid color test; patch attempt was rejected, so not applied yet

Known Issues
- Strong banding artifacts remain; user suspects fog involvement
- Banding still visible in DEBUG_UV view; different fog values affect bands

Last Changes Applied
- Removed per-pixel jitter/refine; raymarch loop is 72 steps
- Safer secondary trench: ds += trench * r2 * 0.25, smin k = 0.22
- Camera blend now stable with twist != 0

Next Steps
1) Switch DEBUG_UV to solid color (or use a param toggle) to isolate fog vs geometry.
2) If fog is the cause, add subtle fog dithering or noise to the fog factor.
3) If geometry is the cause, reduce high-frequency ringNoise or add smoother SDF.
4) Return DEBUG_UV to 0 after diagnosis.

Reload / Save Script (TD exec)
- Script used:
  ops = ["/project1/tunnel_shader_c", "/project1/tunnel_shader_d", "/project1/tunnel_shader_e"]
  for path in ops:
      comp = op(path)
      glsl = comp.op("tunnel_glsl")
      glsl.par.reinit.pulse() or glsl.par.reload.pulse()
      comp.saveExternalTox()

Notes
- control_ui external tox edits required temporarily disabling enableExternalTox;
  re-enabled after saving.
