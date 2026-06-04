# p03_heart_v3 - result

fix_iterations: 4 (2 build-script placeholder slips; LFO wavetype; then 3 vessel/lighting tuning passes - shader compiled every attempt)

## Compile
Vertex + Pixel Compiled Successfully | warnings/errors empty | cook errors none | python exc none

## Performance
Shipped 1280^2. Estimated >=40 fps at 1280, ~76 fps at 1024, ~51 fps at 1536 (GPU-dependent;
one-time shader compile ~0.8s is separate). Meets the >=30fps requirement with margin.

## Renders
output.png (hero, LFO phase, std 0.197); cutaway_systole.png + cutaway_diastole.png
(lit interior now, valves phase-driven).

## Self-assessment
- Best of the three: textured myocardium, oxy(red)/deoxy(blue) great vessels, directional coronaries,
  studio backdrop + contact shadow, functioning valves, LFO-driven, >=30fps.
- Residual gap vs reference: surface coronary tree not as crisp/prominent (painted-vessel limit);
  small dark apex tip; not photoreal/medically exact.

HUMAN VERDICT: ____
