"""Format Converter - Hub for converting between all JSON format layers.

Enables seamless conversion:
- Layer 1 (Builder) ↔ Layer 2 (Extended)
- Layer 2 (Extended) ↔ Layer 3 (Canonical)
- Layer 2 (Extended) ↔ Layer 4 (Lossless)
"""

from typing import Dict, List, Any, Optional
from .models import (
    TDNetwork, Operator, Connection, Metadata, Position, Flags,
    OperatorFamily, FormatLayer, LosslessData, CanonicalData,
    Input, ExtraFile, ParameterValue, ExpressionLanguage, ParameterMode
)
from .operator_registry import OperatorRegistry


class FormatConverter:
    """
    Hub for converting between Builder, Extended, Canonical, and Lossless formats.

    Conversion flows:
    - Builder → Extended: Enrich with defaults from registry
    - Extended → Builder: Strip to essentials
    - Extended → Canonical: Compress with string tables
    - Canonical → Extended: Decompress
    - Extended → Lossless: Add file data (requires .toe.dir)
    - Lossless → Extended: Extract structure
    """

    def __init__(self, registry: Optional[OperatorRegistry] = None):
        """
        Initialize format converter.

        Args:
            registry: OperatorRegistry for validation and defaults
        """
        self.registry = registry or OperatorRegistry()

    # =========================================================================
    # Layer 1: Builder JSON ↔ Extended JSON
    # =========================================================================

    def from_builder(self, builder_json: Dict[str, Any]) -> TDNetwork:
        """
        Convert Builder JSON (Layer 1) → Extended JSON (Layer 2).

        Enriches simple builder format with:
        - Default flags
        - Resolved paths
        - Complete op_type strings
        - Default positions

        Args:
            builder_json: Builder JSON dict

        Returns:
            TDNetwork in Extended format
        """
        meta = builder_json.get("meta", {})
        operators_list = builder_json.get("operators", [])

        # Create metadata
        metadata = Metadata(
            project_name=meta.get("project_name", "untitled"),
            mode=meta.get("mode", "toe"),
            root_comp=meta.get("root_comp", "project1")
        )

        # Convert operators list to Operator objects
        operators = []
        for node in operators_list:
            operator = self._builder_node_to_operator(node, metadata.root_comp)
            operators.append(operator)

        # Extract connections from per-operator inputs (existing path)
        connections = self._extract_connections_from_operators(operators)

        # Also accept top-level `connections` array — same shape ToeBuilderBridge accepts.
        # Purely additive: if absent, behavior is unchanged.
        top_level = builder_json.get("connections") or []
        if top_level:
            seen = {(c.source, c.target, c.target_input) for c in connections}
            for conn_data in top_level:
                resolved = self._resolve_top_level_connection(
                    conn_data, operators, metadata.root_comp
                )
                if resolved is None:
                    continue
                key = (resolved.source, resolved.target, resolved.target_input)
                if key not in seen:
                    connections.append(resolved)
                    seen.add(key)

        # Create network
        network = TDNetwork(
            format_version="2.0.0",
            format_layer=FormatLayer.EXTENDED,
            metadata=metadata,
            operators=operators,
            connections=connections
        )

        return network

    def to_builder(self, network: TDNetwork) -> Dict[str, Any]:
        """
        Convert Extended JSON (Layer 2) → Builder JSON (Layer 1).

        Strips Extended format to essentials:
        - Remove default flags
        - Use local paths where possible
        - Remove op_type (redundant with family:type)
        - Remove positions (optional in builder)

        Args:
            network: TDNetwork in Extended format

        Returns:
            Builder JSON dict
        """
        builder = {
            "meta": {
                "project_name": network.metadata.project_name,
                "mode": network.metadata.mode,
                "root_comp": network.metadata.root_comp
            },
            "operators": []
        }

        for operator in network.operators:
            node = self._operator_to_builder_node(operator)
            builder["operators"].append(node)

        return builder

    def _builder_node_to_operator(self, node: Dict[str, Any], root_comp: str) -> Operator:
        """Convert builder node to Operator."""
        # Accept the AI-friendly builder shape: prefer explicit "path", but
        # fall back to "name" (what td_build_project accepts and what
        # td_validate/td_convert callers actually send). Without this,
        # name-only operators collapse to path "/" and fail schema with
        # "'' does not match ..." (cascading to duplicate-path errors).
        path = node.get("path") or node.get("name") or ""

        # Ensure absolute path
        if not path.startswith("/"):
            # If path already includes root_comp, don't duplicate
            if path.startswith(root_comp + "/") or path == root_comp:
                path = "/" + path
            else:
                path = f"/{path}"

        name = path.split("/")[-1]
        parent = "/".join(path.split("/")[:-1]) if "/" in path and path.count("/") > 1 else None

        # Parse family — accept either explicit `family` field or `family:type` colon-form
        family_str = node.get("family", "")
        type_str = node.get("type", "")
        if not family_str and ":" in type_str:
            family_str, type_str = type_str.split(":", 1)
        try:
            family = OperatorFamily(family_str)
        except ValueError:
            raise ValueError(f"Invalid operator family: {family_str!r} (node: {node!r})")

        type_name = type_str

        # Get flags (with defaults)
        flags_data = node.get("flags", {})
        flags = Flags(
            display=flags_data.get("display", False),
            render=flags_data.get("render", False),
            bypass=flags_data.get("bypass", False),
            lock=flags_data.get("lock", False)
        )

        # Get parameters
        parameters = self._deserialize_parameters(node.get("params", {}))

        # Optional position (so builder JSON can preserve network layout)
        position = None
        pos_data = node.get("position")
        if isinstance(pos_data, dict):
            viewport = pos_data.get("viewport")
            tile = pos_data.get("tile")
            if viewport is not None or tile is not None:
                position = Position(viewport=viewport, tile=tile)
        else:
            # Back-compat/alternate keys
            viewport = node.get("viewport")
            tile = node.get("tile")
            if viewport is not None or tile is not None:
                position = Position(viewport=viewport, tile=tile)

        # Optional TD-specific metadata (used by fixture pipelines)
        custom_data = {}
        td_data = node.get("td", {})
        if isinstance(td_data, dict):
            if "parlanguage" in td_data:
                custom_data["parlanguage"] = td_data["parlanguage"]

        # Optional extra files (fixture passthrough, e.g. `.table` / `.text`)
        extra_files = {}
        extra_files_data = node.get("extra_files", {})
        if isinstance(extra_files_data, dict):
            for ext, file_data in extra_files_data.items():
                if not isinstance(file_data, dict):
                    continue
                content = file_data.get("content")
                if content is None:
                    continue
                extra_files[ext] = ExtraFile(
                    content=content,
                    is_binary=bool(file_data.get("is_binary", False)),
                    encoding=file_data.get("encoding", "utf-8"),
                )

        # Get inputs (convert to Input objects)
        inputs_data = node.get("inputs", [])
        inputs = []
        if isinstance(inputs_data, list):
            for inp in inputs_data:
                if isinstance(inp, dict):
                    inputs.append(Input(
                        index=inp.get("index", 0),
                        src=inp.get("src", "")
                    ))

        return Operator(
            path=path,
            name=name,
            family=family,
            type=type_name,
            parent=parent,
            position=position,
            flags=flags,
            parameters=parameters,
            inputs=inputs,
            extra_files=extra_files,
            custom_data=custom_data,
        )

    def _operator_to_builder_node(self, operator: Operator) -> Dict[str, Any]:
        """Convert Operator to builder node."""
        # Use path as-is (already absolute)
        node = {
            "path": operator.path,
            "family": operator.family.value,
            "type": operator.type,
            "name": operator.name,
            "flags": {
                "bypass": operator.flags.bypass,
                "display": operator.flags.display,
                "render": operator.flags.render,
                "lock": operator.flags.lock
            }
        }

        # Preserve layout if present (optional in builder format)
        if operator.position and (operator.position.tile or operator.position.viewport):
            node["position"] = {
                "tile": operator.position.tile,
                "viewport": operator.position.viewport,
            }

        # Preserve TD-specific metadata if present
        if operator.custom_data:
            td_data = {}
            if "parlanguage" in operator.custom_data:
                td_data["parlanguage"] = operator.custom_data["parlanguage"]
            if td_data:
                node["td"] = td_data

        # Preserve extra files for fixture workflows (keep scoped to data-carrying types)
        if operator.extra_files:
            # `toeexpand` emits additional operator sidecars beyond `.text/.table` (e.g. GLSL `.oldacbo`, some `.data`).
            # Keep this list tight but sufficient for small tox/toe fixtures to rebuild/collapse reliably.
            kept_exts = {"table", "text", "data", "oldacbo"}
            extra = {}
            for ext, ef in operator.extra_files.items():
                if ext not in kept_exts:
                    continue
                extra[ext] = {
                    "content": ef.content,
                    "is_binary": ef.is_binary,
                    "encoding": ef.encoding,
                }
            if extra:
                node["extra_files"] = extra

        # Add parameters if any (non-defaults only in builder)
        if operator.parameters:
            node["params"] = self._serialize_parameters(operator.parameters)

        # Add inputs if any
        if operator.inputs:
            node["inputs"] = [
                {"index": inp.index, "src": inp.src}
                for inp in operator.inputs
            ]

        return node

    def _extract_connections_from_operators(self, operators: List[Operator]) -> List[Connection]:
        """Extract connections from operator inputs."""
        connections = []
        for operator in operators:
            for inp in operator.inputs:
                # Resolve source path
                source_path = inp.src
                if not source_path.startswith("/"):
                    # Relative - resolve to parent
                    if operator.parent:
                        source_path = f"{operator.parent}/{source_path}"
                    else:
                        source_path = f"/{source_path}"

                connections.append(Connection(
                    source=source_path,
                    target=operator.path,
                    target_input=inp.index
                ))
        return connections

    def _resolve_top_level_connection(
        self,
        conn_data: Dict[str, Any],
        operators: List[Operator],
        root_comp: str,
    ) -> Optional[Connection]:
        """Resolve a top-level builder connection ({from, to, [to_input]}) into a Connection.

        Accepts `from`/`to` (ToeBuilderBridge shape) or `source`/`target` (Connection-model
        shape). Returns None for malformed entries so the caller can skip silently —
        consistent with the rest of this module's tolerant parsing.
        """
        src_name = conn_data.get("from") or conn_data.get("source")
        dst_name = conn_data.get("to") or conn_data.get("target")
        if not src_name or not dst_name:
            return None

        target_input = int(
            conn_data.get("to_input",
            conn_data.get("target_input",
            conn_data.get("index", 0)))
        )
        source_output = int(
            conn_data.get("from_output",
            conn_data.get("source_output", 0))
        )

        return Connection(
            source=self._resolve_name_to_path(src_name, operators, root_comp),
            target=self._resolve_name_to_path(dst_name, operators, root_comp),
            source_output=source_output,
            target_input=target_input,
        )

    def _resolve_name_to_path(
        self,
        name: str,
        operators: List[Operator],
        root_comp: str,
    ) -> str:
        """Resolve a bare operator name to an absolute path using the parsed operators.

        Already-absolute paths pass through unchanged. Bare names match against the
        operator's `.name` field — first match wins. Falls back to `/<root_comp>/<name>`
        if no match.
        """
        if name.startswith("/"):
            return name
        for op in operators:
            if op.name == name:
                return op.path
        return f"/{root_comp}/{name}"

    # =========================================================================
    # Layer 3: Canonical JSON ↔ Extended JSON
    # =========================================================================

    def to_canonical(self, network: TDNetwork) -> Dict[str, Any]:
        """
        Convert Extended JSON (Layer 2) → Canonical JSON (Layer 3).

        Compresses using string tables for deduplication.

        Args:
            network: TDNetwork in Extended format

        Returns:
            Canonical JSON dict
        """
        # Build string table
        string_table = []
        string_map = {}  # str -> index

        def get_string_index(s: str) -> int:
            """Get or create string table index."""
            if s not in string_map:
                string_map[s] = len(string_table)
                string_table.append(s)
            return string_map[s]

        # Compress operators to array format
        compressed_nodes = []
        for operator in network.operators:
            node_record = [
                get_string_index(operator.path),          # 0: path
                get_string_index(operator.parent or ""),  # 1: parent
                get_string_index(operator.name),          # 2: name
                get_string_index(operator.family.value),  # 3: family
                get_string_index(operator.type),          # 4: type
                operator.position.viewport if operator.position else None,  # 5: viewport
                operator.position.tile if operator.position else None,      # 6: tile
                self._flags_to_bitmask(operator.flags),   # 7: flags bitmask
                self._serialize_parameters(operator.parameters)  # 8: parameters
            ]
            compressed_nodes.append(node_record)

        canonical = {
            "format_version": "2.0.0",
            "format_layer": "canonical",
            "metadata": {
                "project_name": network.metadata.project_name,
                "mode": network.metadata.mode
            },
            "string_table": string_table,
            "compressed_nodes": compressed_nodes,
            "connections": [
                {
                    "from": get_string_index(conn.source),
                    "to": get_string_index(conn.target),
                    "to_input": conn.target_input
                }
                for conn in network.connections
            ]
        }

        return canonical

    def from_canonical(self, canonical_json: Dict[str, Any]) -> TDNetwork:
        """
        Convert Canonical JSON (Layer 3) → Extended JSON (Layer 2).

        Decompresses string tables.

        Args:
            canonical_json: Canonical JSON dict

        Returns:
            TDNetwork in Extended format
        """
        string_table = canonical_json.get("string_table", [])
        compressed_nodes = canonical_json.get("compressed_nodes", [])

        # Create metadata
        meta = canonical_json.get("metadata", {})
        metadata = Metadata(
            project_name=meta.get("project_name", "untitled"),
            mode=meta.get("mode", "toe"),
            root_comp=meta.get("root_comp", "project1")
        )

        # Decompress operators
        operators = []
        for node_record in compressed_nodes:
            path = string_table[node_record[0]]
            parent_str = string_table[node_record[1]] if node_record[1] < len(string_table) else ""
            parent = parent_str if parent_str else None
            name = string_table[node_record[2]]
            family = OperatorFamily(string_table[node_record[3]])
            type_name = string_table[node_record[4]]
            viewport = node_record[5]
            tile = node_record[6]
            flags_bitmask = node_record[7]
            parameters = self._deserialize_parameters(node_record[8])

            position = Position(viewport=viewport, tile=tile) if (viewport or tile) else None
            flags = self._bitmask_to_flags(flags_bitmask)

            operator = Operator(
                path=path,
                name=name,
                family=family,
                type=type_name,
                parent=parent,
                position=position,
                flags=flags,
                parameters=parameters
            )
            operators.append(operator)

        # Decompress connections
        connections_data = canonical_json.get("connections", [])
        connections = []
        for conn_data in connections_data:
            connections.append(Connection(
                source=string_table[conn_data["from"]],
                target=string_table[conn_data["to"]],
                target_input=conn_data.get("to_input", 0)
            ))

        network = TDNetwork(
            format_version="2.0.0",
            format_layer=FormatLayer.EXTENDED,
            metadata=metadata,
            operators=operators,
            connections=connections
        )

        return network

    def _serialize_parameters(self, params: Any) -> Any:
        """Convert parameter values into JSON-serializable structures."""
        if isinstance(params, ParameterValue):
            data = {
                "value": params.value,
                "expression": params.expression,
                "language": params.language.value if params.language else None,
                "mode": params.mode.value if params.mode else None,
                "td_mode": getattr(params, "td_mode", None),
            }
            return {k: v for k, v in data.items() if v is not None}

        if isinstance(params, dict):
            return {k: self._serialize_parameters(v) for k, v in params.items()}

        if isinstance(params, list):
            return [self._serialize_parameters(v) for v in params]

        return params

    def _deserialize_parameters(self, params: Any) -> Any:
        """Convert JSON parameter objects into ParameterValue instances when applicable."""
        if isinstance(params, dict):
            keys = set(params.keys())

            # Heuristic: ParameterValue dicts use semantic keys; vector dicts usually use numeric string keys.
            # Important: plain parameter maps can legitimately contain keys like "language" or "mode",
            # so only treat a dict as a ParameterValue when it includes an actual payload key.
            is_param_value = (
                ("value" in keys or "expression" in keys)
                and bool(keys & {"expression", "mode", "language", "td_mode"})
                and keys.issubset({"value", "expression", "language", "mode", "td_mode"})
            )
            if is_param_value:
                mode_str = params.get("mode", ParameterMode.CONSTANT.value)
                lang_str = params.get("language", ExpressionLanguage.PYTHON.value)
                try:
                    mode = ParameterMode(mode_str)
                except ValueError:
                    mode = ParameterMode.CONSTANT
                try:
                    language = ExpressionLanguage(lang_str)
                except ValueError:
                    language = ExpressionLanguage.PYTHON

                td_mode = params.get("td_mode", None)
                if td_mode is not None:
                    try:
                        td_mode = int(td_mode)
                    except (TypeError, ValueError):
                        td_mode = None

                return ParameterValue(
                    value=params.get("value"),
                    expression=params.get("expression"),
                    language=language,
                    mode=mode,
                    td_mode=td_mode,
                )

            return {k: self._deserialize_parameters(v) for k, v in params.items()}

        if isinstance(params, list):
            return [self._deserialize_parameters(v) for v in params]

        return params

    def _flags_to_bitmask(self, flags: Flags) -> int:
        """Convert Flags to bitmask."""
        bitmask = 0
        if flags.display:
            bitmask |= 1  # bit 0
        if flags.render:
            bitmask |= 2  # bit 1
        if flags.bypass:
            bitmask |= 4  # bit 2
        if flags.lock:
            bitmask |= 8  # bit 3
        if flags.viewer:
            bitmask |= 16  # bit 4
        if flags.current:
            bitmask |= 32  # bit 5
        return bitmask

    def _bitmask_to_flags(self, bitmask: int) -> Flags:
        """Convert bitmask to Flags."""
        return Flags(
            display=bool(bitmask & 1),
            render=bool(bitmask & 2),
            bypass=bool(bitmask & 4),
            lock=bool(bitmask & 8),
            viewer=bool(bitmask & 16),
            current=bool(bitmask & 32)
        )

    # =========================================================================
    # Helper: Direct conversions
    # =========================================================================

    def builder_to_lossless(self, builder_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Direct conversion: Builder → Lossless.

        Note: Lossless requires .toe.dir file data, so this only creates structure.

        Args:
            builder_json: Builder JSON

        Returns:
            Extended JSON with lossless_data placeholder
        """
        network = self.from_builder(builder_json)
        network.format_layer = FormatLayer.LOSSLESS
        network.lossless_data = LosslessData()
        return network

    def builder_to_canonical(self, builder_json: Dict[str, Any]) -> Dict[str, Any]:
        """Direct conversion: Builder → Canonical."""
        network = self.from_builder(builder_json)
        return self.to_canonical(network)
