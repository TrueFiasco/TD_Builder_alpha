# Today's Plan - December 19, 2024

## Your Tasks (Jake)

### Morning
1. **Open teardrop_full.toe in TouchDesigner**
   - Location: `test_output/teardrop_v2_subagent/teardrop_full.toe`

2. **Find audioAnalysis output info**
   - Navigate to `/project1/audio/audioAnalysis`
   - Find the output operator (likely a null or out1)
   - Note the full path (e.g., `op('/project1/audio/audioAnalysis/out1')`)
   - List all channel names (e.g., `low`, `mid`, `high`, `level`, etc.)

3. **Share the info with me**
   - Just paste what you find, I'll update the builder

### Afternoon
4. **Test the rebuilt TOE**
   - Open the new version after I fix it
   - Verify:
     - [ ] Audio analysis receiving input
     - [ ] Visual chain rendering
     - [ ] Audio reactivity working
     - [ ] Window displaying output

5. **Report any issues**
   - I'll fix whatever doesn't work

### Evening (Optional)
6. **Review Claude AI documentation**
   - Location: `TD_Build_Alpha/claude_ai_docs/`
   - Check if anything needs adjustment for their review

---

## My Tasks (Claude)

### Blocked Until You Provide Audio Info
- Fix expression paths in `build_teardrop.py`
- Currently guessing: `op('../audio/audioAnalysis/out1')['low']`
- Need actual path and channel names from your TD inspection

### Ready to Do Now
1. **Add display/window output**
   - Add `windowCOMP` to builder
   - Connect output chain to window
   - Set display parameters

2. **Improve connection validation**
   - Verify operator connections in build

3. **Add error handling**
   - Better logging in builder
   - Catch common issues

### After You Test
4. **Fix any issues found**
   - Iterate based on your feedback

### Optional (If Time)
5. **Add GPU particles**
6. **Add glitch effects**

---

## Quick Reference

### Files I Need to Update
```
build_teardrop.py         # Expression paths + window
```

### Files You Need to Check
```
test_output/teardrop_v2_subagent/teardrop_full.toe
```

### Files for Claude AI Review
```
TD_Build_Alpha/claude_ai_docs/01_SYSTEM_PROMPTS.md
TD_Build_Alpha/claude_ai_docs/02_TOOL_DEFINITIONS.md
TD_Build_Alpha/claude_ai_docs/03_HANDOFF_SCHEMA.md
TD_Build_Alpha/claude_ai_docs/04_KB_QUERY_INTERFACE.md
... (all 9 docs)
```

---

## What I'm Waiting For

**From you:**
```
audioAnalysis output path: _______________
Channel names: _______________
```

Example of what I need:
```
Path: op('/project1/audio/audioAnalysis/analyze1')
Channels: ['bass', 'mid', 'treble', 'volume']
```

Once you give me this, I can fix the expressions and rebuild immediately.
