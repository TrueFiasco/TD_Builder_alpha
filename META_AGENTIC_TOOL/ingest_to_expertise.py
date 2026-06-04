#!/usr/bin/env python3
"""
Ingest extracted_facts/ and haiku_output/ into expertise JSONL events.
Follows INTEROP_AND_POLICY.md schema requirements.
"""

import json
import yaml
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

HAIKU_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_output")
FACTS_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")
META_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\meta_agentic")
EVENTS_FILE = META_DIR / "history" / "expertise_events.jsonl"

TD_VERSION = "2023.11000"  # Default TD version
SCHEMA_VERSION = "1.0"


def generate_event_id() -> str:
    """Generate unique event ID."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    uid = uuid.uuid4().hex[:8]
    return f"EVT-{ts}-{uid}"


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def load_yaml(path: Path) -> dict:
    """Load YAML file."""
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> dict:
    """Load JSON file."""
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def append_event(event: dict):
    """Append event to JSONL file."""
    with open(EVENTS_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')


def create_event(
    agent_id: str,
    domain: str,
    task: str,
    outputs: dict,
    evidence: List[dict],
    confidence: float = 0.8,
    notes: str = ""
) -> dict:
    """Create a properly formatted event."""
    return {
        "id": generate_event_id(),
        "ts": datetime.now().isoformat(),
        "agent_id": agent_id,
        "domain": domain,
        "inputs": {"task": task},
        "outputs": outputs,
        "evidence": evidence,
        "metrics": {
            "validation_passed": len(evidence) >= 3,
            "evidence_count": len(evidence)
        },
        "status": "success",
        "notes": notes,
        "schema_version": SCHEMA_VERSION,
        "td_version": TD_VERSION,
        "confidence": confidence,
        "problem_ids": []
    }


# =============================================================================
# INGESTORS
# =============================================================================

def ingest_operator_semantics() -> int:
    """Ingest operator wiki semantics."""
    count = 0
    data = load_yaml(HAIKU_DIR / "all_operator_wiki_semantics.yaml")

    for family, operators in data.items():
        if not isinstance(operators, dict):
            continue

        for op_name, op_data in operators.items():
            if not isinstance(op_data, dict):
                continue

            summary = op_data.get('summary', '')
            python_class = op_data.get('python_class', '')
            params = op_data.get('parameters', {})

            if not summary:
                continue

            # Create evidence from parameters (each param is evidence)
            evidence = []
            for param_code, param_data in list(params.items())[:5]:
                desc = param_data.get('description', '') if isinstance(param_data, dict) else str(param_data)
                evidence.append({
                    "source_path": f"haiku_output/all_operator_wiki_semantics.yaml",
                    "chunk_id": f"{op_name}.{param_code}",
                    "excerpt_hash": compute_hash(desc),
                    "td_version": TD_VERSION
                })

            # Add operator itself as evidence
            evidence.append({
                "source_path": "extracted_facts/TOP_operators_wiki.json" if family == "TOP" else f"extracted_facts/{family}_operators_wiki.json",
                "chunk_id": op_name,
                "excerpt_hash": compute_hash(summary),
                "td_version": TD_VERSION
            })

            outputs = {
                "operators": {
                    family: {
                        op_name: {
                            "summary": summary,
                            "python_class": python_class,
                            "parameter_count": len(params)
                        }
                    }
                }
            }

            event = create_event(
                agent_id="wiki_ingestor",
                domain="operators",
                task=f"Ingest {op_name} from wiki",
                outputs=outputs,
                evidence=evidence,
                confidence=0.95,
                notes=f"Ingested {op_name} with {len(params)} parameters"
            )
            append_event(event)
            count += 1

    return count


def ingest_concepts() -> int:
    """Ingest concept descriptions."""
    count = 0
    data = load_yaml(HAIKU_DIR / "concept_semantic_descriptions.yaml")

    # Batch concepts by first letter for efficient events
    batches = {}
    for concept, description in data.items():
        if not description:
            continue
        first = concept[0].upper() if concept else 'X'
        if first not in batches:
            batches[first] = {}
        batches[first][concept] = description

    for letter, concepts in batches.items():
        evidence = []
        for concept, desc in list(concepts.items())[:5]:
            evidence.append({
                "source_path": "haiku_output/concept_semantic_descriptions.yaml",
                "chunk_id": concept,
                "excerpt_hash": compute_hash(desc),
                "td_version": TD_VERSION
            })

        outputs = {
            "concepts": {
                f"batch_{letter}": {
                    "count": len(concepts),
                    "items": list(concepts.keys())
                }
            }
        }

        event = create_event(
            agent_id="concept_ingestor",
            domain="concepts",
            task=f"Ingest concepts starting with {letter}",
            outputs=outputs,
            evidence=evidence,
            confidence=0.9,
            notes=f"Ingested {len(concepts)} concepts"
        )
        append_event(event)
        count += 1

    return count


def ingest_steering() -> int:
    """Ingest steering descriptions."""
    count = 0
    data = load_yaml(HAIKU_DIR / "steering_semantic_descriptions.yaml")

    glsl_items = {}
    python_items = {}
    native_items = {}

    for key, description in data.items():
        if not description or key.startswith('#'):
            continue
        if key.startswith('glsl_'):
            glsl_items[key] = description
        elif key.startswith('python_'):
            python_items[key] = description
        elif key.startswith('native_'):
            native_items[key] = description

    # GLSL steering
    if glsl_items:
        evidence = [
            {"source_path": "haiku_output/steering_semantic_descriptions.yaml",
             "chunk_id": k, "excerpt_hash": compute_hash(v), "td_version": TD_VERSION}
            for k, v in list(glsl_items.items())[:4]
        ]
        event = create_event(
            agent_id="steering_ingestor",
            domain="steering",
            task="Ingest GLSL steering guidance",
            outputs={"steering": {"glsl": {"patterns": list(glsl_items.keys())}}},
            evidence=evidence,
            confidence=0.85,
            notes=f"Ingested {len(glsl_items)} GLSL steering patterns"
        )
        append_event(event)
        count += 1

    # Python steering
    if python_items:
        evidence = [
            {"source_path": "haiku_output/steering_semantic_descriptions.yaml",
             "chunk_id": k, "excerpt_hash": compute_hash(v), "td_version": TD_VERSION}
            for k, v in list(python_items.items())[:4]
        ]
        event = create_event(
            agent_id="steering_ingestor",
            domain="steering",
            task="Ingest Python steering guidance",
            outputs={"steering": {"python": {"patterns": list(python_items.keys())}}},
            evidence=evidence,
            confidence=0.85,
            notes=f"Ingested {len(python_items)} Python steering patterns"
        )
        append_event(event)
        count += 1

    # Native steering
    if native_items:
        evidence = [
            {"source_path": "haiku_output/steering_semantic_descriptions.yaml",
             "chunk_id": k, "excerpt_hash": compute_hash(v), "td_version": TD_VERSION}
            for k, v in list(native_items.items())[:4]
        ]
        event = create_event(
            agent_id="steering_ingestor",
            domain="steering",
            task="Ingest Native operator steering guidance",
            outputs={"steering": {"native": {"patterns": list(native_items.keys())}}},
            evidence=evidence,
            confidence=0.85,
            notes=f"Ingested {len(native_items)} Native steering patterns"
        )
        append_event(event)
        count += 1

    return count


def ingest_python_patterns() -> int:
    """Ingest Python patterns and callbacks."""
    count = 0

    # Patterns
    patterns = load_yaml(HAIKU_DIR / "python_patterns_semantics.yaml")
    if patterns:
        evidence = []
        for name, data in list(patterns.items())[:4]:
            if isinstance(data, dict):
                desc = data.get('description', '')
                evidence.append({
                    "source_path": "haiku_output/python_patterns_semantics.yaml",
                    "chunk_id": name,
                    "excerpt_hash": compute_hash(desc),
                    "td_version": TD_VERSION
                })

        event = create_event(
            agent_id="pattern_ingestor",
            domain="patterns",
            task="Ingest Python code patterns",
            outputs={"patterns": {"python": {"count": len(patterns), "names": list(patterns.keys())}}},
            evidence=evidence,
            confidence=0.9,
            notes=f"Ingested {len(patterns)} Python patterns"
        )
        append_event(event)
        count += 1

    # Callbacks
    callbacks = load_yaml(HAIKU_DIR / "python_callbacks_semantics.yaml")
    if callbacks:
        evidence = []
        for name, data in list(callbacks.items())[:4]:
            if isinstance(data, dict):
                desc = data.get('description', '')
                evidence.append({
                    "source_path": "haiku_output/python_callbacks_semantics.yaml",
                    "chunk_id": name,
                    "excerpt_hash": compute_hash(desc),
                    "td_version": TD_VERSION
                })

        event = create_event(
            agent_id="pattern_ingestor",
            domain="patterns",
            task="Ingest Python callback signatures",
            outputs={"patterns": {"callbacks": {"count": len(callbacks), "names": list(callbacks.keys())}}},
            evidence=evidence,
            confidence=0.9,
            notes=f"Ingested {len(callbacks)} callback signatures"
        )
        append_event(event)
        count += 1

    return count


def ingest_class_methods() -> int:
    """Ingest class method documentation."""
    count = 0
    data = load_yaml(HAIKU_DIR / "class_semantic_descriptions.yaml")

    # Batch by class prefix
    for class_name, methods in data.items():
        if not isinstance(methods, dict) or not methods:
            continue

        evidence = []
        for method_name, desc in list(methods.items())[:4]:
            if desc and isinstance(desc, str):
                evidence.append({
                    "source_path": "haiku_output/class_semantic_descriptions.yaml",
                    "chunk_id": f"{class_name}.{method_name}",
                    "excerpt_hash": compute_hash(desc),
                    "td_version": TD_VERSION
                })

        if len(evidence) >= 3:
            event = create_event(
                agent_id="class_ingestor",
                domain="api",
                task=f"Ingest {class_name} methods",
                outputs={"api": {"classes": {class_name: {"method_count": len(methods)}}}},
                evidence=evidence,
                confidence=0.85,
                notes=f"Ingested {len(methods)} methods for {class_name}"
            )
            append_event(event)
            count += 1

    return count


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("Ingesting knowledge base into expertise events...")
    print(f"Output: {EVENTS_FILE}\n")

    total = 0

    # Run ingestors
    ingestors = [
        ("Operator Semantics", ingest_operator_semantics),
        ("Concepts", ingest_concepts),
        ("Steering", ingest_steering),
        ("Python Patterns", ingest_python_patterns),
        ("Class Methods", ingest_class_methods),
    ]

    for name, func in ingestors:
        count = func()
        print(f"  {name}: {count} events")
        total += count

    print(f"\n=== Complete ===")
    print(f"Total events appended: {total}")
    print(f"Run compaction to refresh expertise_state.yaml")


if __name__ == '__main__':
    main()
