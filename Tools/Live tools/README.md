# Live tools

The tools on the **`td-builder-live`** server — they talk to a *running* TouchDesigner via its
WebServer DAT (`:9981`). Register `td-builder-live` only when TD is open.

Capture: `capture_top_output`, `get_top_info`, `capture_op_viewer`, `capture_network_layout`.
Node CRUD + introspection: `get_td_info`, `get_td_nodes`, `get_td_node_parameters`,
`get_td_node_errors`, `create_td_node`, `delete_td_node`, `update_td_node_parameters`,
`exec_node_method`, `execute_python_script`, `get_td_classes`, `get_td_class_details`,
`get_td_module_help`.
Diagnostics: `get_cook_errors`, `get_error_summary`, `get_python_exceptions`.

Full signatures: [`../TOOLS.md`](../TOOLS.md). Protocol: [`../../MCP/COMM_LAYER.md`](../../MCP/COMM_LAYER.md).
