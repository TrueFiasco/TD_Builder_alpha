#!/usr/bin/env python3
"""Add file transfer capability to MCP server - returns built files as base64"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = 'C:/TD_Projects/kb_pipeline/mcp/unified_mcp_server.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add base64 import at the top
old_imports = "import json\nimport os"
new_imports = "import base64\nimport json\nimport os"
content = content.replace(old_imports, new_imports)

# 2. Replace the network_design success block to include file transfer
old_success_block = '''                    result = {
                        "success": True,
                        "builder": "ToeBuilderBridge",
                        "output_file": str(result_path),
                        "operators": op_count,
                        "connections": conn_count,
                        "features_used": {
                            "containers": len(network_design.get("containers", [])) > 0,
                            "embed_tox": any(
                                op.get("embed_tox")
                                for container in network_design.get("containers", [])
                                for op in container.get("operators", [])
                            )
                        }
                    }

                    return [TextContent(type="text", text=json.dumps(result, indent=2))]'''

new_success_block = '''                    # Check if file was actually created
                    if result_path is None or not Path(result_path).exists():
                        return [TextContent(type="text", text=json.dumps({
                            "success": False,
                            "builder": "ToeBuilderBridge",
                            "error": "Build completed but file was not created",
                            "attempted_path": str(result_path) if result_path else "None"
                        }, indent=2))]

                    # Read file and encode as base64 for transfer
                    file_data = None
                    file_size = Path(result_path).stat().st_size
                    if file_size < 10 * 1024 * 1024:  # Only transfer files under 10MB
                        with open(result_path, 'rb') as f:
                            file_data = base64.b64encode(f.read()).decode('utf-8')

                    result = {
                        "success": True,
                        "builder": "ToeBuilderBridge",
                        "output_file": str(result_path),
                        "file_size": file_size,
                        "operators": op_count,
                        "connections": conn_count,
                        "features_used": {
                            "containers": len(network_design.get("containers", [])) > 0,
                            "embed_tox": any(
                                op.get("embed_tox")
                                for container in network_design.get("containers", [])
                                for op in container.get("operators", [])
                            )
                        }
                    }

                    # Include file data if available
                    if file_data:
                        result["file_base64"] = file_data
                        result["transfer_note"] = "File included as base64. Decode and save to use."

                    return [TextContent(type="text", text=json.dumps(result, indent=2))]'''

content = content.replace(old_success_block, new_success_block)

# 3. Also update the converted network success block (for "network" format)
old_converted_success = '''                    result = {
                        "success": True,
                        "builder": "ToeBuilderBridge",
                        "output_file": str(result_path),
                        "operators": len(converted_design.get("operators", [])),
                        "connections": len(converted_design.get("connections", [])),
                        "converted_from": "network"
                    }

                    return [TextContent(type="text", text=json.dumps(result, indent=2))]'''

new_converted_success = '''                    # Check if file was actually created
                    if result_path is None or not Path(result_path).exists():
                        return [TextContent(type="text", text=json.dumps({
                            "success": False,
                            "builder": "ToeBuilderBridge",
                            "error": "Build completed but file was not created",
                            "attempted_path": str(result_path) if result_path else "None",
                            "converted_from": "network"
                        }, indent=2))]

                    # Read file and encode as base64 for transfer
                    file_data = None
                    file_size = Path(result_path).stat().st_size
                    if file_size < 10 * 1024 * 1024:  # Only transfer files under 10MB
                        with open(result_path, 'rb') as f:
                            file_data = base64.b64encode(f.read()).decode('utf-8')

                    result = {
                        "success": True,
                        "builder": "ToeBuilderBridge",
                        "output_file": str(result_path),
                        "file_size": file_size,
                        "operators": len(converted_design.get("operators", [])),
                        "connections": len(converted_design.get("connections", [])),
                        "converted_from": "network"
                    }

                    # Include file data if available
                    if file_data:
                        result["file_base64"] = file_data
                        result["transfer_note"] = "File included as base64. Decode and save to use."

                    return [TextContent(type="text", text=json.dumps(result, indent=2))]'''

content = content.replace(old_converted_success, new_converted_success)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify changes
checks = [
    ('base64 import', 'import base64' in content),
    ('file existence check', 'file was not created' in content),
    ('file_base64 field', 'file_base64' in content),
    ('transfer_note', 'transfer_note' in content),
]

print('File transfer update:')
all_passed = True
for name, passed in checks:
    status = 'PASS' if passed else 'FAIL'
    if not passed:
        all_passed = False
    print(f'  {status}: {name}')

if all_passed:
    print('\nSUCCESS: File transfer capability added')
else:
    print('\nWARNING: Some changes may not have applied')
