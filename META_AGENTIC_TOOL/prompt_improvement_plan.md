# TD-Build Prompt Improvement Plan (Combined)

## Problem Summary

VANTA build produced 91 operators but had:
- 23 parameter warnings (unvalidated params)
- Missing POP workflow chain (used particleSOP instead of popnet)
- No blocking enforcement on structural issues

## Root Causes

1. KB returns pattern metadata, not buildable structures
2. No "query before building" enforcement
3. Critic validates but doesn't block
4. No uncertainty resolution workflow
5. No operator family inference from type names

---

## Files to Modify

| File | Path | Change Type |
|------|------|-------------|
| td_designer plan.md | `meta_agentic/experts/td_designer/plan.md` | Full rewrite with KB-first mandate |
| td_designer build.md | `meta_agentic/experts/td_designer/build.md` | Add validation output format |
| critic build.md | `meta_agentic/experts/critic/build.md` | Add blocking checks with score caps |
| kb_query.py | `meta_agentic/execution/kb_query.py` | Add 3 new functions |

---

## Task 1: kb_query.py - New Functions

Add these functions to enable buildable chain extraction:

```python
import logging

logger = logging.getLogger(__name__)


def _infer_operator_family(self, op_type: str) -> str:
    """
    Infer operator family from type name using suffix patterns.

    Returns: "CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP", or "UNKNOWN"
    """
    op_lower = op_type.lower()

    # Suffix-based detection (most reliable)
    suffix_map = {
        'chop': 'CHOP',
        'top': 'TOP',
        'sop': 'SOP',
        'dat': 'DAT',
        'comp': 'COMP',
        'mat': 'MAT',
        'pop': 'POP'
    }

    for suffix, family in suffix_map.items():
        if op_lower.endswith(suffix):
            return family

    # Common operator name patterns
    chop_patterns = ['audio', 'midi', 'osc', 'noise', 'lfo', 'math', 'select',
                     'merge', 'null', 'constant', 'lag', 'filter', 'analyze',
                     'beat', 'speed', 'lookup', 'rename', 'delete', 'shuffle',
                     'hold', 'logic', 'count', 'timer', 'trigger', 'limit',
                     'trail', 'record', 'wave', 'pattern', 'fan', 'resample']

    top_patterns = ['render', 'composite', 'level', 'blur', 'transform',
                    'feedback', 'glsl', 'text', 'movie', 'ramp', 'noise',
                    'hsvadjust', 'lookup', 'crop', 'flip', 'resolution',
                    'cache', 'null', 'out', 'displace', 'edge']

    sop_patterns = ['grid', 'box', 'sphere', 'tube', 'circle', 'line',
                    'merge', 'transform', 'noise', 'convert', 'add', 'copy',
                    'particle', 'force', 'limit', 'spring', 'metaball',
                    'carve', 'divide', 'facet', 'fuse', 'hole', 'sort']

    dat_patterns = ['table', 'text', 'script', 'execute', 'select', 'merge',
                    'convert', 'fifo', 'null', 'info', 'oscinput', 'web']

    comp_patterns = ['geometry', 'camera', 'light', 'base', 'container',
                     'window', 'button', 'slider', 'field']

    pop_patterns = ['popnet', 'source', 'force', 'attractor', 'limit',
                    'kill', 'collision', 'interact', 'property', 'sprite',
                    'stream', 'replicate', 'curve']

    # Check patterns (order matters - more specific first)
    if any(p in op_lower for p in pop_patterns):
        return 'POP'
    if any(p in op_lower for p in comp_patterns):
        return 'COMP'
    if any(p in op_lower for p in dat_patterns):
        return 'DAT'
    if any(p in op_lower for p in sop_patterns):
        return 'SOP'
    if any(p in op_lower for p in top_patterns):
        return 'TOP'
    if any(p in op_lower for p in chop_patterns):
        return 'CHOP'

    logger.warning(f"Could not infer family for operator type: {op_type}")
    return 'UNKNOWN'


def get_buildable_chain(self, pattern_name: str) -> dict:
    """
    Extract a complete buildable operator chain from a pattern.

    This is the PRIMARY function for TD Designer to use before building.
    Returns structured data ready for direct instantiation.

    Returns:
        {
            "pattern": "audio_reactive_visuals",
            "description": "Pattern description",
            "operators": [
                {
                    "step": 1,
                    "type": "audiodevicein",
                    "family": "CHOP",
                    "role": "Audio source",
                    "suggested_name": "audio_in",
                    "key_params": {"device": "default"},
                    "validated": true,
                    "is_primary": true,
                    "alternatives": ["audiofileinCHOP"]
                }
            ],
            "connections": [
                {"from_step": 1, "to_step": 2, "type": "wire"}
            ],
            "common_errors": ["Missing analyze after filter"],
            "validated": true
        }
    """
    logger.info(f"Getting buildable chain for pattern: {pattern_name}")

    # Query the pattern
    patterns = self.query_patterns(pattern_name)
    if not patterns:
        logger.warning(f"No pattern found for: {pattern_name}")
        return {
            "pattern": pattern_name,
            "description": "",
            "operators": [],
            "connections": [],
            "common_errors": [],
            "validated": False,
            "error": f"Pattern '{pattern_name}' not found in knowledge base"
        }

    pattern = patterns[0]
    chain_data = pattern.get('typical_chain', [])
    key_params = pattern.get('key_parameters', [])
    common_errors = pattern.get('common_errors', [])

    logger.info(f"Pattern has {len(chain_data)} chain steps, {len(key_params)} key params")

    # Build operators list
    operators = []
    for step in chain_data:
        step_num = step.get('step', len(operators) + 1)
        step_operators = step.get('operators', [])
        role = step.get('role', '')

        # First operator is primary, rest are alternatives
        for i, op_type in enumerate(step_operators):
            family = self._infer_operator_family(op_type)

            # Gather parameters for this operator
            params = {}
            for kp in key_params:
                if kp.get('operator') == op_type:
                    typical_values = kp.get('typical_values', [])
                    if typical_values:
                        params[kp['param']] = typical_values[0]

            # Validate operator exists
            is_valid = self.validate_operator(family, op_type)

            if i == 0:
                # Primary operator
                operators.append({
                    "step": step_num,
                    "type": op_type,
                    "family": family,
                    "role": role,
                    "suggested_name": f"{op_type.replace('CHOP', '').replace('TOP', '').replace('SOP', '')}1",
                    "key_params": params,
                    "validated": is_valid,
                    "is_primary": True,
                    "alternatives": step_operators[1:] if len(step_operators) > 1 else []
                })
            else:
                # Log alternatives for reference
                logger.debug(f"Alternative operator for step {step_num}: {op_type}")

    # Build connections
    connections = []
    for i in range(len(operators) - 1):
        connections.append({
            "from_step": operators[i]['step'],
            "to_step": operators[i + 1]['step'],
            "type": "wire"
        })

    # Calculate overall validation status
    all_validated = all(op['validated'] for op in operators)

    result = {
        "pattern": pattern_name,
        "description": pattern.get('description', ''),
        "operators": operators,
        "connections": connections,
        "common_errors": common_errors,
        "validated": all_validated
    }

    logger.info(f"Chain built: {len(operators)} operators, validated={all_validated}")
    return result


def validate_design_structure(self, design: dict) -> dict:
    """
    Comprehensive structural validation for a design.

    Performs 5 blocking checks:
    1. Empty containers - containers with no operators
    2. Chain completeness - all pattern steps implemented
    3. Connection integrity - no dangling connections
    4. Unvalidated parameters - params not in param_catalog
    5. Unresolved uncertainties - flagged items without resolution

    Returns:
        {
            "valid": false,
            "blocking": [
                {"type": "EMPTY_CONTAINER", "container": "audio", "fix": "Add operators or remove container"}
            ],
            "warnings": [...],
            "score_cap": 0.30  # Maximum score allowed given blocking issues
        }
    """
    blocking = []
    warnings = []
    score_cap = 1.0

    containers = design.get('containers', [])

    # CHECK 1: Empty containers
    for container in containers:
        if not container.get('operators', []):
            blocking.append({
                "type": "EMPTY_CONTAINER",
                "container": container.get('name'),
                "fix": "Add operators or remove container"
            })
            score_cap = min(score_cap, 0.30)

    # CHECK 2: Chain completeness
    matched_pattern = design.get('metadata', {}).get('matched_pattern')
    if matched_pattern:
        expected = self.get_buildable_chain(matched_pattern)
        if expected.get('validated'):
            expected_types = {op['type'] for op in expected.get('operators', [])}
            found_types = set()
            for container in containers:
                for op in container.get('operators', []):
                    found_types.add(op.get('type'))

            missing = expected_types - found_types
            if missing:
                blocking.append({
                    "type": "INCOMPLETE_CHAIN",
                    "pattern": matched_pattern,
                    "expected": list(expected_types),
                    "found": list(found_types),
                    "missing": list(missing)
                })
                score_cap = min(score_cap, 0.30)

    # CHECK 3: Connection integrity
    all_ops = set()
    for container in containers:
        for op in container.get('operators', []):
            # Support both "container/op" and just "op" formats
            all_ops.add(f"{container['name']}/{op['name']}")
            all_ops.add(op['name'])

    for conn in design.get('connections', []):
        from_op = conn.get('from', '')
        to_op = conn.get('to', '')

        # Check if connection endpoints exist
        from_exists = from_op in all_ops or from_op.split('/')[-1] in all_ops
        to_exists = to_op in all_ops or to_op.split('/')[-1] in all_ops

        if not from_exists:
            blocking.append({
                "type": "DANGLING_CONNECTION",
                "from": from_op,
                "available_ops": list(all_ops)[:10]  # Show first 10 for context
            })
            score_cap = min(score_cap, 0.30)

        if not to_exists:
            blocking.append({
                "type": "DANGLING_CONNECTION",
                "to": to_op,
                "available_ops": list(all_ops)[:10]
            })
            score_cap = min(score_cap, 0.30)

    # CHECK 4: Unvalidated parameters
    validation_summary = design.get('validation_summary', {})
    unvalidated_params = validation_summary.get('parameters_unvalidated', 0)
    if unvalidated_params > 0:
        blocking.append({
            "type": "UNVALIDATED_PARAMETERS",
            "count": unvalidated_params,
            "fix": "Validate all parameters against param_catalog.json or flag with needs_resolution"
        })
        score_cap = min(score_cap, 0.40)

    # CHECK 5: Unresolved uncertainties
    uncertainties = design.get('uncertainties', [])
    unresolved = [u for u in uncertainties if u.get('needs_resolution') and not u.get('resolution')]
    if unresolved:
        blocking.append({
            "type": "UNRESOLVED_UNCERTAINTIES",
            "count": len(unresolved),
            "items": [u.get('type', 'unknown') for u in unresolved]
        })
        score_cap = min(score_cap, 0.30)

    # CHECK 6: Orphan operators (bonus check from combining plans)
    # Find operators not connected to anything
    connected_ops = set()
    for conn in design.get('connections', []):
        connected_ops.add(conn.get('from', '').split('/')[-1])
        connected_ops.add(conn.get('to', '').split('/')[-1])

    for container in containers:
        for op in container.get('operators', []):
            op_name = op.get('name')
            # Null/out operators are allowed to be endpoints
            if op_name not in connected_ops and not any(x in op.get('type', '').lower() for x in ['null', 'out', 'in']):
                warnings.append({
                    "type": "ORPHAN_OPERATOR",
                    "operator": op_name,
                    "container": container.get('name'),
                    "note": "Operator has no connections - verify this is intentional"
                })

    return {
        "valid": len(blocking) == 0,
        "blocking": blocking,
        "warnings": warnings,
        "score_cap": score_cap
    }


# Module-level convenience functions
def get_chain(pattern_name: str) -> dict:
    """Quick access to buildable chain. Usage: chain = get_chain('audio_reactive')"""
    kb = get_default_kb()
    return kb.get_buildable_chain(pattern_name)


def validate_structure(design: dict) -> dict:
    """Quick structure validation. Usage: result = validate_structure(my_design)"""
    kb = get_default_kb()
    return kb.validate_design_structure(design)
```

