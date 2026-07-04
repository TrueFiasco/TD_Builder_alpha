"""
Blackboard: Central PROJECT DOCUMENT state management.

The blackboard is the single source of truth for all workflow state.
All experts read from and write to specific sections of the blackboard.

Sections:
    §1 Requirements     - User intent + constraints
    §2 Creative Vision  - Artistic direction, mood, style
    §3 Technical Approach - Techniques, tradeoffs
    §4 Available Resources - Operators, palette, patterns
    §5 Network Design   - JSON network + descriptions
    §6 Validation History - All critic reviews
    §7 Build Artifacts  - Paths, validation results
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import json
import yaml
import hashlib


class SectionID(Enum):
    """Blackboard section identifiers."""
    REQUIREMENTS = "§1_requirements"
    CREATIVE_VISION = "§2_creative_vision"
    TECHNICAL_APPROACH = "§3_technical_approach"
    AVAILABLE_RESOURCES = "§4_available_resources"
    NETWORK_DESIGN = "§5_network_design"
    VALIDATION_HISTORY = "§6_validation_history"
    BUILD_ARTIFACTS = "§7_build_artifacts"


class Phase(Enum):
    """Workflow phases."""
    INIT = "init"
    CREATIVE = "creative"
    TECHNICAL = "technical"
    RESOURCES = "resources"
    DESIGN = "design"
    BUILD = "build"
    COMPLETE = "complete"


@dataclass
class SectionVersion:
    """A single version of a section's content."""
    version: int
    content: dict
    author: str
    timestamp: str
    score: Optional[float] = None
    locked: bool = False
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            content_str = json.dumps(self.content, sort_keys=True)
            self.hash = hashlib.sha256(content_str.encode()).hexdigest()[:16]


@dataclass
class BlockingIssue:
    """An issue blocking progress to the next phase."""
    id: str
    section: SectionID
    severity: str  # "high", "medium", "low"
    classification: str  # "creative", "technical", "design", "validation"
    description: str
    created_at: str
    resolved: bool = False
    resolution: Optional[str] = None
    resolved_at: Optional[str] = None


@dataclass
class Section:
    """A blackboard section with version history."""
    id: SectionID
    versions: list[SectionVersion] = field(default_factory=list)
    locked: bool = False
    lock_reason: Optional[str] = None

    @property
    def current(self) -> Optional[SectionVersion]:
        """Get the most recent version."""
        return self.versions[-1] if self.versions else None

    @property
    def current_content(self) -> dict:
        """Get current version's content or empty dict."""
        return self.current.content if self.current else {}

    @property
    def version_count(self) -> int:
        """Number of versions."""
        return len(self.versions)


