"""Operator Registry - Central source of truth for operator metadata.

Loads operator specifications from the TouchDesigner knowledge base
(td_universal_parsed_enriched.json — the canonical superset; falls back to
td_universal_parsed.json) and provides query methods for validation
and parameter schema lookup.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from .models import OperatorSpec, ParamSpec, OperatorFamily


class OperatorRegistry:
    """
    Queryable registry of all TouchDesigner operators with full parameter schemas.

    Loads from META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed_enriched.json
    (the canonical superset the live MCP server also uses; KBU_REPORT.md proves
    it is a strict additive superset of td_universal_parsed.json).
    """

    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize operator registry.

        Args:
            registry_path: Path to the operator KB JSON (auto-detect if None).
                Prefers the enriched superset; falls back to the base parsed file.
        """
        if registry_path is None:
            # Prefer the consolidated KB bundle (repo-root/KB/operators.json =
            # the enriched superset). Fall back to the legacy
            # META_AGENTIC_TOOL/data/wiki_docs layout (pre_alpha baseline).
            root = Path(__file__).resolve().parents[2]
            kb_ops = root / "KB" / "operators.json"
            if kb_ops.exists():
                registry_path = kb_ops
            else:
                legacy = root / "META_AGENTIC_TOOL" / "data" / "wiki_docs"
                enriched = legacy / "td_universal_parsed_enriched.json"
                registry_path = enriched if enriched.exists() else legacy / "td_universal_parsed.json"

        self.registry_path = Path(registry_path)
        self.operators: Dict[str, OperatorSpec] = {}  # Key: "FAMILY:type"
        self._family_index: Dict[OperatorFamily, List[str]] = {}  # Index by family

        self._load_registry()

    def _load_registry(self):
        """Load operator specifications from JSON."""
        if not self.registry_path.exists():
            raise FileNotFoundError(f"Operator registry not found: {self.registry_path}")

        with open(self.registry_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        operators_data = data.get("operators", [])

        for op_data in operators_data:
            if op_data.get("type") != "operator":
                continue

            name = op_data.get("name", "")
            family_str = op_data.get("family", "")
            summary = op_data.get("summary", "")

            # Parse family
            try:
                family = OperatorFamily(family_str)
            except ValueError:
                # Skip unknown families
                continue

            # Determine specific type from name
            # Convert "Noise CHOP" -> "noise"
            specific_type = self._extract_type_from_name(name, family_str)

            if not specific_type:
                continue

            op_type = f"{family.value}:{specific_type}"

            # Parse parameters
            parameters = []
            for param_data in op_data.get("parameters", []):
                param_spec = ParamSpec(
                    code=param_data.get("code", ""),
                    display_name=param_data.get("display_name", ""),
                    description=param_data.get("description", ""),
                    section=param_data.get("section", "")
                )
                parameters.append(param_spec)

            # Create operator spec
            is_comp = family == OperatorFamily.COMP
            operator_spec = OperatorSpec(
                name=name,
                family=family,
                op_type=op_type,
                summary=summary,
                parameters=parameters,
                is_comp=is_comp
            )

            # Store in registry
            self.operators[op_type] = operator_spec

            # Update family index
            if family not in self._family_index:
                self._family_index[family] = []
            self._family_index[family].append(op_type)

        # Post-process known gaps (e.g., Constant CHOP multi-channel params)
        self._extend_constant_params()

    def _extract_type_from_name(self, name: str, family: str) -> Optional[str]:
        """
        Extract specific type from operator name.

        Args:
            name: Display name (e.g., "Noise CHOP", "Audio File In CHOP")
            family: Family string (e.g., "CHOP")

        Returns:
            Lowercase type (e.g., "noise", "audiofilein") or None
        """
        # Remove family suffix
        if name.endswith(f" {family}"):
            name = name[:-len(family)-1]  # Remove " FAMILY"

        # Convert to lowercase, remove spaces
        type_name = name.lower().replace(" ", "")

        return type_name if type_name else None

    def get_operator(self, family: OperatorFamily, type_name: str) -> Optional[OperatorSpec]:
        """
        Get full operator specification.

        Args:
            family: Operator family
            type_name: Specific type (e.g., "noise")

        Returns:
            OperatorSpec or None if not found
        """
        op_type = f"{family.value}:{type_name}"
        return self.operators.get(op_type)

    def get_operator_by_type(self, op_type: str) -> Optional[OperatorSpec]:
        """
        Get operator by full type string.

        Args:
            op_type: Full type "FAMILY:type" (e.g., "CHOP:noise")

        Returns:
            OperatorSpec or None if not found
        """
        return self.operators.get(op_type)

    def validate_operator_type(self, family: OperatorFamily, type_name: str) -> bool:
        """
        Check if operator type exists.

        Args:
            family: Operator family
            type_name: Specific type

        Returns:
            True if operator exists
        """
        return self.get_operator(family, type_name) is not None

    def get_parameters(self, family: OperatorFamily, type_name: str) -> List[ParamSpec]:
        """
        Get all parameters for operator.

        Args:
            family: Operator family
            type_name: Specific type

        Returns:
            List of parameter specifications
        """
        operator = self.get_operator(family, type_name)
        return operator.parameters if operator else []

    def get_parameter(self, family: OperatorFamily, type_name: str, param_code: str) -> Optional[ParamSpec]:
        """
        Get specific parameter specification.

        Args:
            family: Operator family
            type_name: Specific type
            param_code: Parameter code

        Returns:
            ParamSpec or None if not found
        """
        operator = self.get_operator(family, type_name)
        if operator:
            return operator.get_parameter(param_code)
        return None

    def has_parameter(self, family: OperatorFamily, type_name: str, param_code: str) -> bool:
        """
        Check if parameter exists for operator.

        Args:
            family: Operator family
            type_name: Specific type
            param_code: Parameter code

        Returns:
            True if parameter exists
        """
        return self.get_parameter(family, type_name, param_code) is not None

    def get_operators_by_family(self, family: OperatorFamily) -> List[OperatorSpec]:
        """
        Get all operators in a family.

        Args:
            family: Operator family

        Returns:
            List of operator specifications
        """
        op_types = self._family_index.get(family, [])
        return [self.operators[op_type] for op_type in op_types]

    def search_operators(self, query: str) -> List[OperatorSpec]:
        """
        Search operators by name or type.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching operator specifications
        """
        query_lower = query.lower()
        results = []

        for operator in self.operators.values():
            if (query_lower in operator.name.lower() or
                query_lower in operator.op_type.lower()):
                results.append(operator)

        return results

    def get_all_operator_types(self) -> List[str]:
        """
        Get list of all operator types.

        Returns:
            List of "FAMILY:type" strings
        """
        return list(self.operators.keys())

    def get_family_from_type(self, op_type: str) -> Optional[OperatorFamily]:
        """
        Extract family from operator type string.

        Args:
            op_type: Full type "FAMILY:type"

        Returns:
            OperatorFamily or None if invalid
        """
        if ":" not in op_type:
            return None

        family_str = op_type.split(":")[0]
        try:
            return OperatorFamily(family_str)
        except ValueError:
            return None

    def is_comp(self, family: OperatorFamily, type_name: str) -> bool:
        """
        Check if operator is a COMP (can contain children).

        Args:
            family: Operator family
            type_name: Specific type

        Returns:
            True if operator can have children
        """
        operator = self.get_operator(family, type_name)
        return operator.is_comp if operator else False

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with counts by family, etc.
        """
        stats = {
            "total_operators": len(self.operators),
            "by_family": {}
        }

        for family, op_types in self._family_index.items():
            stats["by_family"][family.value] = len(op_types)

        return stats

    def __len__(self) -> int:
        """Get total number of operators."""
        return len(self.operators)

    def __contains__(self, op_type: str) -> bool:
        """Check if operator type exists."""
        return op_type in self.operators

    def _extend_constant_params(self):
        """Extend Constant CHOP to allow multiple channel name/value pairs (const1-const9)."""
        op_type = "CHOP:constant"
        op = self.operators.get(op_type)
        if not op:
            return

        existing = {p.code for p in op.parameters}
        for i in range(1, 10):
            name_code = f"const{i}name"
            value_code = f"const{i}value"
            if name_code not in existing:
                op.parameters.append(
                    ParamSpec(
                        code=name_code,
                        display_name=f"Name{i}",
                        description=f"Channel {i} name",
                        section="Parameters - Constant Page",
                        param_type="string",
                    )
                )
            if value_code not in existing:
                op.parameters.append(
                    ParamSpec(
                        code=value_code,
                        display_name=f"Value{i}",
                        description=f"Channel {i} value",
                        section="Parameters - Constant Page",
                        param_type="float",
                    )
                )

    def __repr__(self) -> str:
        """String representation."""
        return f"<OperatorRegistry: {len(self.operators)} operators from {self.registry_path}>"


# Global registry instance (lazy-loaded)
_global_registry: Optional[OperatorRegistry] = None


def get_global_registry() -> OperatorRegistry:
    """
    Get or create global operator registry instance.

    Returns:
        Global OperatorRegistry
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = OperatorRegistry()
    return _global_registry