---

## Task 2: td_designer/plan.md - Full Rewrite

Replace entire file with:

```markdown
# TD Designer - Plan Phase

## QUERY BEFORE BUILDING - MANDATORY

Before creating ANY operator section, you MUST follow this decision tree:

```
1. Identify sub-system needed (audio, particles, feedback, glsl, render, etc.)
                    │
                    ▼
2. Query KB: kb.query_patterns("pattern_name")
                    │
         ┌─────────┴─────────┐
         ▼                   ▼
   Pattern Found?        No Pattern?
         │                   │
         ▼                   ▼
3a. Extract typical_chain   3b. Flag as needs_resolution: true
    USE IT EXACTLY              Use placeholders with UNVALIDATED marker
         │                      DO NOT invent operators
         ▼
4. For each step in chain:
   - Instantiate EXACT operators listed
   - Apply key_parameters with typical_values
   - Only deviate if plan EXPLICITLY requires it
```

## UNCERTAINTY PROTOCOL

When you encounter something you're not sure about:

1. **DO NOT GUESS** - Mark it explicitly:
   ```yaml
   uncertainties:
     - type: "operator_choice"
       context: "Need particle system but unclear if SOP or POP"
       options: ["particleSOP in geo", "popnet with POPs"]
       needs_resolution: true
       resolution: null  # To be filled by user/critic
   ```

2. **Use placeholder names** with clear markers:
   ```yaml
   operators:
     - name: "UNVALIDATED_particle_system"
       type: "NEEDS_RESOLUTION"
       notes: "Awaiting pattern match or user input"
   ```

3. **Never proceed** with unresolved uncertainties for core functionality

## ANTI-HALLUCINATION RULES

### NEVER:
- Create an operator type you haven't validated against OperatorRegistry
- Use a parameter name you haven't validated against param_catalog
- Create an empty container (every container must have operators)
- Skip a step in a pattern's typical_chain
- Connect operators without validating both exist
- Invent parameter values without checking typical_values

### ALWAYS:
- Query pattern BEFORE building that section
- Validate operator types against operator_types.json
- Validate parameters against param_catalog.json
- Flag uncertainty with `needs_resolution: true`
- Include ALL chain steps (no shortcuts)
- Check alternatives list if primary operator fails validation

## PATTERN QUICK REFERENCE

Common patterns and their chain structures:

| Pattern | Chain | Key Params |
|---------|-------|------------|
| audio_reactive | audiodevicein → audiofilter → analyze → math → null | filter: cutoff, type; analyze: function |
| feedback_effect | source → composite → feedback → level → composite | level: opacity; composite: operand |
| particle_system | popnet → source → force → limit → render | source: birthrate; force: forcex,y,z |
| render_pipeline | geo + camera + light → render | render: lights, camera |
| glsl_integration | input → glsl → output | glsl: dat (shader source) |

## OUTPUT FORMAT

Your plan must include:

```yaml
plan:
  containers:
    - name: "container_name"
      purpose: "What this container does"
      matched_pattern: "pattern_name"  # From KB query
      pattern_validated: true/false

  uncertainties:
    - type: "uncertainty_type"
      context: "Description"
      needs_resolution: true

  validation_plan:
    patterns_to_query: ["list", "of", "patterns"]
    operators_to_validate: ["list", "of", "operators"]
    estimated_operator_count: N