class Blackboard:
    """
    Central PROJECT DOCUMENT state storage.

    Usage:
        bb = Blackboard(project_name="audio_reactive_test")
        bb.write(SectionID.REQUIREMENTS, {"prompt": "..."}, author="user")
        req = bb.read(SectionID.REQUIREMENTS)
        bb.lock(SectionID.REQUIREMENTS, reason="Approved by critic")
    """

    def __init__(self, project_name: str, persist_path: Optional[Path] = None):
        self.project_name = project_name
        self.persist_path = persist_path
        self.created_at = datetime.utcnow().isoformat() + "Z"

        # Initialize all sections
        self.sections: dict[SectionID, Section] = {
            sid: Section(id=sid) for sid in SectionID
        }

        # Workflow state
        self.current_phase = Phase.INIT
        self.iteration = 0
        self.blocking_issues: list[BlockingIssue] = []

        # Audit trail
        self.events: list[dict] = []

        # Load from disk if exists
        if persist_path and persist_path.exists():
            self._load()

    def read(self, section_id: SectionID) -> dict:
        """
        Read current content from a section.

        Args:
            section_id: Which section to read

        Returns:
            Current content as dict, or empty dict if no content
        """
        section = self.sections[section_id]
        self._log_event("read", section_id=section_id.value)
        return section.current_content

    def read_version(self, section_id: SectionID, version: int) -> Optional[dict]:
        """Read a specific version of a section."""
        section = self.sections[section_id]
        if 0 <= version < len(section.versions):
            return section.versions[version].content
        return None

    def write(
        self,
        section_id: SectionID,
        content: dict,
        author: str,
        score: Optional[float] = None
    ) -> SectionVersion:
        """
        Write new content to a section.

        Args:
            section_id: Which section to write
            content: New content
            author: Who is writing (expert name or "user")
            score: Optional quality score

        Returns:
            The new version created

        Raises:
            PermissionError: If section is locked
        """
        section = self.sections[section_id]

        if section.locked:
            raise PermissionError(
                f"Section {section_id.value} is locked: {section.lock_reason}"
            )

        version = SectionVersion(
            version=section.version_count,
            content=content,
            author=author,
            timestamp=datetime.utcnow().isoformat() + "Z",
            score=score
        )

        section.versions.append(version)

        self._log_event(
            "write",
            section_id=section_id.value,
            version=version.version,
            author=author,
            score=score,
            hash=version.hash
        )

        if self.persist_path:
            self._save()

        return version

    def lock(self, section_id: SectionID, reason: str):
        """Lock a section to prevent further writes."""
        section = self.sections[section_id]
        section.locked = True
        section.lock_reason = reason

        if section.current:
            section.current.locked = True

        self._log_event("lock", section_id=section_id.value, reason=reason)

        if self.persist_path:
            self._save()

    def unlock(self, section_id: SectionID, reason: str):
        """Unlock a section for phase reopening."""
        section = self.sections[section_id]
        section.locked = False
        section.lock_reason = None

        self._log_event("unlock", section_id=section_id.value, reason=reason)

        if self.persist_path:
            self._save()

    def add_blocking_issue(
        self,
        section_id: SectionID,
        severity: str,
        classification: str,
        description: str
    ) -> BlockingIssue:
        """Add a blocking issue to the queue."""
        issue = BlockingIssue(
            id=f"ISSUE-{len(self.blocking_issues) + 1:04d}",
            section=section_id,
            severity=severity,
            classification=classification,
            description=description,
            created_at=datetime.utcnow().isoformat() + "Z"
        )

        self.blocking_issues.append(issue)

        self._log_event(
            "add_issue",
            issue_id=issue.id,
            section_id=section_id.value,
            severity=severity,
            classification=classification
        )

        if self.persist_path:
            self._save()

        return issue

    def resolve_issue(self, issue_id: str, resolution: str):
        """Mark a blocking issue as resolved."""
        for issue in self.blocking_issues:
            if issue.id == issue_id:
                issue.resolved = True
                issue.resolution = resolution
                issue.resolved_at = datetime.utcnow().isoformat() + "Z"

                self._log_event(
                    "resolve_issue",
                    issue_id=issue_id,
                    resolution=resolution
                )

                if self.persist_path:
                    self._save()
                return

        raise ValueError(f"Issue {issue_id} not found")

    def get_unresolved_issues(self) -> list[BlockingIssue]:
        """Get all unresolved blocking issues."""
        return [i for i in self.blocking_issues if not i.resolved]

    def get_issues_for_section(self, section_id: SectionID) -> list[BlockingIssue]:
        """Get unresolved issues for a specific section."""
        return [
            i for i in self.blocking_issues
            if i.section == section_id and not i.resolved
        ]

    def set_phase(self, phase: Phase):
        """Update current workflow phase."""
        old_phase = self.current_phase
        self.current_phase = phase

        self._log_event(
            "phase_transition",
            from_phase=old_phase.value,
            to_phase=phase.value
        )

        if self.persist_path:
            self._save()

    def increment_iteration(self):
        """Increment the iteration counter."""
        self.iteration += 1

        self._log_event("iteration", count=self.iteration)

        if self.persist_path:
            self._save()

    def get_context_for_expert(self, expert_id: str) -> dict:
        """
        Get the relevant blackboard context for a specific expert.

        Expert section access is defined in AGENT_INTERFACE.md.
        """
        # Section access per expert
        access_map = {
            "creative_expert": [SectionID.REQUIREMENTS],
            "cg_expert": [SectionID.REQUIREMENTS, SectionID.CREATIVE_VISION],
            "critic": [
                SectionID.REQUIREMENTS,
                SectionID.CREATIVE_VISION,
                SectionID.TECHNICAL_APPROACH,
                SectionID.AVAILABLE_RESOURCES,
                SectionID.NETWORK_DESIGN
            ],
            "td_designer": [
                SectionID.REQUIREMENTS,
                SectionID.CREATIVE_VISION,
                SectionID.TECHNICAL_APPROACH,
                SectionID.AVAILABLE_RESOURCES
            ],
            "td_glsl_expert": [
                SectionID.TECHNICAL_APPROACH,
                SectionID.NETWORK_DESIGN
            ],
            "td_python_expert": [
                SectionID.TECHNICAL_APPROACH,
                SectionID.NETWORK_DESIGN
            ],
            "network_builder": [SectionID.NETWORK_DESIGN],
            "summary_generator": [
                SectionID.NETWORK_DESIGN,
                SectionID.BUILD_ARTIFACTS
            ],
            "creative_orchestrator": list(SectionID),  # All sections
        }

        sections_to_read = access_map.get(expert_id, [])

        context = {
            "blackboard": {},
            "current_state": {
                "phase": self.current_phase.value,
                "iteration": self.iteration,
                "blocking_issues": [
                    {
                        "id": i.id,
                        "section": i.section.value,
                        "severity": i.severity,
                        "description": i.description
                    }
                    for i in self.get_unresolved_issues()
                ]
            }
        }

        for section_id in sections_to_read:
            section = self.sections[section_id]
            context["blackboard"][section_id.value] = {
                "current": section.current_content,
                "version": section.version_count - 1 if section.versions else -1,
                "score": section.current.score if section.current else None,
                "locked": section.locked
            }

        return context

    def to_dict(self) -> dict:
        """Serialize entire blackboard to dict."""
        return {
            "project_name": self.project_name,
            "created_at": self.created_at,
            "current_phase": self.current_phase.value,
            "iteration": self.iteration,
            "sections": {
                sid.value: {
                    "versions": [
                        {
                            "version": v.version,
                            "content": v.content,
                            "author": v.author,
                            "timestamp": v.timestamp,
                            "score": v.score,
                            "locked": v.locked,
                            "hash": v.hash
                        }
                        for v in section.versions
                    ],
                    "locked": section.locked,
                    "lock_reason": section.lock_reason
                }
                for sid, section in self.sections.items()
            },
            "blocking_issues": [
                {
                    "id": i.id,
                    "section": i.section.value,
                    "severity": i.severity,
                    "classification": i.classification,
                    "description": i.description,
                    "created_at": i.created_at,
                    "resolved": i.resolved,
                    "resolution": i.resolution,
                    "resolved_at": i.resolved_at
                }
                for i in self.blocking_issues
            ],
            "events": self.events
        }

    def _log_event(self, event_type: str, **kwargs):
        """Log an event to the audit trail."""
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **kwargs
        }
        self.events.append(event)

    def _save(self):
        """Save blackboard to disk."""
        if not self.persist_path:
            return

        self.persist_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.persist_path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)

    def _load(self):
        """Load blackboard from disk."""
        if not self.persist_path or not self.persist_path.exists():
            return

        with open(self.persist_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.project_name = data.get("project_name", self.project_name)
        self.created_at = data.get("created_at", self.created_at)
        self.current_phase = Phase(data.get("current_phase", "init"))
        self.iteration = data.get("iteration", 0)

        # Restore sections
        for sid_str, section_data in data.get("sections", {}).items():
            sid = SectionID(sid_str)
            section = self.sections[sid]
            section.locked = section_data.get("locked", False)
            section.lock_reason = section_data.get("lock_reason")

            for v_data in section_data.get("versions", []):
                version = SectionVersion(
                    version=v_data["version"],
                    content=v_data["content"],
                    author=v_data["author"],
                    timestamp=v_data["timestamp"],
                    score=v_data.get("score"),
                    locked=v_data.get("locked", False),
                    hash=v_data.get("hash", "")
                )
                section.versions.append(version)

        # Restore blocking issues
        for i_data in data.get("blocking_issues", []):
            issue = BlockingIssue(
                id=i_data["id"],
                section=SectionID(i_data["section"]),
                severity=i_data["severity"],
                classification=i_data["classification"],
                description=i_data["description"],
                created_at=i_data["created_at"],
                resolved=i_data.get("resolved", False),
                resolution=i_data.get("resolution"),
                resolved_at=i_data.get("resolved_at")
            )
            self.blocking_issues.append(issue)

        # Restore events
        self.events = data.get("events", [])

    def __repr__(self) -> str:
        sections_summary = ", ".join(
            f"{s.id.value}:v{s.version_count}"
            for s in self.sections.values()
            if s.versions
        )
        return (
            f"Blackboard(project={self.project_name}, "
            f"phase={self.current_phase.value}, "
            f"iter={self.iteration}, "
            f"sections=[{sections_summary}])"
        )
