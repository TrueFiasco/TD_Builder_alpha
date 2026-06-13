# Verified MCP Tool Signatures

**Source of Truth for TD Builder MCP Tools**

*Last verified: 2025-01-13 by TERRY (Tool Manager)*
*Extracted directly from source code - NOT from stale documentation*

---

## Quick Summary

| Server File | Tool Count | Status |
|-------------|------------|--------|
| `META_AGENTIC_TOOL/mcp_server.py` | 17 core + 20 TD Live | Active |
| `META_AGENTIC_TOOL/td_live_client.py` | 20 | Active (imported by mcp_server) |
| `kb_pipeline/mcp_archived/unified_mcp_server.py` | 5 | Archived (tools duplicated in mcp_server) |

**Active Server**: `META_AGENTIC_TOOL/mcp_server.py` (37 total tools)

---

## MCP Server Core Tools (17 tools)

### spawn_engineer
**Source**: `mcp_server.py` line 808-825
**Handler**: `spawn_engineer()` at line 525

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| engineer_type | string (enum) | YES | - | One of: `snippet_extractor`, `workflow_analyzer`, `concept_generator`, `knowledge_validator`, `data_source_auditor` |
| task_spec | object | YES | - | Task specification dict with all required inputs |

**Example**:
```json
{
  "engineer_type": "snippet_extractor",
  "task_spec": {"source_path": "/path/to/tox", "output_dir": "/output"}
}
```

**Common Mistakes**:
- Using invalid engineer_type (must be one of the 5 defined types)
- Missing task_spec object

---

### spawn_expert
**Source**: `mcp_server.py` line 827-873
**Handler**: `spawn_expert()` at line 592

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| expert_type | string (enum) | YES | - | One of: `td_designer`, `network_builder`, `td_glsl_expert`, `td_python_expert`, `ui_expert`, `critic`, `cg_expert`, `creative_expert`, `creative_orchestrator`, `format_reverse_engineer`, `summary_generator` |
| task | string | YES | - | Task description for the expert |
| phase | string (enum) | NO | `"build"` | One of: `"build"`, `"plan"`, `"self_improve"` |

**Example**:
```json
{
  "expert_type": "td_designer",
  "task": "Design a feedback noise system with audio reactivity",
  "phase": "build"
}
```

**Common Mistakes**:
- Forgetting that `phase` defaults to "build"
- Using expert for simple tasks (use get_expert_prompt instead to inline)

---

### hybrid_search
**Source**: `mcp_server.py` line 874-892
**Handler**: `call_tool()` line 1321-1348

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| query | string | YES | - | Natural language question about TouchDesigner |
| n_results | integer | NO | 5 | Number of results to return |

**Example**:
```json
{
  "query": "how to create audio reactive visuals",
  "n_results": 3
}
```

**Common Mistakes**:
- Setting n_results too high (causes context bloat)
- Not using specific operator names when looking for parameters

---

### get_operator_info
**Source**: `mcp_server.py` line 893-911
**Handler**: `call_tool()` line 1350-1421

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| operator_name | string | YES | - | Name of operator (e.g., "Grid SOP", "Audio File In CHOP") |
| compact | boolean | NO | `false` | If true, returns minimal info (name, family, type, summary, params with types) |

**Example**:
```json
{
  "operator_name": "Noise CHOP",
  "compact": true
}
```

**Common Mistakes**:
- Not using compact=true (wastes context on full parameter descriptions)
- Using wrong operator name format (try "Noise CHOP" not "noiseCHOP")

---

### query_graph
**Source**: `mcp_server.py` line 912-939
**Handler**: `call_tool()` line 1423-1495

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| command | string (enum) | YES | - | One of: `"params"`, `"related"`, `"family"` |
| operator | string | Conditional | - | Required for `params` and `related` commands |
| family | string | Conditional | - | Required for `family` command. One of: `SOP`, `CHOP`, `TOP`, `DAT`, `COMP`, `MAT`, `POP` |
| compact | boolean | NO | `false` | If true, returns only names for 'family' queries (saves ~700K context) |

