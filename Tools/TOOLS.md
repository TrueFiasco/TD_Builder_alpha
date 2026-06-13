# TD Builder — Tool Reference

34 tools across two MCP servers. All **offline** tools are key-free. The **live** tools require a
running TouchDesigner (WebServer DAT on `:9981`); with TD down they return a clear "not running"
message rather than failing.

---

## Offline server `td-builder` — 15 tools

### KB tools (search the knowledge base)
| Tool | Purpose | Key inputs |
|---|---|---|
| `hybrid_search` | Semantic + graph search of TD docs | `query`, `n_results` |
| `get_operator_info` | Operator spec (family, params, summary) | `operator_name`, `compact` |
| `get_parameter_detail` | Full detail for one parameter | `operator_name`, `parameter_name` |
| `query_graph` | Graph queries: params / related / family | `command`, `family`/`operator` |
| `list_pop_operators` | List all POP operators | — |
| `find_operator_examples` | Real example networks using an operator | `operator` (or `operator_name`), `family`, `limit` |
| `find_operator_combination` | Examples combining several operators | `operator_types`, `require_connection` |
| `find_parameter_usage` | Real parameter values from examples | `operator_type`, `parameter_name` (optional), `compact` |
| `find_similar_networks` | Networks with similar structure | `example_id`, `limit` |
| `get_network_patterns` | Common operator-chain patterns | `min_frequency` |

### offline Builder tools (build/validate `.toe`·`.tox`)
| Tool | Purpose | Key inputs |
|---|---|---|
| `td_validate` | 5-stage validation (schema→semantic→reference→logical→TD-rules) | `network`, `format_layer`, `verbose` |
| `td_convert` | Convert between format layers (builder/extended/canonical) | `network`, `source_layer`, `target_layer` |
| `td_build_project` | Build a `.tox`/`.toe` from a design dict | `network_design`/`design`, `project_name`, `output_dir`, `mode` |

*(Also available as command-line tools — see `Tools/offline Builder tools/`.)*

### Other
| Tool | Purpose | Key inputs |
|---|---|---|
| `get_expert_prompt` | Load a specialized TD expert's prompt to apply its knowledge | `expert_name` (td_designer, network_builder, td_glsl_expert, td_python_expert, ui_expert, critic), `phase` (build/plan/self_improve) |
| `get_server_info` | Server identity (version, Python, paths, live status) | — |

---

## Live server `td-builder-live` — 19 tools (TouchDesigner must be open)

### Live tools — visual feedback
| Tool | Purpose | Key inputs |
|---|---|---|
| `capture_top_output` | Capture a TOP's rendered image (base64 JPEG/PNG) | `operator_path`, `format`, `resolution` |
| `get_top_info` | TOP metadata (resolution, format, GPU mem) | `operator_path` |
| `capture_op_viewer` | Capture an operator's viewer | `operator_path` |
| `capture_network_layout` | Capture the network canvas + node positions | `parent_path` |

### Live tools — node CRUD + introspection
| Tool | Purpose | Key inputs |
|---|---|---|
| `get_td_info` | TD version / OS / API info | — |
| `get_td_nodes` | List nodes under a path | `parent_path`, `pattern`, `limit` |
| `get_td_node_parameters` | Read a node's parameters | `node_path` |
| `get_td_node_errors` | A node's cook/validation errors | `node_path` |
| `create_td_node` | Create an operator | `parent_path`, `node_type`, `node_name` |
| `delete_td_node` | Delete an operator | `node_path` |
| `update_td_node_parameters` | Set parameter values | `node_path`, `properties` |
| `exec_node_method` | Call a method on a node | `node_path`, `method`, `args` |
| `execute_python_script` | Run Python inside TD | `script` |
| `get_td_classes` / `get_td_class_details` / `get_td_module_help` | TD Python API introspection | class/module name |

### Live tools — diagnostics
| Tool | Purpose | Key inputs |
|---|---|---|
| `get_cook_errors` | All current cook errors | `severity_filter`, `limit` |
| `get_error_summary` | Summarized error report | — |
| `get_python_exceptions` | Python runtime exceptions | — |