```
```

---

## Task 3: td_designer/build.md - Add Validation Output

Add after existing design fields in output format:

```yaml
design:
  # ... existing fields (containers, operators, connections, expressions) ...

  validation_summary:
    operators_validated: 0
    operators_unvalidated: 0
    parameters_validated: 0
    parameters_unvalidated: 0
    unvalidated_params_list: []  # List actual param names that failed
    empty_containers: []
    chain_completeness:
      pattern: ""
      expected_steps: 0
      implemented_steps: 0
      missing: []

  uncertainties:
    - type: ""
      operator: ""
      params: []
      needs_resolution: true
      resolution: null
```

Add before "Handoff to network_builder" section:

```markdown
## PRE-SUBMISSION CHECKLIST

Before outputting design, verify ALL of these:

- [ ] Every container has at least one operator
- [ ] Every operator type validated against KB/OperatorRegistry
- [ ] Every parameter validated against param_catalog or flagged
- [ ] Chain completeness >= 100% for matched patterns
- [ ] All connections reference existing operators (no dangling)
- [ ] validation_summary section is complete
- [ ] All uncertainties have resolution OR are flagged for blocking
- [ ] No UNVALIDATED_ prefixed operators remain

**If ANY check fails, DO NOT submit. Fix the issue first.**

## VALIDATION WORKFLOW

Before final output:

1. Run `kb.validate_design_structure(design)`
2. Check result:
   - If `valid: true` → proceed to output
   - If `valid: false` → fix all `blocking` issues
   - If `score_cap < 0.65` → cannot pass critic, fix first
3. Include validation result in output
```

