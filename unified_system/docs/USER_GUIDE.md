# TouchDesigner Unified System - User Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Python API](#python-api)
5. [CLI Tools](#cli-tools)
6. [Format Layers](#format-layers)
7. [Validation](#validation)
8. [Examples](#examples)
9. [Troubleshooting](#troubleshooting)

## Introduction

The TouchDesigner Unified System is a comprehensive toolkit for building, validating, and managing TouchDesigner networks programmatically. It provides:

- **NetworkBuilder API**: Fluent Python API for building networks
- **Validation Pipeline**: 5-stage validation (Schema, Semantic, Reference, Logical, TD Rules)
- **Format Conversion**: 3 format layers (Builder, Extended, Canonical)
- **File Builders**: Generate .toe/.tox files from JSON
- **CLI Tools**: Command-line tools for validation, conversion, and building

## Installation

### From Source (Development)

```bash
cd C:\TD_Projects\unified_system
pip install -e .
```

### Verify Installation

```bash
# CLI tools should be available
td-validate --help
td-convert --help
td-build --help
```

### Python Import

```python
from api.network_builder import NetworkBuilder
from validation.pipeline import ValidationPipeline
from core.format_converter import FormatConverter
```

## Quick Start

### Create a Simple Network

```python
from api.network_builder import NetworkBuilder

# Create network
builder = NetworkBuilder("my_project", mode="toe")

# Add operators
builder.add_operator("noise1", "CHOP", "noise")
builder.add_operator("null1", "CHOP", "null")

# Connect
builder.connect("noise1", "null1")

# Set parameters
builder.set_parameter("noise1", "amp", 0.5)

# Validate
if builder.is_valid():
    # Build .toe file
    builder.build_toe("output.toe")
    print("Success! Run: toecollapse output.toe.toc")
else:
    print("Network has errors")
```

### Using CLI Tools

```bash
# Validate network
td-validate network.json --verbose

# Convert formats
td-convert network.json --from builder --to canonical --pretty

# Build .toe file
td-build network.json --output project.toe --verbose
```

## Python API

### NetworkBuilder

The NetworkBuilder class provides a fluent API for building TouchDesigner networks.

#### Creating a Network

```python
from api.network_builder import NetworkBuilder, quick_network

# Full constructor
builder = NetworkBuilder("project_name", mode="toe")

# Quick network (uses defaults)
builder = quick_network("project_name")
```

####Adding Operators

```python
# Basic operator
builder.add_operator("noise1", "CHOP", "noise")

# With parent (for hierarchical networks)
builder.add_operator("container1", "COMP", "container")
builder.add_operator("noise1", "CHOP", "noise", parent="/project1/container1")

# Method chaining
builder.add_operator("noise1", "CHOP", "noise") \
       .add_operator("null1", "CHOP", "null")
```

#### Connecting Operators

```python
# Simple connection
builder.connect("noise1", "null1")

# Specify input index
builder.connect("noise1", "null1", target_input=0)

# Check if connection is valid before creating
if builder.can_connect("noise1", "null1"):
    builder.connect("noise1", "null1")
```

#### Setting Parameters

```python
# Set constant value
builder.set_parameter("noise1", "amp", 0.5)

# Set expression
builder.set_expression("noise1", "amp", "me.time.seconds", language="python")

# Set multiple parameters
builder.set_parameter("noise1", "amp", 0.5) \
       .set_parameter("noise1", "seed", 42)
```

#### Validation

```python
# Quick validation check
if builder.is_valid():
    print("Network is valid!")

# Get detailed validation report
report = builder.validate()

print(f"Valid: {report.valid}")
print(f"Errors: {report.total_errors}")
print(f"Warnings: {report.total_warnings}")

# Show errors
for error in report.get_errors():
    print(f"[{error.stage}] {error.message}")
```

#### Building .toe/.tox Files

```python
# Build .toe file
toc_file = builder.build_toe("output.toe", verbose=True)
print(f"Run: toecollapse {toc_file}")

# Build .tox file
toc_file = builder.build_tox("component.tox")
```

#### Exporting to JSON

```python
# Export to builder JSON
builder.save_json("network_builder.json", layer="builder")

# Export to canonical JSON (compressed)
builder.save_json("network_canonical.json", layer="canonical")

# Get JSON as dict
json_data = builder.to_json(layer="builder")
```

### Operator Management

```python
# List all operators
operators = builder.list_operators()
for op in operators:
    print(f"{op.path} ({op.op_type})")

# Filter by family
chops = builder.list_operators(family="CHOP")

# Get operator by name
op = builder.get_operator("noise1")

# Remove operator
builder.remove_operator("noise1")
```

### Position Management

```python
# Auto-layout operators
builder.auto_layout(spacing=150)

# Set position manually
builder.set_position("noise1", x=100, y=200)
```

## CLI Tools

### td-validate

Validate TouchDesigner network JSON files.

```bash
# Basic validation
td-validate network.json

# Verbose output (shows all validation stages)
td-validate network.json --verbose

# JSON output (for scripting)
td-validate network.json --json

# Validate canonical format
td-validate network.json --format canonical

# Disable colors
td-validate network.json --no-color
```

**Exit Codes:**
- `0` - Network is valid
- `1` - Network has errors
- `2` - Command error

### td-convert

Convert between format layers.

```bash
# Convert builder to canonical
td-convert network.json --from builder --to canonical

# Save to file
td-convert network.json --from builder --to canonical -o output.json

# Pretty-print JSON
td-convert network.json --from builder --to canonical --pretty

# Short flags
td-convert network.json -f builder -t canonical -o output.json --pretty
```

**Exit Codes:**
- `0` - Conversion successful
- `2` - Command error

### td-build

Build .toe/.tox files from network JSON.

```bash
# Build .toe file
td-build network.json --output project.toe

# Build .tox file
td-build network.json --output component.tox

# Verbose output
td-build network.json --output project.toe --verbose

# Skip validation (not recommended)
td-build network.json --output project.toe --no-validate
```

**Exit Codes:**
- `0` - Build successful
- `1` - Network validation failed
- `2` - Command error

## Format Layers

The unified system supports 3 format layers:

### 1. Builder JSON (AI-Friendly)

Simple, human-readable format optimized for AI generation.

```json
{
  "meta": {
    "project_name": "simple",
    "mode": "toe"
  },
  "nodes": [
    {
      "name": "noise1",
      "family": "CHOP",
      "type": "noise",
      "params": {"amp": 0.5}
    }
  ],
  "connections": [
    {"from": "noise1", "to": "null1"}
  ]
}
```

**Use Cases:**
- AI network generation
- Templates
- Quick prototyping

### 2. Extended JSON (Ground Truth)

Complete format with all operator data, defaults, and metadata.

```json
{
  "format_version": "2.0.0",
  "format_layer": "extended",
  "metadata": {...},
  "operators": [
    {
      "path": "/project1/noise1",
      "name": "noise1",
      "family": "CHOP",
      "type": "noise",
      "op_type": "CHOP:noise",
      "position": {...},
      "flags": {...},
      "parameters": {...}
    }
  ]
}
```

**Use Cases:**
- Round-trip editing
- Complete network representation
- Internal processing

### 3. Canonical JSON (Compact)

Compressed format using string tables for efficient storage.

```json
{
  "format_version": "2.0.0",
  "format_layer": "canonical",
  "string_table": ["noise1", "CHOP", "noise", "/project1/noise1"],
  "compressed_nodes": [[0, 1, 2, 3, {}]],
  "connections": []
}
```

**Use Cases:**
- File storage
- Network transmission
- Large network handling

## Validation

The validation pipeline consists of 5 stages:

### Stage 1: Schema Validation

Validates JSON structure against schema.

```python
# Checks:
- Required fields present
- Correct data types
- Valid enum values
```

### Stage 2: Semantic Validation

Validates operators and parameters exist in registry.

```python
# Checks:
- Operator type exists (CHOP:noise)
- Parameters are valid for operator
- Parameter types match
```

### Stage 3: Reference Validation

Validates connections and references.

```python
# Checks:
- Connection source exists
- Connection target exists
- Parent paths valid
```

### Stage 4: Logical Validation

Validates network logic.

```python
# Checks:
- Family compatibility (CHOP connects to CHOP)
- No circular dependencies
- Input/output compatibility
```

### Stage 5: TD Rules Validation

Validates TouchDesigner-specific rules.

```python
# Checks:
- Family-specific rules
- Version compatibility
- Special operator requirements
```

## Examples

### Example 1: Audio Reactive Visualization

```python
from api.network_builder import quick_network

builder = (quick_network("audio_viz")
    # Audio input
    .add_operator("audioin", "CHOP", "audiofilein")
    .add_operator("beat", "CHOP", "beat")
    .add_operator("lag", "CHOP", "lag")

    # Visual generation
    .add_operator("noise1", "TOP", "noise")
    .add_operator("level1", "TOP", "level")

    # Connect
    .connect("audioin", "beat")
    .connect("beat", "lag")
    .connect("noise1", "level1")

    # Parameters
    .set_parameter("audioin", "file", "audio.wav")
    .set_expression("noise1", "amp", "op('lag')['beat']", "python")

    # Build
    .build_toe("audio_viz.toe"))

print(f"Built: {builder.metadata.project_name}")
```

### Example 2: Feedback Loop

```python
builder = NetworkBuilder("feedback", mode="toe")

# Create feedback loop
builder.add_operator("noise1", "TOP", "noise")
builder.add_operator("blur1", "TOP", "blur")
builder.add_operator("feedback1", "TOP", "feedback")
builder.add_operator("composite1", "TOP", "composite")

# Connect with feedback
builder.connect("noise1", "composite1")
builder.connect("composite1", "blur1")
builder.connect("blur1", "feedback1")
builder.connect("feedback1", "composite1")  # Feedback loop

# Validate
if builder.is_valid():
    builder.build_toe("feedback.toe")
```

### Example 3: Hierarchical Network

```python
builder = NetworkBuilder("hierarchy", mode="toe")

# Create containers
builder.add_operator("base", "COMP", "container")
builder.add_operator("audio", "COMP", "container", parent="/project1/base")

# Add operators inside containers
builder.add_operator("noise1", "CHOP", "noise", parent="/project1/base/audio")
builder.add_operator("null1", "CHOP", "null", parent="/project1/base/audio")

# Connect
builder.connect("noise1", "null1")

# Build
builder.build_toe("hierarchy.toe")
```

### Example 4: Batch Processing

```bash
#!/bin/bash

# Validate all networks
for file in networks/*.json; do
    echo "Validating $file..."
    td-validate "$file" --json > "${file%.json}_report.json"
done

# Build valid networks
for file in networks/*.json; do
    if td-validate "$file" > /dev/null 2>&1; then
        output="builds/$(basename ${file%.json}).toe"
        td-build "$file" --output "$output" --verbose
    else
        echo "Skipping invalid network: $file"
    fi
done
```

## Troubleshooting

### Common Issues

**Issue:** `UnicodeEncodeError` on Windows

**Solution:** CLI tools now use ASCII-only output. If you still see errors, use `--no-color` flag.

```bash
td-validate network.json --no-color
```

**Issue:** Validation fails with "Unknown operator type"

**Solution:** Check that the operator type exists in TouchDesigner. Use the OperatorRegistry to verify:

```python
from core.operator_registry import OperatorRegistry

registry = OperatorRegistry()
spec = registry.get_operator_spec("CHOP", "noise")
if spec:
    print(f"Operator exists: {spec.display_name}")
```

**Issue:** Cannot connect operators

**Solution:** Check family compatibility. CHOPs can only connect to CHOPs, TOPs to TOPs, etc.

```python
# This will fail:
builder.connect("noise1", "ramp1")  # CHOP -> TOP

# This will work:
builder.connect("noise1", "null1")  # CHOP -> CHOP
```

**Issue:** Build fails with validation errors

**Solution:** Always validate before building:

```python
report = builder.validate()
if not report.valid:
    for error in report.get_errors():
        print(f"ERROR: {error.message}")
    exit(1)

builder.build_toe("output.toe")
```

### Performance Tips

1. **Use auto-layout sparingly** - Only call `auto_layout()` once at the end
2. **Batch parameter setting** - Use method chaining for multiple parameters
3. **Disable verbose output** - Set `verbose=False` for faster builds
4. **Validate once** - Don't validate multiple times unnecessarily

### Getting Help

- Check the documentation in `docs/`
- Run tests to see usage examples: `python tests/test_e2e.py`
- Use `--help` flag on CLI tools: `td-validate --help`

## Next Steps

- See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for migrating from old formats
- See [ARCHITECTURE.md](ARCHITECTURE.md) for system architecture details
- Explore example networks in `examples/`
