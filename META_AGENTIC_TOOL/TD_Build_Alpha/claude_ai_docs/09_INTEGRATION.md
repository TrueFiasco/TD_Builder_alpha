# Integration: Pre-Build Validation

This document describes what happens before the schema hits the builder and whether there's validation before TOECOLLAPSE.

---

## Validation Pipeline

```
Network Design (§5)
        │
        ▼
┌───────────────────┐
│  Critic Review    │  ← First validation gate
│  (structural)     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  KB Validation    │  ← Anti-hallucination check
│  (operators/params)│
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Builder Parse    │  ← Schema validation
│  (YAML structure) │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  ToeBuilder       │  ← File generation
│  (TOC, .n, etc)   │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  TOECOLLAPSE      │  ← ZIP compression
│  (final TOE)      │
└─────────┴─────────┘
```

---

## 1. Critic Review (First Gate)

**What's Checked**:
```yaml
structural_checks:
  - All containers referenced exist
  - All connections reference existing operators
  - No dangling inputs
  - Output operator exists
  - Expression syntax looks valid

semantic_checks:
  - Design aligns with creative vision
  - Technical approach followed
  - User requirements addressed
```

**What's NOT Checked**:
```yaml
not_checked_by_critic:
  - Actual operator existence in TD registry
  - Parameter validity
  - Expression runtime correctness
```

---

## 2. KB Validation (Anti-Hallucination)

**Function**: `kb.validate_network_design(network_json)`

**What's Checked**:

```python
def validate_network_design(self, network_json: dict) -> ValidationResult:
    errors = []
    warnings = []
    missing = []

    # 1. Validate operators exist
    for op in network_json.get("operators", []):
        op_type = op.get("type")
        base_name = extract_base_name(op.get("name"))

        if not self.validate_operator(op_type, base_name):
            missing.append(f"{op_type}:{base_name}")
            errors.append(f"Non-existent operator: {op_type}:{base_name}")

        # 2. Validate parameters
        params = op.get("params", {})
        invalid = self.check_parameters_valid(op_type, base_name, params)
        if invalid:
            warnings.append(f"Invalid params for {op_type}:{base_name}: {invalid}")

    # 3. Validate connections reference existing operators
    op_names = [op.get("name") for op in operators]
    for conn in network_json.get("connections", []):
        if conn["source"] not in op_names:
            errors.append(f"Connection source not found: {conn['source']}")
        if conn["target"] not in op_names:
            errors.append(f"Connection target not found: {conn['target']}")

    return ValidationResult(
        valid=len(errors) == 0,
        missing=missing,
        errors=errors,
        warnings=warnings
    )
```

**Validation Source**:
```yaml
ground_truth: "operator_param_schemas.json"
operators_count: 686
includes:
  - All operator types (CHOP, TOP, SOP, COMP, MAT, DAT)
  - All parameters per operator
  - Parameter types and ranges
```

---

## 3. Builder Parse (Schema Validation)

**What's Checked**:

```python
# In network_builder or ToeBuilder
required_fields = {
    "design": ["name", "operators"],
    "operator": ["name", "type"],
    "connection": ["from", "to"]
}

def validate_schema(design: dict) -> list[str]:
    errors = []

    if "operators" not in design:
        errors.append("Missing 'operators' list")

    for op in design.get("operators", []):
        if "name" not in op:
            errors.append(f"Operator missing 'name'")
        if "type" not in op:
            errors.append(f"Operator {op.get('name', '?')} missing 'type'")

    return errors
```

---

## 4. ToeBuilder File Generation

**What's Validated During Build**:

```python
class ToeBuilder:
    def build(self) -> Optional[Path]:
        # 1. Validate output directory
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True)

        # 2. Validate operator types are known
        for container, ops in self.operators.items():
            for op in ops:
                if not self._is_valid_type(op["type"]):
                    logger.warning(f"Unknown type: {op['type']}")

        # 3. Generate files
        self._write_system_files()
        self._write_containers()
        self._write_operators()
        self._write_connections()

        # 4. Generate TOC (CRITICAL for TD to read)
        toc_path = self._write_toc()

        # 5. Collapse to TOE
        return self._collapse(toc_path)
```