---

## Task 4: critic/build.md - Add Blocking Checks

Add after existing scoring section:

```markdown
## BLOCKING CHECKS - HARD STOPS

These checks MUST pass or score is CAPPED at the specified maximum:

### BLOCK-001: Empty Containers (cap: 0.30)
```python
for container in design.containers:
    if len(container.operators) == 0:
        BLOCK("Empty container: " + container.name)
        score_cap = 0.30
```

### BLOCK-002: Chain Completeness (cap: 0.30)
```python
if design.chain_completeness < 100:
    missing = design.validation_summary.chain_completeness.missing
    BLOCK("Missing chain steps: " + str(missing))
    score_cap = 0.30
```

### BLOCK-003: Connection Integrity (cap: 0.30)
```python
op_names = [op.name for op in all_operators]
for conn in design.connections:
    if conn.from not in op_names or conn.to not in op_names:
        BLOCK("Dangling connection: " + str(conn))
        score_cap = 0.30
```

### BLOCK-004: Unvalidated Parameters (cap: 0.40)
```python
if design.validation_summary.parameters_unvalidated > 0:
    unvalidated = design.validation_summary.unvalidated_params_list
    BLOCK("Unvalidated params: " + str(unvalidated))
    score_cap = 0.40
```

### BLOCK-005: Unresolved Uncertainties (cap: 0.30)
```python
for u in design.uncertainties:
    if u.needs_resolution and not u.resolution:
        BLOCK("Unresolved uncertainty: " + u.type)
        score_cap = 0.30
