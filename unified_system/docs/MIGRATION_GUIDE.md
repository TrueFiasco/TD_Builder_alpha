# Migration Guide

## Overview

This guide helps you migrate from legacy TouchDesigner JSON formats to the unified system.

## Quick Migration

```bash
# Convert old format to new builder format
td-convert old_network.json --from canonical --to builder --output new_network.json
```

## Format Comparison

### Legacy Formats vs Unified System

| Feature | Old Lossless | Old Canonical | Unified Builder | Unified Extended |
|---------|--------------|---------------|-----------------|------------------|
| AI-Friendly | ❌ | ❌ | ✅ | ⚠️ |
| Round-Trip | ✅ | ❌ | ⚠️ | ✅ |
| Compact | ❌ | ✅ | ⚠️ | ❌ |
| Validated | ❌ | ❌ | ✅ | ✅ |
| CLI Tools | ❌ | ❌ | ✅ | ✅ |

## Migration Paths

### From Legacy Lossless JSON

```python
from core.format_converter import FormatConverter
from core.operator_registry import OperatorRegistry

registry = OperatorRegistry()
converter = FormatConverter(registry)

# Load legacy lossless JSON
with open("old_lossless.json") as f:
    old_json = json.load(f)

# The lossless format is similar to extended format
# Just update the format_layer field
old_json["format_layer"] = "extended"

# Convert to builder for easier editing
network = converter.from_canonical(old_json)
builder_json = converter.to_builder(network)

# Save
with open("new_builder.json", "w") as f:
    json.dump(builder_json, f, indent=2)
```

### From Legacy Canonical JSON

```python
# Legacy canonical uses string tables like new canonical
# Just ensure format_version is correct

old_json["format_version"] = "2.0.0"
old_json["format_layer"] = "canonical"

# Convert to network
network = converter.from_canonical(old_json)

# Export to preferred format
builder_json = converter.to_builder(network)
```

### From Manual JSON (Custom Formats)

```python
from api.network_builder import NetworkBuilder

# Read your custom JSON
with open("custom.json") as f:
    custom = json.load(f)

# Build network manually
builder = NetworkBuilder(custom["name"], mode="toe")

# Add operators from your format
for node in custom["operators"]:
    builder.add_operator(
        node["id"],
        node["type_family"],
        node["type_name"]
    )

# Add connections
for conn in custom["links"]:
    builder.connect(conn["source"], conn["target"])

# Export to builder JSON
builder.save_json("new_builder.json", layer="builder")
```

## API Changes

### Old: Direct JSON Manipulation

```python
# Old approach
network = {
    "nodes": [],
    "connections": []
}

network["nodes"].append({
    "name": "noise1",
    "type": "CHOP:noise"
})
```

### New: NetworkBuilder API

```python
# New approach
builder = NetworkBuilder("network")
builder.add_operator("noise1", "CHOP", "noise")
```

### Old: Manual Validation

```python
# Old: No validation
with open("output.toe.toc", "w") as f:
    f.write(generate_toc(network))
```

### New: Automatic Validation

```python
# New: Validates before building
builder.build_toe("output.toe")  # Validates automatically
```

## Breaking Changes

### 1. Operator Type Format

**Old:** `"type": "CHOP:noise"`

**New:** `"family": "CHOP", "type": "noise"`

**Migration:**
```python
# Convert old format
old_type = "CHOP:noise"
family, op_type = old_type.split(":")

builder.add_operator("noise1", family, op_type)
```

### 2. Path Format

**Old:** Relative paths `"noise1"`

**New:** Absolute paths `"/project1/noise1"`

**Migration:**
```python
# Old paths are converted automatically
# But if you're using absolute paths manually:
old_path = "noise1"
new_path = f"/project1/{old_path}"
```

### 3. Parameter Format

**Old:** Mixed parameter formats

**New:** Consistent parameter structure