**Examples**:
```json
{"command": "params", "operator": "Noise CHOP"}
{"command": "family", "family": "TOP", "compact": true}
{"command": "related", "operator": "Grid SOP"}
```

**Common Mistakes**:
- Forgetting required `operator` for params/related commands
- Forgetting required `family` for family command
- Not using compact=true for family queries (huge context cost)

---

### list_pop_operators
**Source**: `mcp_server.py` line 940-948
**Handler**: `call_tool()` line 1497-1507

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| (none) | - | - | - | No parameters |

**Example**:
```json
{}
```

---

### find_operator_examples
**Source**: `mcp_server.py` line 949-967
**Handler**: `call_tool()` line 1509-1518

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| operator | string | YES | - | Operator name (e.g., "analyze", "noise", "filter") |
| limit | integer | NO | 10 | Maximum examples to return |

**Example**:
```json
{
  "operator": "analyze",
  "limit": 5
}
```

**Common Mistakes**:
- Using full operator name like "Analyze CHOP" instead of just "analyze"

---

### find_operator_combination
**Source**: `mcp_server.py` line 968-991
**Handler**: `call_tool()` line 1520-1532

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| operator_types | array of strings | YES | - | List of operator types (e.g., `["noise", "analyze"]`) |
| require_connection | boolean | NO | `true` | Whether operators must be connected |
| limit | integer | NO | 5 | Maximum examples to return |

**Example**:
```json
{
  "operator_types": ["noise", "filter", "math"],
  "require_connection": true,
  "limit": 3
}
```

---

### find_parameter_usage
**Source**: `mcp_server.py` line 992-1020
**Handler**: `call_tool()` line 1534-1568

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| operator_type | string | YES | - | Operator type (e.g., "analyze", "filter") |
| parameter_name | string | YES | - | Parameter name (e.g., "function", "method") |
| limit | integer | NO | 10 | Maximum examples to return |
| compact | boolean | NO | `false` | If true, returns only unique values found |

**Example**:
```json
{
  "operator_type": "analyze",
  "parameter_name": "function",
  "compact": true
}
```

**Common Mistakes**:
- Not using compact=true (returns full example contexts, wastes tokens)

---

### find_similar_networks
**Source**: `mcp_server.py` line 1021-1039
**Handler**: `call_tool()` line 1570-1579

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| example_id | string | YES | - | Example ID (e.g., "analyzeCHOP/example1") |
| limit | integer | NO | 5 | Maximum similar examples to return |

**Example**:
```json
{
  "example_id": "analyzeCHOP/example1",
  "limit": 3
}
```

---

### get_parameter_detail
**Source**: `mcp_server.py` line 1040-1057
**Handler**: `call_tool()` line 1581-1637

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| operator_name | string | YES | - | Operator name (e.g., "Noise CHOP", "Level TOP") |
| parameter_name | string | YES | - | Parameter code name (e.g., "amp", "period", "invert") |

**Example**:
```json
{
  "operator_name": "Noise CHOP",
  "parameter_name": "amp"
}
```

**When to use**: After get_operator_info(compact=true) to drill down into specific params.

---

### get_network_patterns
**Source**: `mcp_server.py` line 1058-1072
**Handler**: `call_tool()` line 1639-1647

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| min_frequency | integer | NO | 5 | Minimum pattern frequency |

**Example**:
```json
{
  "min_frequency": 10
}
```

---

### td_build_project
**Source**: `mcp_server.py` line 1073-1182
**Handler**: `call_tool()` line 1649-1727

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| design | object | Conditional | - | Simple network design with `operators` and `connections` |
| network_design | object | Conditional | - | Advanced design with `containers`, `embed_tox` (takes precedence) |
| table_data | object | NO | - | Dict mapping Table DAT names to 2D arrays |
| project_name | string | NO | auto | Project name (auto-generated if omitted) |
| output_dir | string | NO | `mcp_server/output` | Output directory |
| mode | string (enum) | NO | `"tox"` | `"toe"` or `"tox"` |

