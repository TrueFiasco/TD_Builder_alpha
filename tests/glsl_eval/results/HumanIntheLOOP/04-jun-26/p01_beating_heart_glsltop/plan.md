# p01_beating_heart_glsltop - plan

## Expertise studied
get_expert_prompt(td_glsl_expert, build). Applied: standalone glslTOP -> uTDOutputInfo.res for aspect (NOT uTD2DInfos); pixel stage; code in Text DAT referenced by `pixeldat`; `out vec4 fragColor;` required.

## FINDING (deviation from the expertise)
The build prompt claims UI pages auto-inject `uniform` declarations and warns against declaring in both source and page. In 099.2025.32460 that is FALSE: the GLSL TOP does NOT auto-declare page uniforms. Pages only BIND VALUES BY NAME to uniforms declared in source. Omitting declarations gave 'heart_phase undeclared'. Fix: declare all uniforms in source; bind by name on the Vectors page. Constants page also did not declare a `uniform float`; scalars moved to Vectors page as vec4 (.x). seq numBlocks floor is 1, so Constants page left with one neutral '_unused' block.

## Operators / params
- textDAT shader_code (language=glsl): pixel shader.
- glslTOP glsl1: pixeldat=shader_code, outputresolution=custom 1280x1280.
  Vectors page (all uniform vec4, bound by name): vec0 clip_x, vec1 clip_y, vec2 clip_z (x=keepMin,y=keepMax; min>=max disables that axis), vec3 heart_xform (xyz rot rad, w scale), vec4 cam_xform (xyz orbit rad, w FOV deg), vec5 heart_phase(.x), vec6 beat_amplitude(.x).
- infoDAT glsl1_info (op=glsl1): compile log.

## Technique
Raymarched SDF: smin(LV+RV ellipsoids) tapered to apex capsule + 2 atria ellipsoids + great-vessel capsules (aorta arch, pulmonary trunk, SVC) + 4 valve-annulus tori. Chambers hollowed by subtracting inner ellipsoids with a preserved septum slab near x=0 so a clip plane shows a 4-chamber cross-section. Per-primitive material ids; clip cut-faces detected & shaded as muscle. 3-point studio light + soft shadow + AO + fresnel + ACES tonemap.
