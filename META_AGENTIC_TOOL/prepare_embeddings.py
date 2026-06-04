#!/usr/bin/env python3
"""
Prepare TouchDesigner knowledge base for vector embeddings.
Transforms all YAML/JSON sources into embedding-ready documents.
"""

import json
import yaml
from pathlib import Path
from typing import List, Dict, Any

HAIKU_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_output")
FACTS_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")
OUTPUT_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\embedding_docs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_yaml(path: Path) -> dict:
    """Load YAML file safely."""
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> dict:
    """Load JSON file safely."""
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# =============================================================================
# DOCUMENT GENERATORS
# =============================================================================

def generate_operator_docs() -> List[Dict[str, Any]]:
    """Generate documents for all operators."""
    docs = []
    data = load_yaml(HAIKU_DIR / "all_operator_wiki_semantics.yaml")

    for family, operators in data.items():
        if not isinstance(operators, dict):
            continue

        for op_name, op_data in operators.items():
            if not isinstance(op_data, dict):
                continue

            summary = op_data.get('summary', '')
            python_class = op_data.get('python_class', '')

            # Operator document
            text = f"{op_name}: {summary}"
            if python_class:
                text += f" Python class: {python_class}"

            docs.append({
                "id": f"op_{op_name}",
                "type": "operator",
                "family": family,
                "text": text,
                "metadata": {
                    "family": family,
                    "python_class": python_class,
                    "name": op_name
                }
            })

            # Parameter documents
            params = op_data.get('parameters', {})
            for param_code, param_data in params.items():
                if isinstance(param_data, dict):
                    desc = param_data.get('description', '')
                    section = param_data.get('section', '')
                else:
                    desc = str(param_data)
                    section = ''

                if not desc:
                    continue

                param_text = f"{op_name} {param_code} parameter: {desc}"

                docs.append({
                    "id": f"param_{op_name}_{param_code}",
                    "type": "parameter",
                    "family": family,
                    "text": param_text,
                    "metadata": {
                        "operator": op_name,
                        "parameter": param_code,
                        "section": section,
                        "family": family
                    }
                })

    return docs


def generate_concept_docs() -> List[Dict[str, Any]]:
    """Generate documents for concepts."""
    docs = []
    data = load_yaml(HAIKU_DIR / "concept_semantic_descriptions.yaml")

    for concept, description in data.items():
        if not description:
            continue

        docs.append({
            "id": f"concept_{concept.replace(' ', '_')}",
            "type": "concept",
            "family": "concept",
            "text": f"{concept}: {description}",
            "metadata": {
                "name": concept
            }
        })

    return docs


def generate_steering_docs() -> List[Dict[str, Any]]:
    """Generate steering/decision documents."""
    docs = []
    data = load_yaml(HAIKU_DIR / "steering_semantic_descriptions.yaml")

    for key, description in data.items():
        if not description or key.startswith('#'):
            continue

        # Determine approach type
        if key.startswith('glsl_'):
            approach = 'glsl'
        elif key.startswith('python_'):
            approach = 'python'
        elif key.startswith('native_'):
            approach = 'native'
        else:
            approach = 'guidance'

        docs.append({
            "id": f"steering_{key}",
            "type": "steering",
            "family": "steering",
            "text": description,
            "metadata": {
                "approach": approach,
                "key": key
            }
        })

    return docs


def generate_pattern_docs() -> List[Dict[str, Any]]:
    """Generate Python pattern documents."""
    docs = []
    data = load_yaml(HAIKU_DIR / "python_patterns_semantics.yaml")

    for pattern_name, pattern_data in data.items():
        if not isinstance(pattern_data, dict):
            continue

        desc = pattern_data.get('description', '')
        code = pattern_data.get('code', '')

        text = f"{pattern_name}: {desc}"
        if code:
            text += f" Example: {code}"

        docs.append({
            "id": f"pattern_{pattern_name}",
            "type": "python_pattern",
            "family": "python",
            "text": text,
            "metadata": {
                "name": pattern_name,
                "code": code
            }
        })

    return docs


