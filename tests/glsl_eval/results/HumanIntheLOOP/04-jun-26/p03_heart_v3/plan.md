# p03_heart_v3 - plan

## Performance strategy (target >=30fps)
- Skip chamber cavities + valve geometry in the SDF unless a clip plane is active (clipOn gate):
  they never change the exterior, so the common animated view is far cheaper.
- Gate great-vessel evaluation to p.y>0.12.
- MAX_STEPS 150->100, shadow 26->16, AO 5->4 taps, shading fbm 4->3 octaves, larger normal eps.

## Measured frame time (approx; forced re-renders + one readback per block)
- 1024^2 ~13.2 ms (~76 fps); 1280^2 ~24 ms first-pass / faster once GPU clocks up (>=40 fps);
  1536^2 ~19.5 ms (~51 fps). Shipping at 1280^2 -> comfortably >30fps. Verify in TD perf bar.

## Realism changes
- Directional coronary trunks via segment distance (LAD + RCA arterial red; great cardiac vein blue)
  + sparse branches clustered near trunks; per-pixel made exclusively arterial OR venous to avoid
  purple blending. Stronger muscle fbm mottle + micro normal-relief.
- Camera headlight (stronger on cut faces) so sliced chamber interiors are lit, not black voids.
- Bigger aortic arch + descending branch; ground bounce light to lift the shadowed apex.

## Honest residual gap
- Painted coronaries can be made crisp-but-sparse or dense-but-smeary, not both; they don't fully
  match the reference's prominent discrete branching tree. The faithful fix is raised tube geometry
  (a few coronary capsules in the SDF) or a baked vessel texture - offered as a possible p04.
