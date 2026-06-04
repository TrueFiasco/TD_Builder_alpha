# p02_heart_v2 - plan

## Changes vs p01 (reference-driven)
- Myocardium: procedural fbm mottling + micro normal-relief; two domain-warped branching vessel
  networks painted on the surface (shading only, not displaced geometry): coronary arteries (red,
  oxygenated) and coronary veins (blue, deoxygenated).
- Oxygenation color split by anatomy: aorta + pulmonary veins = id2 red (oxygenated);
  pulmonary trunk + SVC + IVC = id3 blue (deoxygenated). Added aortic-arch branches, pulmonary
  bifurcation, IVC, pulmonary veins, and a left auricle bump for silhouette.
- Functioning valves: per-valve aperture from heart_phase. systole window ~ph[0.15,0.45];
  AV (mitral/tricuspid) open in diastole (1-sys), semilunar (aortic/pulmonary) open in systole.
  Leaflet = annular membrane disc whose inner hole = aperture*ringR (0 sealed, 1 open ring).
- Studio: bright near-white sweep background + ground plane (y=-1.5) catching a soft contact shadow.
- LFO CHOP 'lfo1' -> heart_phase. wavetype=ramp, amp=0.5, offset=0.5 (=> clean 0..1 per cycle),
  frequency=1.1 Hz (~66 bpm). Bound via parameter EXPRESSION op('lfo1')['chan1'].

## Build findings (this MCP/TD build)
- LFO waveform parameter is 'wavetype' (NOT 'type').
- ParMode is not exposed as td.ParMode / tdu.ParMode / bare ParMode in execute_python_script.
  Workaround: PM = type(par.mode); par.mode = PM.EXPRESSION / PM.CONSTANT.
- First cook reported ~797 ms = one-time SHADER COMPILE; steady-state CPU dispatch ~0.2 ms.
  (GPU pixel cost not captured by cookTime; heavy per-pixel fbm is the main GPU expense.)

## Known gaps vs reference
- Coronary vessels are denser/more marbled than the reference's sparse discrete navy coronaries.
- Cutaway interior reads as dark voids (concave chamber interiors are unlit); valves work but the
  cutaway lighting is crude. Vessels are painted, not raised tube geometry.