def generate_callback_docs() -> List[Dict[str, Any]]:
    """Generate callback documentation."""
    docs = []
    data = load_yaml(HAIKU_DIR / "python_callbacks_semantics.yaml")

    for callback_name, callback_data in data.items():
        if not isinstance(callback_data, dict):
            continue

        desc = callback_data.get('description', '')
        sig = callback_data.get('signature', '')

        text = f"{callback_name}: {desc}"
        if sig:
            text += f" Signature: {sig}"

        docs.append({
            "id": f"callback_{callback_name}",
            "type": "callback",
            "family": "python",
            "text": text,
            "metadata": {
                "name": callback_name,
                "signature": sig
            }
        })

    return docs


def generate_class_docs() -> List[Dict[str, Any]]:
    """Generate class/method documentation."""
    docs = []
    data = load_yaml(HAIKU_DIR / "class_semantic_descriptions.yaml")

    for class_name, methods in data.items():
        if not isinstance(methods, dict):
            continue

        for method_name, description in methods.items():
            if not description:
                continue

            text = f"{class_name}.{method_name}: {description}"

            docs.append({
                "id": f"class_{class_name}_{method_name}",
                "type": "class_method",
                "family": "python",
                "text": text,
                "metadata": {
                    "class": class_name,
                    "method": method_name
                }
            })

    return docs


def generate_snippet_docs() -> List[Dict[str, Any]]:
    """Generate snippet example documents."""
    docs = []

    families = ['CHOP', 'TOP', 'SOP', 'DAT', 'COMP', 'MAT', 'POP']

    for family in families:
        data = load_yaml(HAIKU_DIR / f"{family}_descriptions.yaml")

        for op_name, examples in data.items():
            if not isinstance(examples, dict):
                continue

            for ex_key, ex_desc in examples.items():
                if not ex_desc:
                    continue

                # Clean up description
                if len(ex_desc) > 500:
                    ex_desc = ex_desc[:497] + "..."

                text = f"{op_name} example: {ex_desc}"

                docs.append({
                    "id": f"snippet_{op_name}_{ex_key}",
                    "type": "snippet",
                    "family": family,
                    "text": text,
                    "metadata": {
                        "operator": op_name,
                        "example": ex_key,
                        "family": family
                    }
                })

    return docs


def generate_python_example_docs() -> List[Dict[str, Any]]:
    """Generate Python code example documents."""
    docs = []
    data = load_json(FACTS_DIR / "python_examples.json")

    examples = data.get('examples', [])

    for i, example in enumerate(examples):
        if isinstance(example, dict):
            code = example.get('code', '')
            context = example.get('context', '')
            source = example.get('source', '')
        else:
            code = str(example)
            context = ''
            source = ''

        if not code or len(code) < 10:
            continue

        # Truncate very long code
        if len(code) > 300:
            code = code[:297] + "..."

        text = f"Python code: {code}"
        if context:
            text = f"{context} - {text}"

        docs.append({
            "id": f"pyex_{i}",
            "type": "python_example",
            "family": "python",
            "text": text,
            "metadata": {
                "source": source,
                "index": i
            }
        })

    return docs


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("Preparing embedding documents...")

    all_docs = []

    # Generate all document types
    generators = [
        ("Operators & Parameters", generate_operator_docs),
        ("Concepts", generate_concept_docs),
        ("Steering", generate_steering_docs),
        ("Python Patterns", generate_pattern_docs),
        ("Callbacks", generate_callback_docs),
        ("Class Methods", generate_class_docs),
        ("Snippets", generate_snippet_docs),
        ("Python Examples", generate_python_example_docs),
    ]

    for name, generator in generators:
        docs = generator()
        print(f"  {name}: {len(docs)} documents")
        all_docs.extend(docs)

    # Save all documents
    output_path = OUTPUT_DIR / "all_embedding_docs.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "total": len(all_docs),
            "documents": all_docs
        }, f, indent=2, ensure_ascii=False)

    print(f"\n=== Complete ===")
    print(f"Total documents: {len(all_docs)}")
    print(f"Output: {output_path}")

    # Stats by type
    by_type = {}
    for doc in all_docs:
        t = doc.get('type', 'unknown')
        by_type[t] = by_type.get(t, 0) + 1

    print("\nBy type:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")


if __name__ == '__main__':
    main()
