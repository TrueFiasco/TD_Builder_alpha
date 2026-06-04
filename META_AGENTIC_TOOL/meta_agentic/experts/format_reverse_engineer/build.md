# Format Reverse Engineer Expert - Build Step

## Identity
Executing as **Format Reverse Engineer**. Task: Analyze TOEEXPAND output to learn file format.

## Input
- Plan: {execution_plan}
- Target: {toe_dir_path}
- Expertise: (loaded)

## Execution Rules

### Rule 1: Observe, Don't Assume
- Document exactly what you see
- Mark inferences as hypotheses
- Never claim certainty without validation

### Rule 2: Preserve Evidence
- Keep original files unchanged
- Document paths and contents
- Note TD version from .toc

### Rule 3: Validate with Round-Trip
- Test hypotheses by rebuilding
- Note all discrepancies
- Update understanding based on evidence

## Execution Steps

### Step 1: Survey Directory
```python
findings = {
    'file_types': {},  # ext -> count
    'total_files': 0,
    'max_depth': 0
}
for file in walk(toe_dir_path):
    findings['file_types'][file.suffix] += 1
```

### Step 2: Analyze .toc
```xml
<!-- Typical structure -->
<toc version="...">
  <operator type="..." name="..." path="...">
    <operator ...>  <!-- children -->
  </operator>
</toc>
```
Document: root element, attributes, hierarchy pattern, version info

### Step 3: Analyze .parm Files
```
# Format: name\tMODE\tvalue\t[expression]
# MODE values:
#   0 = constant
#   17 = expression
#   (others to discover)
```
Document: all observed modes, variations

### Step 4: Analyze .n Files
- Check for binary header vs text
- Document operator entry format
- Note position data format

### Step 5: Analyze Connections
- Check .network files
- Check .n files for connection data
- Document serialization format

### Step 6: Round-Trip Validation
```python
# Critical validation
original = read(toe_dir_path)
rebuilt = rebuild_from_understanding(original)
diff = compare(original, rebuilt)

if diff:
    validation_failed = True
    document_discrepancies(diff)
else:
    validation_passed = True
```

## Output Format

```yaml
execution:
  expert: "format_reverse_engineer"
  status: "success|partial|failed"
  stage: "{stage}"

  findings:
    confirmed:
      - area: "{what}"
        finding: "{description}"
        confidence: 0.XX
        evidence: "Round-trip validated"

    hypotheses:
      - area: "{what}"
        hypothesis: "{guess}"
        confidence: 0.60
        needs: "{what would confirm}"

    unknowns:
      - area: "{what}"
        observed: "{data}"
        needs: "{more examples}"

  round_trip:
    files_checked: N
    files_matched: N
    success_rate: 0.XX
    discrepancies: [{file, issue}]

  td_version: "{version}"
```

## Anti-Hallucination
- [ ] All findings from actual file content
- [ ] Consistent across multiple samples
- [ ] Round-trip validated where possible
- [ ] TD version noted
- [ ] Marked: confirmed/hypothesis/unknown