**Simple Example**:
```json
{
  "design": {
    "operators": [
      {"name": "noise1", "type": "noise", "family": "CHOP"},
      {"name": "null1", "type": "null", "family": "CHOP"}
    ],
    "connections": [{"from": "noise1", "to": "null1"}]
  },
  "project_name": "my_network"
}
```

**Advanced Example with containers**:
```json
{
  "network_design": {
    "containers": [
      {
        "name": "audio",
        "type": "baseCOMP",
        "operators": [
          {"name": "audioIn", "type": "audiofileinCHOP"}
        ]
      }
    ],
    "connections": []
  },
  "mode": "tox"
}
```

**Common Mistakes**:
- Not specifying `family` for ambiguous operators (noise, constant, null exist in multiple families)
- Using `design` instead of `network_design` for container hierarchies
- Forgetting to query KB for operator parameters before building

---

### td_validate
**Source**: `mcp_server.py` line 1183-1211
**Handler**: `call_tool()` line 1729-1782

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| network | object | YES | - | TD network JSON |
| format_layer | string (enum) | NO | `"builder"` | `"builder"`, `"extended"`, or `"canonical"` |
| verbose | boolean | NO | `false` | Include detailed validation stages |

**Example**:
```json
{
  "network": {"operators": [{"name": "n1", "type": "noiseCHOP"}]},
  "format_layer": "builder",
  "verbose": true
}
```

---

### td_convert
**Source**: `mcp_server.py` line 1212-1239
**Handler**: `call_tool()` line 1784-1825

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| network | object | YES | - | TD network JSON to convert |
| source_layer | string (enum) | YES | - | `"builder"`, `"extended"`, or `"canonical"` |
| target_layer | string (enum) | YES | - | `"builder"`, `"extended"`, or `"canonical"` |

**Example**:
```json
{
  "network": {"operators": [...]},
  "source_layer": "builder",
  "target_layer": "canonical"
}
```

---

### td_compact_expertise
**Source**: `mcp_server.py` line 1240-1265
**Handler**: `call_tool()` line 1827-1861

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| refresh_yaml | boolean | NO | `true` | Also refresh legacy YAML views |
| events_path | string | NO | - | Override for events JSONL path |
| state_path | string | NO | - | Override for state YAML path |

**Example**:
```json
{
  "refresh_yaml": true
}
```

---

### get_expert_prompt
**Source**: `mcp_server.py` line 1266-1286
**Handler**: `call_tool()` line 1863-1870

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| expert_name | string (enum) | YES | - | `"td_designer"`, `"network_builder"`, `"td_glsl_expert"`, `"td_python_expert"`, `"ui_expert"`, or `"critic"` |
| phase | string (enum) | NO | `"build"` | `"build"`, `"plan"`, or `"self_improve"` |

**Example**:
```json
{
  "expert_name": "td_designer",
  "phase": "build"
}
```

**When to use**: Load expert knowledge into your context without spawning a separate agent (cheaper, more control).

---

## TD Live Client Tools (20 tools)

### Visual Feedback Tools (7)

#### capture_top_output
**Source**: `td_live_client.py` line 67-100 (handler), line 643-677 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| operator_path | string | YES | - | Path to TOP (e.g., `/project1/moviefilein1`) |
| resolution | string (enum) | NO | `"original"` | `"original"`, `"256"`, `"512"`, `"1024"` |
| format | string (enum) | NO | `"jpeg"` | `"jpeg"` or `"png"` |
| quality | number | NO | `0.85` | JPEG quality (0.1-1.0) |

**Example**:
```json
{
  "operator_path": "/project1/level1",
  "resolution": "512",
  "format": "jpeg"
}
```

---

#### get_top_info
**Source**: `td_live_client.py` line 103-132 (handler), line 678-691 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| operator_path | string | YES | - | Path to TOP |

