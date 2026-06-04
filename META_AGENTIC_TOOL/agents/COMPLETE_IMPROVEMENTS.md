# COMPLETE AGENT SYSTEM IMPROVEMENTS
# Based on Crystalline Synthesis Project Learnings
# Date: 2024-12-06

## EXECUTIVE SUMMARY

**Project**: Salt Crystal VJ System (Crystalline Synthesis)
**Result**: 6 runtime errors, missing features, poor UX
**Root Causes**: Validator failure, Builder shortcuts, missing requirements
**Success Rate**: 0% first-attempt, required extensive debugging

---

## CRITICAL FAILURES IDENTIFIED

### 1. VALIDATOR - COMPLETE FAILURE
**Errors Caught**: 0/6 (0%)
**Should Have Caught**:
- ❌ `audio_fft.par.bands` (doesn't exist → `outlength`)
- ❌ `scatterSOP` (doesn't exist → `gridSOP`)  
- ❌ `noise.par.freq` (doesn't exist → `period`)
- ❌ `light.par.colorr/g/b` (doesn't exist → unknown)
- ❌ `render.par.resolution` (doesn't exist → `outputresolution`)
- ❌ `fit()` function (tscript, not Python)

### 2. BUILDER - FEATURE OMISSIONS
**Specified vs Delivered**:
- ❌ 3 interactive buttons → 0 buttons delivered
- ❌ Fractal crystal growth → Simple grid with noise
- ❌ Palette audioAnalysis → Manual audio analysis
- ❌ Organized node layout → Everything at (0,0)
- ❌ Smoothed audio reactivity → Direct jittery values
- ❌ Mode system (hypnotic/building/intense) → Not implemented

### 3. TECHNICAL ARCHITECT - INCOMPLETE SPECS
**Missing Details**:
- ❌ HOW to create palette components
- ❌ Node layout coordinates
- ❌ Expression language (Python vs tscript)
- ❌ Audio smoothing requirements
- ❌ Verification that specs match Creative Brief

### 4. CREATIVE DIRECTOR - GOOD (No issues)
**Actually worked well** - clear vision, good requirements

---

## COMPREHENSIVE SKILL UPDATES

### FILE 1: technical_architect.md

**ADD THESE SECTIONS:**

---

## CRITICAL: CHECK PALETTE COMPONENTS FIRST

**BEFORE designing any custom solution:**

### Step 1: Search for Palette Components
```
MANDATORY searches:
1. "palette [task] component"
2. "Palette: [functionality]"
3. "[task] touchdesigner palette"
```

### Step 2: Document Finding
**In Technical Specification, MUST include:**

```
PALETTE COMPONENT CHECK:
✓ Searched: [list queries used]
✓ Found: [component name OR "none found"]
✓ Decision: [using palette / building custom]
✓ Implementation: [HOW to create it]
```

### Step 3: Implementation Plan
If palette component found:
- **Preferred**: Document manual drag-from-palette step
- **Alternative**: Research if programmatic instantiation possible
- **Rationale**: Palette components are pre-tested and optimized

**RULE**: ALWAYS prefer palette components over custom builds!

---

## MANDATORY: NODE LAYOUT SPECIFICATION

**Technical Architect MUST specify node positions.**

### Layout Requirements:
```python
# MUST include in spec:
- X/Y coordinates for each operator
- Data flow direction (left-to-right typical)
- Spacing between nodes (100-200 units standard)
- Visual grouping of related operators
```

### Example Layout Spec:
```
Audio Analysis Section (X: -600 to -200):
- audio_in: (-600, 400)
- audio_fft: (-400, 400)
- bass_extract: (-200, 500)
- mids_extract: (-200, 400)
- highs_extract: (-200, 300)

Particle Section (X: 0 to 400):
- grid: (0, 0)
- noise: (200, 0)
- points: (400, 0)
```

**WHY**: Proper layout = usable network for iteration

---

## AUDIO REACTIVE BEST PRACTICES

**When mapping audio to parameters:**

### DO:
✓ Use smoothing: `filter CHOP` or `lag CHOP`
✓ Use appropriate ranges: `math CHOP` with gain/offset
✓ Use `chanop: 'average'` for RMS
✓ Test parameter behavior over time

### DON'T:
❌ Direct raw audio to parameters (jittery)
❌ Use `absTime.seconds * constant` (grows forever)
❌ Skip smoothing on visual parameters

### Example:
```python
# BAD:
grid.par.rows.expr = f'op("{rms.path}")[0] * 100'

# GOOD:
# Create lag CHOP first for smoothing
lag = root.create(lagCHOP, 'rms_smooth')
lag.inputConnectors[0].connect(rms)
lag.par.lag = 0.3  # 300ms smoothing

# Then use smoothed value
grid.par.rows.expr = f'int(50 + op("{lag.path}")[0] * 100)'
```

---

## EXPRESSION LANGUAGE SPECIFICATION

**Technical Architect MUST specify expression language.**

### Python Expressions (Default):
```python
# Use Python syntax:
param.expr = 'min + (val - inMin) / (inMax - inMin) * (max - min)'
param.expr = 'sin(absTime.seconds * 0.1) + 2'
param.expr = 'noise(me.inputPoint.index * 0.1)'
```

### Tscript Expressions:
```python
# Must set language first:
param.exprLanguage = 'tscript'
param.expr = 'fit($F, 0, 100, 0, 1)'
```

**CRITICAL**: 
- `fit()` is tscript ONLY
- Default is Python
- Specify which language in spec

---

## FEATURE COMPLETENESS CHECK

**Before finalizing Technical Specification:**

### Checklist:
□ ALL Creative Brief requirements addressed
□ Interactive controls specified (if requested)
□ Mode systems detailed (if requested)
□ Fractal/procedural systems explained (if requested)
□ Audio reactivity fully mapped
□ Node layout coordinates provided
□ Expression language specified
□ Palette components researched

**If ANY Creative Brief requirement is unclear or missing:**
- STOP
- Ask Creative Director for clarification
- Update spec with details

---

### FILE 2: builder.md

**ADD THESE SECTIONS:**

---

## STRICT PARAMETER VERIFICATION PROTOCOL

**MANDATORY: Verify EVERY parameter before using.**

### Verification Process:

```python
# STEP 1: Before using ANY parameter
result = get_operator_info("Operator Name")

# STEP 2: Search returned parameters for exact match
# Example: Looking for 'bands' parameter
# Result: NOT FOUND in parameter list
# Action: Search documentation for correct parameter

# STEP 3: Use correct parameter
# Found: 'outlength' is the correct parameter
audio_fft.par.outlength = 16  # VERIFIED
```

### Verification Checklist:
□ Operator exists (not made-up type)
□ Parameter exists in get_operator_info results
□ Parameter name matches exactly (case-sensitive)
□ Parameter code is correct (not display name)

### Common Mistakes to Avoid:
```python
# ❌ WRONG - Guessed parameters:
audio_fft.par.bands = 16  # Doesn't exist
scatter = create(scatterSOP)  # Operator doesn't exist
noise.par.freq = 0.5  # Doesn't exist
light.par.colorr = 1.0  # Doesn't exist
render.par.resolution = '1920x1080'  # Doesn't exist

# ✅ CORRECT - Verified parameters:
audio_fft.par.outlength = 16  # Verified: exists
grid = create(gridSOP)  # Verified: exists
noise.par.period = 0.5  # Verified: exists
# light color: SKIP if unclear
render.par.outputresolution = '1920x1080'  # Verified: exists
```

**RULE**: If parameter verification fails, STOP and research correct parameter.

---

## EXPRESSION LANGUAGE COMPLIANCE

**When setting .expr on parameters:**

### Default: Python Expressions
```python
# Use Python math:
param.expr = '50 + value * 100'
param.expr = '0.05 + (noise(...) + 1) / 2 * 0.15'
param.expr = 'sin(absTime.seconds * 0.1) + 2'
```

### Tscript Functions:
```python
# If using fit(), clamp(), etc:
param.exprLanguage = 'tscript'
param.expr = 'fit($F, 0, 100, 0, 1)'
```

**CRITICAL**:
- `fit()`, `clamp()`, `$F` are tscript ONLY
- Default expression language is Python
- Set `.exprLanguage = 'tscript'` if needed

---

## NODE LAYOUT REQUIREMENTS

**Builder MUST position nodes according to Technical Spec.**

### Standard Layout Pattern:
```python
# Data flows left → right
# Y increases upward
# Spacing: 200 units horizontal, 100 units vertical

# Example proper layout:
audio_in.nodeX = -600
audio_in.nodeY = 400

audio_fft.nodeX = -400  # 200 units right
audio_fft.nodeY = 400   # Same Y = same "level"

bass.nodeX = -200       # 200 units right
bass.nodeY = 500        # 100 units up = separate branch
```

### Layout Rules:
1. **Follow data flow**: Inputs left, outputs right
2. **Group related ops**: Same Y coordinate
3. **Branch vertically**: Different Y for parallel paths
4. **Spacing**: 200px horizontal minimum
5. **Match spec**: Use exact coordinates from Technical Spec

**NEVER stack all nodes at (0, 0)!**

---

## FEATURE COMPLETENESS REQUIREMENT

**Builder MUST implement ALL Technical Spec features.**

### Pre-Build Checklist:
□ Read entire Technical Specification
□ List all required features
□ List all interactive controls
□ Note all mode systems
□ Check node layout coordinates

### During Build:
□ Implement each feature from list
□ Verify against Technical Spec
□ Do NOT simplify or skip features
□ Do NOT substitute simpler alternatives

### Post-Build Verification:
□ ALL features implemented
□ ALL controls created
□ ALL modes functional
□ Node layout matches spec

**RULE**: If feature seems difficult, implement it anyway or ask for help. Do NOT skip!

---

## AUDIO REACTIVE IMPLEMENTATION

**When implementing audio reactivity:**

### Required Components:
1. **Smoothing**: Use `lag CHOP` or `filter CHOP`
2. **Mapping**: Use `math CHOP` for gain/offset
3. **Averaging**: Use `chanop: 'average'` for multi-channel

### Example Implementation:
```python
# Audio input
audio_in = root.create(audiofileinCHOP, 'audio')

# Extract RMS with smoothing
rms_raw = root.create(mathCHOP, 'rms_raw')
rms_raw.inputConnectors[0].connect(audio_in)
rms_raw.par.chanop = 'average'

# Smooth the RMS
rms_smooth = root.create(lagCHOP, 'rms_smooth')
rms_smooth.inputConnectors[0].connect(rms_raw)
rms_smooth.par.lag = 0.3  # 300ms smoothing

# Map to useful range
rms_mapped = root.create(mathCHOP, 'rms_mapped')
rms_mapped.inputConnectors[0].connect(rms_smooth)
rms_mapped.par.gain = 100
rms_mapped.par.preoff = 50

# Use in expression
grid.par.rows.expr = f'int(op("{rms_mapped.path}")[0])'
```

---

## VERIFICATION LOG REQUIREMENT

**Builder MUST include verification log in code comments.**

### Log Format:
```python
"""
PARAMETER VERIFICATION LOG:

✓ Audio File In CHOP - audiofileinCHOP_Class
  - par.file: verified (code: file)
  - par.play: verified (code: play)

✓ Audio Spectrum CHOP - audiospectrumCHOP_Class  
  - par.outlength: verified (code: outlength)
  - ❌ par.bands: NOT FOUND (used outlength instead)

✓ Grid SOP - gridSOP_Class
  - par.rows: verified (code: rows)
  - par.cols: verified (code: cols)

✓ Noise SOP - noiseSOP_Class
  - par.period: verified (code: period)
  - ❌ par.freq: NOT FOUND (used period instead)
"""
```

**RULE**: If verification log is incomplete, code is incomplete.

---

### FILE 3: validator.md  

**ADD THESE SECTIONS:**

---

## STRICT PARAMETER VERIFICATION PROTOCOL

**MANDATORY: Validator MUST verify EVERY parameter.**

### Verification Process:

**For each parameter assignment in code:**

```python
# Example: audio_fft.par.bands = 16

# STEP 1: Extract info
operator_type = "Audio Spectrum CHOP"
parameter_name = "bands"

# STEP 2: Call verification tool
result = get_operator_info("Audio Spectrum CHOP")

# STEP 3: Search result for parameter
# Look through: Parameters (14)
# Search for: "bands" or code: "bands"
# Result: NOT FOUND

# STEP 4: Action
Status: FAIL
Error: "Parameter 'bands' does not exist on Audio Spectrum CHOP"
Correction: "Check documentation for correct parameter"
```

### Verification Checklist Per Parameter:
□ Operator type identified correctly
□ get_operator_info() called for operator
□ Parameter name searched in results
□ Parameter code verified
□ If NOT found → FAIL validation

### Validation Rules:
1. **EVERY** `par.paramname` must be verified
2. **EVERY** operator type must be verified to exist
3. **NO EXCEPTIONS** - even "obvious" parameters
4. If verification log missing → FAIL immediately
5. If any unverified parameter → FAIL immediately

---

## EXPRESSION LANGUAGE VERIFICATION

**Validator MUST check expression language compliance.**

### Check Process:
```python
# Scan for expressions:
patterns_to_check = [
    '.expr = ',
    '.expr=',
]

# For each expression found:
# Check for tscript-only functions:
tscript_functions = ['fit(', 'clamp(', '$F', 'ifs(']

# If tscript function found:
if 'fit(' in expression:
    # Check if exprLanguage set:
    if '.exprLanguage = ' not in code_before_expression:
        Status: FAIL
        Error: "Using fit() without setting exprLanguage = 'tscript'"
```

### Expression Validation Rules:
□ All expressions use valid Python OR tscript set
□ No `fit()` without `exprLanguage = 'tscript'`
□ No undefined variables in expressions
□ Expressions are properly quoted strings

---

## FEATURE COMPLETENESS VERIFICATION

**Validator MUST verify ALL features implemented.**

### Comparison Process:

**Step 1: Extract Creative Brief Requirements**
```
Example from Crystalline Synthesis:
- 3 interactive buttons (Genesis Pulse, Prismatic Shift, Density Override)
- Fractal-like crystal growth
- Three modes (hypnotic, building, intense)
- Bismuth iridescence colors
- Audio-reactive particle system
```

**Step 2: Extract Technical Spec Features**
```
- Button 1: Genesis Pulse → burst 500 particles
- Button 2: Prismatic Shift → cycle colors 0-3
- Button 3: Density Override → force dense mode
- Fractal: Attraction forces + size hierarchies
- Modes: RMS-based thresholds (<0.3, 0.3-0.7, >0.7)
```

**Step 3: Verify Implementation**
```python
# Scan code for:
□ Button 1 created?
□ Button 2 created?
□ Button 3 created?
□ Fractal system implemented?
□ Mode detection implemented?
□ All audio mappings present?
```

**Step 4: Feature Checklist**
For each feature in Tech Spec:
□ Feature implemented in code
□ Feature matches spec description
□ Feature has proper parameters
□ Feature is connected properly

**If ANY feature missing → FAIL validation immediately**

---

## NODE LAYOUT VERIFICATION

**Validator MUST check node positioning.**

### Layout Check:
```python
# Extract all node positions from code:
node_positions = {
    'audio_in': (nodeX, nodeY),
    'audio_fft': (nodeX, nodeY),
    # etc...
}

# Check for problems:
issues = []

# 1. Check if everything at (0, 0)
if all(pos == (0, 0) for pos in node_positions.values()):
    issues.append("All nodes at origin - no layout")

# 2. Check if positions match Tech Spec
if tech_spec_has_layout_coords:
    for node, spec_pos in spec_positions.items():
        if node_positions[node] != spec_pos:
            issues.append(f"{node} position mismatch")

# 3. Check data flow direction
# Inputs should have lower X than outputs
```

**If layout problems found → FAIL with corrections**

---

## AUDIO REACTIVITY VERIFICATION

**Validator MUST check audio implementation quality.**

### Quality Checks:
□ Audio values smoothed (lag/filter CHOP present)
□ No direct raw audio to visual parameters
□ Appropriate value ranges (math CHOP used)
□ No infinitely-growing expressions (`absTime * const`)

### Examples of FAIL:
```python
# ❌ No smoothing:
grid.par.rows.expr = f'op("{rms.path}")[0] * 100'
# Should have lag/filter CHOP first

# ❌ Grows forever:
noise.par.period.expr = 'absTime.seconds * 0.1'  
# Should use sin/cos or bounded function

# ❌ Direct audio:
pts.par.pscale.expr = f'op("{bass.path}")[0]'
# Should smooth and map to appropriate range
```

---

## VALIDATION FAILURE REPORT FORMAT

**When validation fails, provide detailed report:**

```
VALIDATION STATUS: FAIL

CRITICAL ERRORS:
1. Parameter 'bands' does not exist on Audio Spectrum CHOP
   - Line: audio_fft.par.bands = 16
   - Fix: Use audio_fft.par.outlength = 16
   - Verified: get_operator_info("Audio Spectrum CHOP")

2. Operator 'scatterSOP' does not exist
   - Line: scatter = main.create(scatterSOP, 'particles')
   - Fix: Use gridSOP instead
   - Verified: Search results show no scatterSOP

MISSING FEATURES:
1. Button 1 (Genesis Pulse) not implemented
   - Required: Creative Brief, Technical Spec
   - Found: No button creation in code

2. Fractal system not implemented
   - Required: Creative Brief specifies "fractal-like"
   - Found: Simple grid with noise (not fractal)

NODE LAYOUT ISSUES:
1. All nodes at (0, 0)
   - Required: Organized data flow
   - Found: Everything stacked at origin

CORRECTIONS REQUIRED:
- Fix all 5 parameter errors
- Implement 3 missing buttons  
- Implement fractal system
- Add proper node layout
- Return to Builder for fixes

DO NOT APPROVE until ALL issues resolved.
```

---

## VALIDATION SUCCESS CRITERIA

**Validation passes ONLY when:**

□ ALL parameters verified with get_operator_info
□ ALL operators verified to exist
□ ALL Creative Brief features implemented
□ ALL Technical Spec features implemented
□ Node layout proper and organized
□ Audio reactivity smoothed and mapped
□ Expressions use correct language
□ No runtime errors expected
□ Code quality excellent
□ Verification log complete

**Success Rate Target: 100% first-attempt working code**

---

### FILE 4: TESTING_GUIDE.md

**ADD THIS SECTION:**

---

## POST-MORTEM CHECKLIST

**After each test, evaluate:**

### Creative Director:
□ Clear vision and requirements?
□ Requirements achievable?
□ Appropriate scope?
□ Good communication?

### Technical Architect:
□ All Creative Brief requirements in spec?
□ Palette components researched?
□ Node layout specified?
□ Expression language specified?
□ Audio smoothing specified?
□ Implementation details clear?

### Builder:
□ ALL features implemented?
□ ALL parameters verified?
□ Proper node layout?
□ No shortcuts taken?
□ Verification log complete?

### Validator:
□ ALL parameters verified?
□ ALL features checked?
□ Layout verified?
□ Audio quality checked?
□ Caught errors?

### Overall:
□ First-attempt success?
□ If not, what failed?
□ How to prevent next time?
□ What to add to skills?

---

## SUMMARY OF IMPROVEMENTS

### Key Changes:

1. **Technical Architect**:
   - MUST search palette components first
   - MUST specify node layout coordinates
   - MUST specify expression language
   - MUST verify specs match Creative Brief
   - MUST detail audio smoothing

2. **Builder**:
   - MUST verify EVERY parameter with tools
   - MUST implement ALL features (no shortcuts)
   - MUST create proper node layout
   - MUST use correct expression language
   - MUST include verification log
   - MUST smooth audio reactivity

3. **Validator**:
   - MUST call get_operator_info for EVERY parameter
   - MUST verify ALL Creative Brief features
   - MUST check node layout
   - MUST verify expression language
   - MUST verify audio quality
   - MUST produce detailed failure reports

### Target Metrics:
- **First-attempt success rate**: 100%
- **Parameter errors**: 0
- **Missing features**: 0
- **User corrections**: 0
- **Validator catch rate**: 100%

---

## PALETTE COMPONENT LIMITATION

**Current Limitation Discovered:**
- Cannot easily instantiate palette components programmatically
- No clear documentation for `loadTox()` or similar
- Manual drag-from-palette may be required

**Recommendation**:
- Technical Architect should specify: "User drag audioAnalysis from Palette"
- Builder should create placeholder: "# TODO: User add audioAnalysis here"
- Document integration: "Connect audio → audioAnalysis → use outputs"

---

## NEXT STEPS

1. **Update skill files** with all sections above
2. **Test with new prompt** to verify improvements
3. **Measure success rate** (target: 100%)
4. **Iterate** based on new learnings

---

## LEARNINGS APPLIED

From Crystalline Synthesis build:
✅ 6 parameter errors → Add strict verification
✅ Missing features → Add completeness checks
✅ Poor layout → Add layout requirements
✅ No smoothing → Add audio best practices
✅ Wrong expression language → Add language specification
✅ 0% validator success → Complete validator overhaul

**Goal**: Never repeat these mistakes.
