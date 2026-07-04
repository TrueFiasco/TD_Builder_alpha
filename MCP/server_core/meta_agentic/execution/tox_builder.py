"""
TOX Builder - Build TouchDesigner .tox component files from design specs.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from paths import resolve_td_tool, td_tool_missing_error

from .toe_builder_bridge import ToeBuilderBridge

# Hang-guard for the toecollapse subprocess. Generous (toecollapse is normally fast);
# this only catches a genuinely stuck process so the build can't block forever. NOTE:
# the MCP *client* may impose a much shorter tool-call timeout (~45s) that the server
# cannot override — on a client timeout the .tox usually still completes on disk.
COLLAPSE_TIMEOUT_S = 300


class ToxBuilder(ToeBuilderBridge):
    """Builder for TOX (component) files."""

    def build_tox(self, design: dict, component_name: str = None) -> Optional[Path]:
        """Convert TD Designer network_design JSON to TOX file."""
        self.log("=" * 60)
        self.log("Building TOX from TD Designer output")
        self.log("=" * 60)

        network = design.get("network_design", design)
        component_name = component_name or network.get("project", "component")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.project_dir = self.output_dir / f"{component_name}.tox.dir"
        if self.project_dir.exists():
            shutil.rmtree(self.project_dir)
        self.project_dir.mkdir(parents=True)
        self.toc_entries = []

        self._build_connection_map(network.get("connections", []))
        self._build_expression_map(network.get("expressions", []))
        # BUG-012 FIX: Extract table_data for Table DAT operators
        self.table_data_map = network.get("table_data", {})

        self.log("[1/4] Writing build file...")
        build_content = """version 099
build 2025.31760
time Fri Dec 20 10:00:00 2025
osname Windows
osversion 10
"""
        self._write_file(".build", build_content)

        self.log("[2/4] Creating root component...")
        comp_n = """COMP:base
tile 0 0 200 150
flags =  parlanguage 0
end
"""
        self._write_file(f"{component_name}.n", comp_n)
        parm_content = """?
?
"""
        self._write_file(f"{component_name}.parm", parm_content)
        (self.project_dir / component_name).mkdir(exist_ok=True)

        flat_operators = network.get("operators", [])
        if flat_operators:
            self.log(f"[3/4] Writing {len(flat_operators)} operators...")

            # =================================================================
            # BUG-022 FIX: Respect 'parent' field for operator hierarchy
            # Group operators by parent, write containers first, then children
            # =================================================================

            # Step 1: Identify parent containers and group children
            parent_containers = {}  # parent_name -> list of child operators
            root_operators = []     # operators without parent field
            container_ops = {}      # name -> operator (for container creation)

            for op in flat_operators:
                parent = op.get("parent")
                if parent:
                    # Normalize parent name (strip leading slashes, path prefixes)
                    parent = parent.lstrip("/").split("/")[-1]
                    if parent not in parent_containers:
                        parent_containers[parent] = []
                    parent_containers[parent].append(op)
                else:
                    root_operators.append(op)
                    # Track if this is a container that will have children
                    container_ops[op.get("name")] = op

            # Step 2: Write parent containers first (create directories)
            for parent_name in parent_containers.keys():
                if parent_name in container_ops:
                    # Parent is in our operators list, write it as container
                    parent_op = container_ops[parent_name]
                    container_path = f"{component_name}/{parent_name}"

                    # Determine container type/position. Honour the declared type/family via
                    # the shared resolver (BUG 2) instead of a blind COMP:{op_type}, so e.g.
                    # type:"geometry" -> COMP:geo (not COMP:geometry).
                    op_type = parent_op.get("type", "base")
                    family = parent_op.get("family", "COMP")
                    position = parent_op.get("position", [0, 0])
                    td_type = self._map_op_type(op_type, component_name, family)

                    # Write container .n file (honor the parent COMP's render/display flags — BUG-2)
                    n_content = f"""{td_type}
tile {position[0]} {position[1]} 200 150
flags =  {self._flags_tokens(parent_op.get("flags", {}) or {})}parlanguage 0
end
"""
                    self._write_file(f"{container_path}.n", n_content)
                    # Apply the parent container's own parameters (instancing/material/...).
                    parm_lines = ["?"]
                    parm_lines += self._param_lines(parent_op.get("parameters", {}) or {}, td_type,
                                                    op_type, container_path, component_name, parent_name)
                    parm_lines.append("?")
                    self._write_file(f"{container_path}.parm", "\n".join(parm_lines) + "\n")

                    # Create container directory
                    (self.project_dir / container_path).mkdir(parents=True, exist_ok=True)
                    self.log(f"    Created container: {parent_name}")
                else:
                    # Parent not in operators list - create implicit container
                    container_path = f"{component_name}/{parent_name}"
                    n_content = f"""COMP:base
