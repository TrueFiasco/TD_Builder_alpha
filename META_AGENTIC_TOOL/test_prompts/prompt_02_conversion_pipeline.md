# Test Prompt 02: Data Conversion Pipeline

## Prompt
Create a TouchDesigner network demonstrating data type conversions:
1. A Table DAT with sample data that converts to CHOP channels
2. A Sphere SOP that converts to CHOP, then to TOP showing point positions as RGB

## Expected Operators
- `table1` (DAT:table) - Sample data
- `datto1` (CHOP:datto) - DAT to CHOP conversion
- `sphere1` (SOP:sphere) - Geometry source
- `sopto1` (CHOP:sopto) - SOP to CHOP conversion
- `chopto1` (TOP:chopto) - CHOP to TOP conversion
- `null_output` (TOP:null) - Final output

## Critical Parameters
```json
"datto1": {
  "dat": "op('table1')",
  "output": "chanpercol",
  "firstrow": "names",
  "firstcolumn": "values"
}

"sopto1": {
  "sop": "op('sphere1')",
  "attribscope": "P"
}

"chopto1": {
  "chop": "op('sopto1')",
  "dataformat": "rgb"
}
```

## Table Data Required
```json
"table_data": {
  "table1": [
    ["chan1", "chan2", "chan3"],
    ["0.0", "0.5", "1.0"],
    ["0.25", "0.75", "0.8"]
  ]
}
```

## Common Mistakes
1. Using integers for menu params (firstrow: 1 instead of "names")
2. Missing dataformat on choptoTOP
3. Not passing table_data to builder

## Success Criteria
- Table has data populated
- CHOP shows channels from table
- TOP shows RGB from sphere positions
- No "Skipping unrecognized parameter" errors in TD console