**Example**:
```json
{"operator_path": "/project1/noise1"}
```

---

#### get_cook_errors
**Source**: `td_live_client.py` line 135-172 (handler), line 692-715 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| source_filter | string | NO | - | Filter errors by source operator path |
| severity_filter | string (enum) | NO | - | `"info"`, `"warning"`, `"error"`, `"fatal"` |
| limit | integer | NO | 100 | Maximum errors to return |

**Example**:
```json
{"severity_filter": "error", "limit": 10}
```

---

#### get_error_summary
**Source**: `td_live_client.py` line 175-202 (handler), line 716-724 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| (none) | - | - | - | No parameters |

**Example**:
```json
{}
```

---

#### capture_network_layout
**Source**: `td_live_client.py` line 205-241 (handler), line 725-743 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| comp_path | string | YES | - | Path to COMP (e.g., `/project1`) |
| depth | integer | NO | 1 | How deep to search for children |

**Example**:
```json
{"comp_path": "/project1", "depth": 2}
```

---

#### get_python_exceptions
**Source**: `td_live_client.py` line 244-275 (handler), line 744-758 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| limit | integer | NO | 50 | Maximum exceptions to return |

**Example**:
```json
{"limit": 20}
```

---

#### capture_op_viewer
**Source**: `td_live_client.py` line 278-331 (handler), line 759-788 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| operator_path | string | YES | - | Path to ANY operator |
| resolution | integer | NO | 512 | Output resolution in pixels |
| format | string (enum) | NO | `"jpeg"` | `"jpeg"` or `"png"` |
| quality | number | NO | `0.85` | JPEG quality |

**Example**:
```json
{"operator_path": "/project1/table1", "resolution": 256}
```

**Note**: Returns image for visual ops (TOP, rendered SOP), text for DATs, geometry stats for SOPs.

---

### CRUD Tools (6)

#### get_td_info
**Source**: `td_live_client.py` line 338-365 (handler), line 791-799 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| (none) | - | - | - | No parameters |

**Example**:
```json
{}
```

**Returns**: TD version, OS, MCP API version. **Call first to verify TD connection.**

---

#### get_td_nodes
**Source**: `td_live_client.py` line 368-397 (handler), line 800-825 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| parent_path | string | YES | - | Parent path (e.g., `/project1`) |
| pattern | string | NO | - | Filter pattern |
| include_properties | boolean | NO | `false` | Include full properties |
| limit | integer | NO | - | Max nodes to return |

**Example**:
```json
{"parent_path": "/project1", "limit": 50}
```

---

#### get_td_node_parameters
**Source**: `td_live_client.py` line 400-419 (handler), line 826-839 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| node_path | string | YES | - | Full path to node |

**Example**:
```json
{"node_path": "/project1/noise1"}
```

---

#### create_td_node
**Source**: `td_live_client.py` line 422-444 (handler), line 840-861 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| parent_path | string | YES | - | Parent path where node will be created |
| node_type | string | YES | - | Type (e.g., `"noiseTOP"`, `"mathCHOP"`) |
| node_name | string | NO | - | Optional custom name (auto-generated if omitted) |

**Example**:
```json
{"parent_path": "/project1", "node_type": "noiseTOP", "node_name": "myNoise"}
```

---

#### update_td_node_parameters
**Source**: `td_live_client.py` line 447-473 (handler), line 862-879 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| node_path | string | YES | - | Full path to node |
| properties | object | YES | - | Parameter name-value pairs to update |

**Example**:
```json
{"node_path": "/project1/noise1", "properties": {"amp": 2.0, "period": 10.0}}
```

---

#### delete_td_node
**Source**: `td_live_client.py` line 476-495 (handler), line 880-893 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| node_path | string | YES | - | Full path to node to delete |

**Example**:
```json
{"node_path": "/project1/noise1"}
```

---

### Execution Tools (2)

#### execute_python_script
**Source**: `td_live_client.py` line 498-525 (handler), line 894-907 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| script | string | YES | - | Python script to execute |

