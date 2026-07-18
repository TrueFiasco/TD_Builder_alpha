"""Validation Pipeline - Orchestrates multi-stage validation.

Runs all 7 validation stages in sequence and aggregates results: schema,
semantic, grounding, reference, component-source, logical, TD-rules. The stage
COMMENTS below number to 5 because two arrived as "2.5" and "3.5" (grounding and
component-source, added in W3a/BUG-3) -- that labelling is why the count has been
repeatedly under-read as 5 or 6. The list length is 7; count `stages.append`.
"""

import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))

from typing import Dict, Any
from datetime import datetime

from core.models import ValidationReport, StageReport, TDNetwork
from core.operator_registry import OperatorRegistry

from .schema_validator import SchemaValidator
from .semantic_validator import SemanticValidator
from .grounding_validator import GroundingValidator
from .reference_validator import ReferenceValidator
from .component_source_validator import ComponentSourceValidator
from .logical_validator import LogicalValidator
from .td_rules_validator import TDRulesValidator


class ValidationPipeline:
    """
    Multi-stage validation pipeline.

    Runs stages in sequence:
    1.  Schema - JSON structure validation
    2.  Semantic - Operator/parameter existence
    2.5 Grounding - operator family-correctness vs live-TD KB grounding (advisory)
    3.  Reference - Connection/parent validity
    3.5 Component wiring - a component is never itself a data source (BUG-3)
    4.  Logical - Type compatibility, cycles
    5.  TD Rules - TouchDesigner-specific rules

    Stops on first failure (configurable).
    """

    def __init__(self, registry: OperatorRegistry = None, stop_on_error: bool = False):
        """
        Initialize validation pipeline.

        Args:
            registry: OperatorRegistry (creates new if None)
            stop_on_error: Stop pipeline on first error stage
        """
        self.registry = registry or OperatorRegistry()
        self.stop_on_error = stop_on_error

        # Initialize validators
        self.schema_validator = SchemaValidator()
        self.semantic_validator = SemanticValidator(self.registry)
        self.grounding_validator = GroundingValidator()
        self.reference_validator = ReferenceValidator()
        self.component_source_validator = ComponentSourceValidator()
        self.logical_validator = LogicalValidator(self.registry)
        self.td_rules_validator = TDRulesValidator(self.registry)

    def validate(self, network_json: Dict[str, Any], network_path: str = "network") -> ValidationReport:
        """
        Run complete validation pipeline.

        Args:
            network_json: Network JSON or TDNetwork
            network_path: Path to network (for reporting)

        Returns:
            ValidationReport with all stage results
        """
        stages = []
        total_errors = 0
        total_warnings = 0

        # Stage 1: Schema
        schema_report = self.schema_validator.validate(network_json)
        stages.append(schema_report)
        total_errors += len(schema_report.errors)
        total_warnings += len(schema_report.warnings)

        if self.stop_on_error and schema_report.status == "FAIL":
            return self._build_report(stages, network_path, total_errors, total_warnings, stopped=True)

        # Stage 2: Semantic
        semantic_report = self.semantic_validator.validate(network_json)
        stages.append(semantic_report)
        total_errors += len(semantic_report.errors)
        total_warnings += len(semantic_report.warnings)

        if self.stop_on_error and semantic_report.status == "FAIL":
            return self._build_report(stages, network_path, total_errors, total_warnings, stopped=True)

        # Stage 2.5: Grounding (family-correctness vs live-TD KB; advisory warnings only,
        # so it never gates a build — it surfaces the correct family/token to fix by hand).
        grounding_report = self.grounding_validator.validate(network_json)
        stages.append(grounding_report)
        total_errors += len(grounding_report.errors)
        total_warnings += len(grounding_report.warnings)

        # Stage 3: Reference
        reference_report = self.reference_validator.validate(network_json)
        stages.append(reference_report)
        total_errors += len(reference_report.errors)
        total_warnings += len(reference_report.warnings)

        if self.stop_on_error and reference_report.status == "FAIL":
            return self._build_report(stages, network_path, total_errors, total_warnings, stopped=True)

        # Stage 3.5: Component wiring — a component is never itself a data source (BUG-3).
        # A bare component name in a connection SOURCE can never bind (TD drops it); this is
        # the static, pre-build half of the builder's build-time fail-loud.
        component_report = self.component_source_validator.validate(network_json)
        stages.append(component_report)
        total_errors += len(component_report.errors)
        total_warnings += len(component_report.warnings)

        if self.stop_on_error and component_report.status == "FAIL":
            return self._build_report(stages, network_path, total_errors, total_warnings, stopped=True)

        # Stage 4: Logical
        logical_report = self.logical_validator.validate(network_json)
        stages.append(logical_report)
        total_errors += len(logical_report.errors)
        total_warnings += len(logical_report.warnings)

        if self.stop_on_error and logical_report.status == "FAIL":
            return self._build_report(stages, network_path, total_errors, total_warnings, stopped=True)

        # Stage 5: TD Rules
        td_rules_report = self.td_rules_validator.validate(network_json)
        stages.append(td_rules_report)
        total_errors += len(td_rules_report.errors)
        total_warnings += len(td_rules_report.warnings)

        return self._build_report(stages, network_path, total_errors, total_warnings)

    def _build_report(self, stages, network_path, total_errors, total_warnings, stopped=False) -> ValidationReport:
        """Build final validation report."""
        overall_status = "PASS" if total_errors == 0 else "FAIL"
        stages_passed = sum(1 for s in stages if s.status == "PASS")
        stages_failed = len(stages) - stages_passed

        summary = {
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "stages_passed": stages_passed,
            "stages_failed": stages_failed,
            "stopped_early": stopped
        }

        return ValidationReport(
            overall_status=overall_status,
            timestamp=datetime.now().isoformat(),
            network=network_path,
            summary=summary,
            stages=stages
        )

    def validate_stage(self, stage_name: str, network_json: Dict[str, Any]) -> StageReport:
        """
        Run single validation stage.

        Args:
            stage_name: Stage name (schema, semantic, reference, logical, td_rules)
            network_json: Network JSON

        Returns:
            StageReport for that stage
        """
        validators = {
            "schema": self.schema_validator,
            "semantic": self.semantic_validator,
            "grounding": self.grounding_validator,
            "reference": self.reference_validator,
            "component_wiring": self.component_source_validator,
            "logical": self.logical_validator,
            "td_rules": self.td_rules_validator
        }

        validator = validators.get(stage_name)
        if not validator:
            raise ValueError(f"Unknown stage: {stage_name}. Use one of: {list(validators.keys())}")

        return validator.validate(network_json)


