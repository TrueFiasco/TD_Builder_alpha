# TouchBuilder Test Prompts

Standardized test prompts for regression testing.

## Test Suite

| # | Name | Focus | Status |
|---|------|-------|--------|
| 01 | Basic Network | Simple noise→null chain | TODO |
| 02 | Conversion Pipeline | DAT→CHOP, SOP→CHOP→TOP | DOCUMENTED |
| 03 | GLSL Shader | GLSL TOP with uniforms | TODO |
| 04 | UI Panel | Control panel with sliders | TODO |
| 05 | Audio Reactive | Audio analysis chain | TODO |

## How to Use

1. Give the prompt text to Claude Desktop
2. Note build attempts and any errors
3. Check TD console for "Skipping unrecognized parameter"
4. Verify visual output matches description

## Prompt File Format

Each prompt file contains:
- **Prompt**: What to ask Claude
- **Expected Operators**: What should be created
- **Critical Parameters**: Parameters that often fail
- **Table Data Required**: Any table_data needed
- **Common Mistakes**: Known failure modes
- **Success Criteria**: How to verify it worked

## Recording Results

After each test, note:
- Number of build attempts
- Errors encountered
- Whether find_parameter_usage was called
- Final success/failure