```

### BLOCK-006: UNVALIDATED Prefix Check (cap: 0.20)
```python
for op in all_operators:
    if op.name.startswith("UNVALIDATED_"):
        BLOCK("Placeholder operator not resolved: " + op.name)
        score_cap = 0.20
```

## UPDATED SCORING

```yaml
scoring:
  pass_threshold: 0.75      # Raised from 0.65
  conditional_pass: 0.65    # Pass with warnings only
  fail_threshold: 0.50

  caps:
    placeholder_operators: 0.20
    blocking_issues: 0.30
    validation_errors: 0.40
    unresolved_uncertainties: 0.50

  weights:
    structural_validity: 0.30
    pattern_compliance: 0.25
    parameter_validation: 0.25
    connection_integrity: 0.20
```

## CRITIC WORKFLOW

1. Receive design from td_designer
2. Run `validate_design_structure(design)`
3. Check for blocking issues first
4. If any blocking issues:
   - Cap score at `score_cap`
   - Return with `needs_revision: true`
   - List specific fixes required
5. If no blocking issues:
   - Calculate full score using weights
   - Provide feedback for improvement
```

---

## Execution Order

1. Add `_infer_operator_family()` to kb_query.py
2. Add `get_buildable_chain()` to kb_query.py
3. Add `validate_design_structure()` to kb_query.py
4. Add module-level convenience functions to kb_query.py
5. Replace td_designer/plan.md with KB-first mandate version
6. Update td_designer/build.md with validation output format
7. Update critic/build.md with blocking checks
8. Run integration test

