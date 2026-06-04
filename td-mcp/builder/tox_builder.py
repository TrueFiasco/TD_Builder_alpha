"""
TOX Builder - Build TouchDesigner .tox component files from design specs.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

TOECOLLAPSE = "C:/Program Files/Derivative/TouchDesigner/bin/toecollapse.exe"

from .toe_builder_bridge import ToeBuilderBridge


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

        self.log("[1/4] Writing build file...")
        build_content = """version 099
build 2023.11880
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
            for idx, op in enumerate(flat_operators):
                self._write_operator(op, component_name, idx)

        for container in network.get("containers", []):
            self._write_container(container, component_name)

        toc_path = self._write_tox_toc(component_name)
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

        if not Path(TOECOLLAPSE).exists():
            self.log(f"[ERROR] toecollapse not found at: {TOECOLLAPSE}")
            return None

        # Pass the .toc file path, not the .dir directory
        toc_path = self.output_dir / f"{component_name}.tox.toc"
        result = subprocess.run([TOECOLLAPSE, str(toc_path)], capture_output=True, text=True)

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
