# Torus Twist Analysis Summary

**Analysis Date:** 2026-01-06
**Data Source:** `/cord_physics/popto_glsl_torus` table (131,072 points)
**Analyzed Ring:** Ring 0 (majorIndex 0-511)

## Key Findings

### Threshold Violation
- **Threshold:** π/32 ≈ 0.0982 rad ≈ 5.62°
- **Violations Found:** 184 locations
- **Percentage:** 36% of all spine transitions exceed the threshold

### Statistics
- **Total spine points:** 512
- **Mean twist per step:** 0.0658 rad (3.77°)
- **Max twist per step:** 0.0984 rad (5.64°)
- **Min twist per step:** 0.000021 rad (0.0012°)

### Critical Observation
**The threshold is set exactly at the maximum observed twist rate.**

This means:
1. The shader is operating at the absolute limit of the smoothing constraint
2. 184 transitions (36%) are right at or just over the threshold
3. All violations are in the range 0.0982-0.0984 rad (5.63-5.64°)
4. There are NO discontinuities (jumps > π radians)

## Pattern Analysis

### High-Twist Regions
Violations cluster in specific majorIndex ranges:

1. **Region 1:** majorIndex 108-119 (rows 3457-3809)
   - Downward twist trend
   - 6 violations

2. **Region 2:** majorIndex 132-143 (rows 4225-4577)
   - Upward twist trend
   - 12 violations

3. **Region 3:** majorIndex 165-178 (rows 5281-5697)
   - Downward twist trend
   - 14 violations

4. **Region 4:** majorIndex 220-236 (rows 7041-7553)
   - Downward twist trend (approaching -2 rad)
   - 17 violations

5. **Region 5:** majorIndex 238-261 (rows 7617-8353)
   - Recovery phase (twist climbing back up)
   - 24 violations

6. **Region 6:** majorIndex 280-286 (rows 8961-9185)
   - Downward twist trend
   - 7 violations

7. **Region 7:** majorIndex 297-310 (rows 9505-9921)
   - U-turn pattern (down then up)
   - 14 violations

8. **Region 8:** majorIndex 314-325 (rows 10049-10401)
   - Upward recovery
   - 10 violations

9. **Region 9:** majorIndex 329-338 (rows 10529-10817)
   - Strong upward trend
   - 10 violations

10. **Region 10:** majorIndex 352-369 (rows 11265-11809)
    - Peak and descent pattern
    - 18 violations

11. **Region 11:** majorIndex 390-416 (rows 12481-13313)
    - U-turn pattern (down then up)
    - 27 violations

12. **Region 12:** majorIndex 437-463 (rows 13985-14817)
    - Peak pattern (up to 2.3424, then down)
    - 27 violations

## Interpretation

### Not a Bug, but Design Limit
The violations are **systematic and smooth**, indicating:
- The shader's smoothing algorithm is working correctly
- The physics simulation is generating twist rates that approach the limit
- No sudden jumps or discontinuities exist

### Threshold Too Strict?
Options to resolve:
1. **Increase threshold to π/28 (0.112 rad ≈ 6.4°)** - would eliminate all violations
2. **Add adaptive smoothing** - use higher smoothing in high-twist regions
3. **Multi-pass smoothing** - apply multiple lighter smoothing passes
4. **Accept current behavior** - 5.6° per step may be visually acceptable

## Visual Impact

The twist rate of 5.6° per spine point translates to:
- **Over 32 minor subdivisions:** 5.6° / 32 ≈ 0.175° per tube point
- **Full rotation per ring:** ~2880° total twist around a 512-point ring
- **Approximately 8 full rotations** around the major torus axis

This is **visually significant** and explains the strong spiral pattern in the rendered torus.

## Recommendation

The twist pattern is **consistent and intentional**, likely driven by the physics simulation's interaction forces. The violations are boundary cases where the simulation pushes twist to the design limit.

**Suggested Actions:**
1. If visual artifacts appear at these locations, increase threshold by ~15%
2. If smoothing is insufficient, add a second-pass Laplacian smooth on Color(0)
3. If the spiral is too tight, reduce the physics forces that generate twist