tile 0 0 200 150
flags =  parlanguage 0
end
"""
                    self._write_file(f"{container_path}.n", n_content)
                    self._write_file(f"{container_path}.parm", "?\n?\n")
                    (self.project_dir / container_path).mkdir(parents=True, exist_ok=True)
                    self.log(f"    Created implicit container: {parent_name}")

            # Step 3: Write root-level operators (excluding ones we made into containers)
            for idx, op in enumerate(root_operators):
                op_name = op.get("name")
                if op_name not in parent_containers:
                    # Not a parent container, write as regular operator
                    self._write_operator(op, component_name, idx)

            # Step 4: Write child operators into their parent containers
            for parent_name, children in parent_containers.items():
                container_path = f"{component_name}/{parent_name}"
                for idx, op in enumerate(children):
                    self._write_operator(op, container_path, idx)

        for container in network.get("containers", []):
            self._write_container(container, component_name)

        toc_path = self._write_tox_toc(component_name)
        self._write_component_summary(component_name)
        tox_path = self._collapse_tox(component_name)

        if tox_path:
            self.log("=" * 60)
            self.log(f"[SUCCESS] Created: {tox_path}")
            self.log(f"         Size: {tox_path.stat().st_size} bytes")
            self.log("=" * 60)

        return tox_path

    def _toc_sort_key(self, filepath):
        ext_priority = {".n": 0, ".cparm": 1, ".parm": 2, ".panel": 3, ".network": 4}
        parts = filepath.rsplit(".", 1)
        if len(parts) == 2:
            ext = "." + parts[1]
            base = parts[0]
        else:
            ext = ""
            base = filepath
        priority = ext_priority.get(ext, 5)
        depth = filepath.count("/") + filepath.count("\\")
        return (depth, base, priority, filepath)

    def _write_tox_toc(self, component_name: str) -> Path:
        self.log("[4/4] Writing TOC...")
        sorted_entries = sorted(self.toc_entries, key=self._toc_sort_key)
        header = "# 4 0 0 0 1"
        lines = [header] + sorted_entries
        toc_content = "\n".join(lines) + "\n"
        toc_path = self.output_dir / f"{component_name}.tox.toc"
        toc_path.write_text(toc_content, encoding="utf-8", newline="\n")
        self.log(f"  Created TOC with {len(sorted_entries)} entries")
        return toc_path

    def _collapse_tox(self, component_name: str) -> Optional[Path]:
        self.log("[5/4] Collapsing to TOX...")
        tox_path = self.output_dir / f"{component_name}.tox"
        if tox_path.exists():
            tox_path.unlink()

        toecollapse = resolve_td_tool("toecollapse")
        if toecollapse is None:
            self.log(f"[ERROR] {td_tool_missing_error('toecollapse')}")
            return None

        # Pass the .toc file path, not the .dir directory
        toc_path = self.output_dir / f"{component_name}.tox.toc"
        try:
            result = subprocess.run(
                [str(toecollapse), str(toc_path)],
                capture_output=True, text=True, timeout=COLLAPSE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            # A genuinely stuck toecollapse — fail cleanly instead of blocking forever.
            self.log(
                f"[ERROR] toecollapse exceeded {COLLAPSE_TIMEOUT_S}s and was aborted. "
                f"If your MCP client also reported a timeout (~45s) the build may still have "
                f"completed on disk at {tox_path} — check there before rebuilding."
            )
            return None

        # Check for subprocess errors
        if result.returncode != 0:
            self.log(f"[ERROR] toecollapse failed with return code {result.returncode}")
            if result.stderr:
                self.log(f"  stderr: {result.stderr}")
            return None

        if tox_path.exists() and tox_path.stat().st_size > 50:
            return tox_path
        else:
            self.log(f"[ERROR] Collapse failed: {result.stderr}")
            return None


def build_tox_from_design(design: dict, output_dir: Path, component_name: str = None) -> Optional[Path]:
    """Convenience function to build TOX from TD Designer output."""
    builder = ToxBuilder(output_dir)
    return builder.build_tox(design, component_name)