```python
# Old
params = {
    "amp": 0.5,
    "freq": {"value": 1.0, "expr": "me.time.seconds"}
}

# New (both supported)
builder.set_parameter("noise1", "amp", 0.5)
builder.set_expression("noise1", "freq", "me.time.seconds", "python")
```

## Step-by-Step Migration

### Step 1: Backup

```bash
# Backup old files
cp -r old_networks/ old_networks_backup/
```

### Step 2: Convert Format

```bash
# Convert all old JSON files
for file in old_networks/*.json; do
    td-convert "$file" --from canonical --to builder -o "new_networks/$(basename $file)"
done
```

### Step 3: Validate

```bash
# Validate all converted files
for file in new_networks/*.json; do
    echo "Validating $file..."
    td-validate "$file" --verbose
done
```

### Step 4: Build Test

```bash
# Build one file to test
td-build new_networks/test.json --output test.toe --verbose

# Collapse and test in TouchDesigner
toecollapse test.toe.toc
```

### Step 5: Batch Convert

```bash
# Convert and build all valid networks
for file in new_networks/*.json; do
    if td-validate "$file"; then
        output="builds/$(basename ${file%.json}).toe"
        td-build "$file" -o "$output"
    fi
done
```

## Compatibility

### Backward Compatibility

The unified system can read:
- ✅ Legacy canonical JSON (with format updates)
- ✅ Legacy lossless JSON (as extended format)
- ⚠️ Custom JSON formats (manual conversion required)

### Forward Compatibility

Legacy tools **cannot** read:
- ❌ New builder JSON
- ❌ New extended JSON
- ❌ New canonical JSON (different format_version)

**Solution:** Export to compatible format

```python
# If you need to support legacy tools
# Keep old format alongside new format
builder.save_json("new_format.json", layer="builder")

# Also export to legacy-compatible format (if needed)
# Note: May lose some features
```

## Common Migration Issues

### Issue 1: Missing Operators

**Problem:** Operator types changed between TD versions

**Solution:**
```python
# Check operator exists
registry = OperatorRegistry()
spec = registry.get_operator_spec("CHOP", "old_type")

if not spec:
    # Find replacement
    print("Operator not found, check TD documentation for replacement")
```

### Issue 2: Invalid Connections

**Problem:** Connection rules changed

**Solution:**
```python
# Validate before building
report = builder.validate()

for error in report.get_errors():
    if "cannot connect" in error.message.lower():
        print(f"Fix connection: {error.message}")
```

### Issue 3: Parameter Names Changed

**Problem:** Parameter names different in new TD version

**Solution:**
```python
# Manually map old parameters to new
param_map = {
    "amplitude": "amp",
    "frequency": "freq"
}

for old_name, new_name in param_map.items():
    value = old_params.get(old_name)
    if value:
        builder.set_parameter("noise1", new_name, value)
```

## Testing Your Migration

### 1. Unit Tests

```python
# Test conversion
old_json = load_old_format("test.json")
new_json = convert_to_new_format(old_json)

assert len(old_json["nodes"]) == len(new_json["nodes"])
assert validate_network(new_json)
```

### 2. Integration Tests

```bash
# Test full pipeline
td-convert old.json --from canonical --to builder -o new.json
td-validate new.json --verbose
td-build new.json --output test.toe
toecollapse test.toe.toc

# Open in TouchDesigner and verify
```

### 3. Visual Comparison

- Open old .toe file in TouchDesigner
- Open new .toe file in TouchDesigner
- Compare network structure, parameters, connections

## Rollback Plan

If migration fails:

```bash
# Restore from backup
rm -rf new_networks/
cp -r old_networks_backup/ old_networks/

# Continue using old system
```

## Next Steps

After successful migration:

1. **Update build scripts** - Use new CLI tools
2. **Update documentation** - Reference new format
3. **Train team** - Share USER_GUIDE.md
4. **Monitor** - Watch for issues in production

## Getting Help

- Check [USER_GUIDE.md](USER_GUIDE.md) for API usage
- Check [ARCHITECTURE.md](ARCHITECTURE.md) for system details
- Run `td-validate --help` for CLI help