def validate_network(network_json: Dict[str, Any],
                     registry: OperatorRegistry = None,
                     stop_on_error: bool = False,
                     network_path: str = "network") -> ValidationReport:
    """
    Convenience function to validate network through complete pipeline.

    Args:
        network_json: Network JSON or TDNetwork
        registry: Optional OperatorRegistry
        stop_on_error: Stop on first error stage
        network_path: Path to network (for reporting)

    Returns:
        ValidationReport
    """
    pipeline = ValidationPipeline(registry, stop_on_error)
    return pipeline.validate(network_json, network_path)


def print_validation_report(report: ValidationReport, verbose: bool = True):
    """
    Print validation report in human-readable format.

    Args:
        report: ValidationReport to print
        verbose: Print detailed errors
    """
    print("=" * 70)
    print("VALIDATION REPORT")
    print("=" * 70)
    print(f"Network: {report.network}")
    print(f"Timestamp: {report.timestamp}")
    print(f"Status: {report.overall_status}")
    print(f"\nSummary:")
    print(f"  Errors: {report.summary['total_errors']}")
    print(f"  Warnings: {report.summary['total_warnings']}")
    print(f"  Stages passed: {report.summary['stages_passed']}")
    print(f"  Stages failed: {report.summary['stages_failed']}")

    print(f"\nStages:")
    for stage in report.stages:
        status_symbol = "[OK]" if stage.status == "PASS" else "[FAIL]"
        print(f"  {status_symbol} {stage.stage}: {len(stage.errors)} errors, {len(stage.warnings)} warnings")

    if verbose and report.total_errors > 0:
        print(f"\nErrors:")
        for error in report.get_errors():
            print(f"  [{error.code}] {error.message}")
            if error.location:
                print(f"    Location: {error.location}")
            if error.path:
                print(f"    Path: {error.path}")
            if error.suggestion:
                print(f"    Suggestion: {error.suggestion}")
            print()

    if verbose and report.total_warnings > 0:
        print(f"Warnings:")
        for warning in report.get_warnings():
            print(f"  [{warning.code}] {warning.message}")
            if warning.suggestion:
                print(f"    Suggestion: {warning.suggestion}")
            print()

    print("=" * 70)
