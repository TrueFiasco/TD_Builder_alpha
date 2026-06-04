# Example: Identifying Bottlenecks in a TD Network

## Scenario

User has uploaded a .toe file and reports: "My project is running slow, around 15fps when it should be 60fps"

## Analysis Workflow

### Step 1: Expand and Explore Structure

```bash
# Expand the network
expand_toe_file("C:/TD_Projects/user_project.toe")

# List top-level
list_directory("C:/TD_Projects/user_project.toe.dir")
```

**Result:**
```
Found:
- project1/ (main container)
- 15 TOP operators
- 8 CHOP operators
- 3 COMP operators
```

### Step 2: Check TOP Resolutions

**Parse each TOP's .parm file looking for resolution settings:**

```
moviefilein1.parm:
resolution 0 3840  # 4K width!
resolution 1 2160  # 4K height!

blur1.parm:
resolution 0 3840  # Also 4K
resolution 1 2160

level1.parm:
resolution 0 3840  # Also 4K
resolution 1 2160
```

**🚨 RED FLAG:** Multiple 4K TOPs detected!

### Step 3: Identify Expensive Operators

**From operator types in .n files:**

```
blur1.n: TOP:blur          # Expensive!
blur2.n: TOP:blur          # Expensive!
edge1.n: TOP:edge          # Expensive!
convolve1.n: TOP:convolve  # Very expensive!
```

**🚨 RED FLAG:** 4 expensive image processing operators in chain

### Step 4: Calculate Performance Impact

**From operator documentation:**

- **Blur TOP at 4K:** ~8ms per frame
- **Edge TOP at 4K:** ~6ms per frame  
- **Convolve TOP at 4K:** ~12ms per frame

**Total estimated cook time:** ~40ms per frame (= 25fps max)

**With 4 expensive ops:** Could be 60-80ms (= 12-16fps) ✅ Matches user's 15fps!

### Step 5: Generate Recommendations

## Bottleneck Analysis

**Primary Issues:**

1. **4K Resolution Throughout Chain**
   - **Impact:** Massive - 4x more pixels than 1080p
   - **Current:** 3840x2160 = 8.3M pixels
   - **Should be:** 1920x1080 = 2.1M pixels
   - **Performance gain:** ~4x faster

2. **Multiple Expensive Operators in Series**
   - Blur → Blur → Edge → Convolve = Compounded cost
   - Each operator at 4K takes 6-12ms
   - **Performance gain:** Consider alternatives or reduce quality

3. **No Optimization Null Operators**
   - Missing NULL TOPs after expensive operations
   - Can't cache results
   - **Performance gain:** Add NULLs to enable caching

## Specific Recommendations

### Recommendation 1: Reduce Resolution (CRITICAL)
```
Change all TOP resolutions:
FROM: 3840x2160 (4K)
TO: 1920x1080 (1080p)

Expected improvement: 15fps → 60fps
Effort: Low (change resolution parameters)
Trade-off: Slightly less detail (usually imperceptible)
```

**How to implement:**
```python
# For each TOP in chain
op.par.resolution1 = 1920
op.par.resolution2 = 1080
```

### Recommendation 2: Consolidate Blur Operations
```
Current: blur1 → blur2 (two passes)
Better: Single blur with higher radius

Expected improvement: Additional 5-10fps
Effort: Low (remove one operator)
Trade-off: Slightly different blur characteristics
```

### Recommendation 3: Consider Edge Alternative
```
Current: Edge TOP (expensive)
Alternative: Sobel TOP (faster edge detection)

Expected improvement: 3-5fps
Effort: Low (replace operator)
Trade-off: Different edge detection algorithm
```

### Recommendation 4: Add Cache Points
```
Add NULL TOPs after:
- blur2 (before edge)
- edge1 (before convolve)
- convolve1 (after expensive chain)

Expected improvement: Smoother playback, better scrubbing
Effort: Low (insert NULL operators)
Trade-off: Slightly more memory usage
```

### Recommendation 5: Consider Time Slicing
```
If real-time not required:
- Set expensive COMPs to Time Slice mode
- Cook only when needed

Expected improvement: Varies by usage
Effort: Medium (restructure if needed)
Trade-off: Not suitable for real-time performance
```

## Priority Implementation Order

**Phase 1 (Do First - Biggest Impact):**
1. ✅ Change resolution to 1080p
2. ✅ Remove duplicate blur

**Expected result:** 15fps → 55-60fps

**Phase 2 (If Still Needed):**
3. ✅ Add NULL operators for caching
4. ✅ Consider Edge → Sobel replacement

**Expected result:** 60fps stable with headroom

**Phase 3 (Polish):**
5. ✅ Organize network layout
6. ✅ Add performance monitoring

## Verification Steps

After implementing changes:

1. **Check frame rate in Performance Monitor**
   - Target: Steady 60fps
   - Cook time: <16ms per frame

2. **Verify visual quality**
   - Compare 4K vs 1080p output
   - Ensure acceptable quality

3. **Test under load**
   - Multiple effects enabled
   - Ensure stable performance

## Summary

**Root Cause:** 4K resolution throughout expensive operator chain

**Solution:** Reduce to 1080p + optimize operator chain

**Expected Outcome:** 15fps → 60fps (4x improvement)

**Time to Implement:** ~15 minutes

**Confidence:** Very High (textbook performance issue)

---

**Analysis completed using TD Network Analysis Skill**  
**Operator documentation referenced for performance characteristics**
