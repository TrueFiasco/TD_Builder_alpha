# Alpha Demo Plan - December 19-20, 2024

## Goal
Deliver a working alpha demo of META_AGENTIC_TOOL that can:
1. Take a creative prompt
2. Run the expert workflow
3. Generate a working TOE file
4. Open and run in TouchDesigner

---

## Current State (End of Dec 18)

### Working
- [x] KB query system (278 palette, 600+ operators)
- [x] Blackboard state management
- [x] Expert prompts (8 experts)
- [x] V2-V6 workflow strategies
- [x] Subagent spawning via Claude Code
- [x] ToeBuilder file generation
- [x] Palette embedding from expanded .tox.dir
- [x] Teardrop TOE builds (137KB)
- [x] Critic review cycle

### Not Working
- [ ] Audio reactivity (expression paths wrong)
- [ ] Visual output (no display/window)
- [ ] Expression validation

---

## Day 1: December 19 (Today)

### Morning: Fix Critical Bugs

#### Task 1: Get Audio Channel Names (User)
**Owner**: Jake
**Time**: 15 min

1. Open `teardrop_full.toe` in TouchDesigner
2. Navigate to `/project1/audio/audioAnalysis`
3. Find the output null/out operator
4. Document actual channel names:
   - What is the path to output? `op('.../out1')` or different?
   - What channels exist? `low`, `mid`, `high`, `level`?
5. Share findings with Claude

#### Task 2: Fix Expression Paths (Claude)
**Owner**: Claude
**Depends on**: Task 1

Once channel names known:
1. Update `build_teardrop.py` with correct paths
2. Fix all expressions:
   - `noise1.amp` → correct audio reference
   - `hsv1.satmult` → correct audio reference
   - `bloom1.threshold` → correct audio reference
3. Rebuild TOE

#### Task 3: Add Display Output (Claude)
**Owner**: Claude
**Time**: 30 min

1. Add to build_teardrop.py:
   - `windowCOMP` for display
   - Connect `out1` → `window1`
   - Set window parameters (borderless, size)
2. Rebuild TOE

### Afternoon: Verify and Test

#### Task 4: Test in TouchDesigner (User)
**Owner**: Jake
**Time**: 30 min

1. Open rebuilt `teardrop_full.toe`
2. Verify:
   - [ ] Audio analysis receiving input
   - [ ] Visual chain rendering
   - [ ] Audio reactivity working
   - [ ] Window displaying output
3. Document any issues

#### Task 5: Fix Issues Found (Claude)
**Owner**: Claude
**Time**: Variable

Address any issues from Task 4 testing.

### Evening: Expand Visual Effects

#### Task 6: Add GPU Particles (Optional)
**Owner**: Claude
**Time**: 1-2 hours

If time permits:
1. Add particle system to teardrop
2. Map particle behavior to audio
3. Composite with existing visuals

#### Task 7: Add Glitch Effects (Optional)
**Owner**: Claude
**Time**: 30 min

If time permits:
1. Add RGB split effect
2. Map to high frequencies
3. Subtle, musical timing

---

## Day 2: December 20 (Demo Day)

### Morning: Polish

#### Task 8: End-to-End Test
**Owner**: Both
**Time**: 1 hour

1. Start from fresh prompt
2. Run full workflow
3. Generate new TOE
4. Verify it works

#### Task 9: Documentation
**Owner**: Claude
**Time**: 30 min

1. Update COORDINATION.md
2. Create demo script/guide
3. Document known limitations

### Afternoon: Demo

#### Demo Flow
1. Show the prompt input
2. Watch KB queries run
3. See expert agents spawn
4. Review critic approval
5. Generate TOE file
6. Open in TouchDesigner
7. Play Teardrop audio
8. Watch reactive visuals

---

## Blockers

### P0 (Must Fix)
| Issue | Owner | Status |
|-------|-------|--------|
| Audio channel names unknown | Jake | Pending |
| Expression paths wrong | Claude | Blocked on above |
| No display output | Claude | Ready to fix |

### P1 (Should Fix)
| Issue | Owner | Status |
|-------|-------|--------|
| Operator connections unverified | Claude | Pending |
| No error handling in builder | Claude | Pending |

### P2 (Nice to Have)
| Issue | Owner | Status |
|-------|-------|--------|
| GPU particles | Claude | Optional |
| Glitch effects | Claude | Optional |
| Multiple prompts tested | Both | Optional |

---

## Success Criteria

### Minimum Viable Demo
- [ ] TOE opens in TD without errors
- [ ] Audio analysis shows activity
- [ ] Visuals render to window
- [ ] Some audio reactivity visible

### Good Demo
- [ ] All minimum criteria
- [ ] Multiple visual layers
- [ ] Smooth audio response
- [ ] Feedback creates organic feel

### Great Demo
- [ ] All good criteria
- [ ] Particles respond to beats
- [ ] Glitch on high frequencies
- [ ] Emotional arc visible through song

---

## Rollback Plan

If we can't fix critical issues:

### Option A: Manual Fix in TD
1. Open broken TOE
2. Manually fix expressions
3. Save and demo

### Option B: Simpler Prompt
1. Use prompt without audio ("generative noise visualization")
2. Remove audio analysis dependency
3. Demo pure generative output

### Option C: Demo the Workflow Only
1. Show agents running
2. Show YAML output
3. Explain what TOE would contain
4. Manual TD demo separately

---

## Files to Watch

```
build_teardrop.py          # Main builder - expressions here
teardrop_full.toe          # Output file
test_output/teardrop_v2_subagent/  # Workflow outputs
meta_agentic/COORDINATION.md       # Current status
```

---

## Communication

### Morning Check-in
- Jake provides audio channel names
- Claude updates expressions
- Test cycle begins

### Afternoon Check-in
- Review test results
- Prioritize remaining work
- Adjust plan if needed

### Evening Wrap
- Document final state
- Note any remaining issues
- Prepare for demo day