**Example**:
```json
{"script": "print(op('/project1/noise1').par.amp.val)"}
```

**Returns**: result, stdout, stderr.

---

#### exec_node_method
**Source**: `td_live_client.py` line 528-550 (handler), line 908-932 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| node_path | string | YES | - | Full path to node |
| method | string | YES | - | Method name to call |
| args | array | NO | `[]` | Positional arguments |
| kwargs | object | NO | `{}` | Keyword arguments |

**Example**:
```json
{
  "node_path": "/project1/container1",
  "method": "cook",
  "args": [],
  "kwargs": {"force": true}
}
```

---

### Query Tools (4)

#### get_td_node_errors
**Source**: `td_live_client.py` line 553-574 (handler), line 934-952 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| node_path | string | YES | - | Path to node to check |
| recurse | boolean | NO | `true` | Include descendant errors |

**Example**:
```json
{"node_path": "/project1/container1", "recurse": true}
```

---

#### get_td_classes
**Source**: `td_live_client.py` line 577-594 (handler), line 953-961 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| (none) | - | - | - | No parameters |

**Example**:
```json
{}
```

---

#### get_td_class_details
**Source**: `td_live_client.py` line 597-614 (handler), line 962-975 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| class_name | string | YES | - | Class name (e.g., `"OP"`, `"CHOP"`, `"TOP"`) |

**Example**:
```json
{"class_name": "CHOP"}
```

---

#### get_td_module_help
**Source**: `td_live_client.py` line 617-636 (handler), line 976-989 (schema)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| target | string | YES | - | Module/class path (e.g., `"td"`, `"td.OP"`) |

**Example**:
```json
{"target": "td.TOP"}
```

---

## KB Pipeline Archived Tools (5 tools)

**Note**: These are in `kb_pipeline/mcp_archived/unified_mcp_server.py` and are duplicated in the main mcp_server.py. Listed for reference only.

### td_assistant
**Source**: `unified_mcp_server.py` line 252-293

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| action | string (enum) | YES | - | `"query"`, `"batch_query"`, `"build_python"`, `"stats"` |
| query | string | Conditional | - | For `query` action |
| queries | array of strings | Conditional | - | For `batch_query` action |
| n_results | integer | NO | 5 | Number of results |
| filters | object | NO | - | Filter options (sources, categories, difficulty, min_popularity, tiers) |
| network | object | Conditional | - | For `build_python` action |
| target_parent_path | string | NO | `"/project1"` | For `build_python` action |
| collision_policy | string (enum) | NO | `"reuse"` | `"reuse"` or `"delete"` |

---

## Common Mistakes Summary

1. **Context Bloat**: Not using `compact=true` on query tools
2. **Wrong Operator Names**: Using `noiseCHOP` instead of `"Noise CHOP"` for get_operator_info
3. **Missing Family**: Not specifying `family` for ambiguous operators in td_build_project
4. **Skipping KB Query**: Building without first querying for operator parameters
5. **Wrong Design Key**: Using `design` instead of `network_design` for container hierarchies
6. **TD Not Running**: Calling TD Live tools without checking get_td_info first
7. **Full Path Required**: TD Live tools require full paths like `/project1/noise1`, not just `noise1`

---

## Workflow Best Practices

### Before Building
```
1. get_operator_info(compact=true) for each unfamiliar operator
2. find_parameter_usage(compact=true) for specific param values
3. td_validate before td_build_project
```

### After Building (with TD running)
```
1. get_td_info()  # verify connection
2. get_error_summary()  # quick health check
3. capture_top_output() or capture_op_viewer()  # visual verification
```

### Debugging
```
1. get_error_summary()
2. get_cook_errors(severity_filter="error")
3. get_python_exceptions() if scripts involved
4. capture_network_layout() to check connections
5. get_td_node_parameters() to verify values
```

---

*Document maintained by TERRY (Tool Manager)*
*Source files verified against commit 08d59f6*