**Critical TOC Ordering**:
```python
def _write_toc(self) -> Path:
    # Order matters! TD expects this sequence:
    entries = []

    # 1. .n files first (operator definitions)
    entries.extend(sorted([f for f in files if f.endswith('.n')]))

    # 2. .cparm files (custom parameters)
    entries.extend(sorted([f for f in files if f.endswith('.cparm')]))

    # 3. .parm files (standard parameters)
    entries.extend(sorted([f for f in files if f.endswith('.parm')]))

    # 4. .panel files (UI panels)
    entries.extend(sorted([f for f in files if f.endswith('.panel')]))

    # Write TOC
    with open(toc_path, 'w') as f:
        f.write('\n'.join(entries))

    return toc_path
```

---

## 5. TOECOLLAPSE (Final Step)

**What Happens**:
```python
def _collapse(self, toc_path: Path) -> Path:
    """
    Create .toe file by zipping the expanded directory.
    TOE files are just ZIP files with specific structure.
    """
    toe_path = self.output_dir / f"{self.project_name}.toe"

    with zipfile.ZipFile(toe_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in self.expanded_dir.rglob('*'):
            if file.is_file():
                arcname = file.relative_to(self.expanded_dir)
                zf.write(file, arcname)

    return toe_path
```

**No Additional Validation** at this stage - it's purely file packaging.

---

## What's NOT Validated

### Expression Runtime Correctness

```yaml
not_validated:
  - "op('../audio/out1')['low']" may reference non-existent path
  - Channel names are guessed, not verified
  - Expression syntax is unchecked by Python

reason: "Would require TD runtime to evaluate"

mitigation:
  - Document expected paths
  - User verifies in TD
  - Log expressions for debugging
```

### Palette Component Internals

```yaml
not_validated:
  - audioAnalysis output structure
  - Internal operator organization
  - Custom parameter names

reason: "Palette components are black boxes until embedded"

mitigation:
  - Embed from expanded .tox.dir (preserves structure)
  - User inspects in TD to find actual paths
```

### Visual Correctness

```yaml
not_validated:
  - "Does it look right?"
  - "Does audio actually react?"
  - "Are colors correct?"

reason: "Requires TD runtime + human judgment"

mitigation:
  - Critic scores on technical feasibility
  - User tests in TD
  - Iteration based on feedback
```

---

## Pre-Build Checklist

Before calling `builder.build()`, the system should verify:

```yaml
pre_build_checklist:
  # Automatic checks
  - [ ] All operators have valid types (KB validation)
  - [ ] All connections reference existing operators
  - [ ] Parameters are for correct operator types
  - [ ] Container hierarchy is valid
  - [ ] Critic approved (score >= 0.65)

  # Manual/future checks
  - [ ] Expression paths are correct (requires TD)
  - [ ] Audio channel names are correct (requires TD)
  - [ ] Palette components have expected outputs (requires TD)
```

---

## Current State Summary

| Validation Stage | Implemented | Runs Automatically |
|------------------|-------------|-------------------|
| Critic Review | ✅ Yes | ✅ Yes |
| KB Operator Validation | ✅ Yes | ⚠️ On demand |
| KB Parameter Validation | ✅ Yes | ⚠️ On demand |
| Schema Validation | ⚠️ Basic | ✅ Yes |
| TOC Ordering | ✅ Yes | ✅ Yes |
| Expression Validation | ❌ No | N/A |
| Runtime Validation | ❌ No | N/A |

---

## Recommended Validation Flow

```python
def build_with_validation(design: dict, kb: KnowledgeBase) -> Path:
    # 1. Validate against KB
    validation = kb.validate_network_design(design)

    if not validation.valid:
        raise ValidationError(
            f"Network design has errors: {validation.errors}"
        )

    if validation.warnings:
        logger.warning(f"Validation warnings: {validation.warnings}")

    # 2. Build the file
    builder = ToeBuilder(
        project_name=design["design"]["name"],
        output_dir=Path("output")
    )

    # Add operators, connections, etc.
    for op in design["operators"]:
        builder.add_operator(...)

    for conn in design["connections"]:
        builder.add_connection(...)

    # 3. Generate TOE
    toe_path = builder.build()

    # 4. Log for debugging
    logger.info(f"Built: {toe_path}")
    logger.info(f"Validation warnings: {validation.warnings}")

    return toe_path
```

---

## Known Validation Gaps (Alpha Blockers)

1. **Expression Path Validation**: Currently guessing audio channel names
2. **Palette Output Structure**: Need to verify audioAnalysis outputs
3. **Connection Index Validation**: Input indices not checked against operator specs
4. **Display Flag Verification**: Easy to forget render/display flags

These should be addressed before alpha release.