---

## Success Criteria

After implementing these changes:

- [ ] `get_buildable_chain("audio_reactive")` returns structured chain
- [ ] `validate_design_structure(vanta_design)` catches 23 param issues
- [ ] TD Designer queries patterns BEFORE building sections
- [ ] TD Designer outputs validation_summary in every design
- [ ] Critic blocks on empty containers (score capped at 0.30)
- [ ] Critic blocks on incomplete chains (score capped at 0.30)
- [ ] Critic blocks on unvalidated parameters (score capped at 0.40)
- [ ] VANTA rebuild with new prompts fails validation (correctly!)
- [ ] Fixed VANTA rebuild passes with 0 unvalidated parameters

---

## Test Commands

```bash
# Test KB query functions
cd C:/TD_Projects/META_AGENTIC_TOOL
python -c "
from meta_agentic.execution.kb_query import get_default_kb
kb = get_default_kb()

# Test chain extraction
chain = kb.get_buildable_chain('audio_reactive_visuals')
print('=== Buildable Chain ===')
print(f'Pattern: {chain[\"pattern\"]}')
print(f'Validated: {chain[\"validated\"]}')
for op in chain['operators']:
    print(f'  Step {op[\"step\"]}: {op[\"type\"]} ({op[\"family\"]}) - {op[\"role\"]}')

# Test family inference
print('\\n=== Family Inference ===')
for op_type in ['noiseCHOP', 'renderTOP', 'gridSOP', 'textDAT', 'geometryCOMP', 'popnet']:
    family = kb._infer_operator_family(op_type)
    print(f'{op_type} → {family}')
"

# Test structure validation with VANTA design
python -c "
import yaml
from meta_agentic.execution.kb_query import get_default_kb

with open('C:/TD_Projects/VANTA_Collapse_Architecture/VANTA_network_design.yaml') as f:
    design = yaml.safe_load(f)

kb = get_default_kb()
result = kb.validate_design_structure(design)
print('=== Validation Result ===')
print(f'Valid: {result[\"valid\"]}')
print(f'Score Cap: {result[\"score_cap\"]}')
print(f'Blocking Issues: {len(result[\"blocking\"])}')
for issue in result['blocking']:
    print(f'  - {issue[\"type\"]}: {issue}')
"
```

---

## Comparison Notes

This combined plan incorporates:

**From original plan:**
- Execution order with explicit test steps
- Success criteria checklist
- Critic blocking checks with specific score caps
- td_designer/build.md validation output YAML format
- Test commands

**From user's comprehensive plan:**
- `_infer_operator_family()` helper with extensive pattern matching
- Full td_designer/plan.md rewrite with decision tree
- Uncertainty protocol with examples
- Pattern quick reference table
- `get_buildable_chain()` with alternatives, is_primary, common_errors
- `validate_design_structure()` with 5 checks
- Module-level convenience functions
- Detailed logging

**New additions from combining:**
- BLOCK-006: UNVALIDATED prefix check
- Orphan operator detection (as warning)
- `unvalidated_params_list` field to show actual failing params
- Pre-submission checklist in build.md
- Validation workflow section in critic
