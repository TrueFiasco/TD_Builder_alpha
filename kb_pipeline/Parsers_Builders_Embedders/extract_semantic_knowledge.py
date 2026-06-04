#!/usr/bin/env python3
"""
Semantic Knowledge Extractor
Extracts learning-relevant knowledge from lossless TouchDesigner JSON

Input: Lossless JSON from toe_to_json_LOSSLESS.py
Output: Semantic knowledge for GraphRAG (operators, parameters, connections)

Focus: Extract REAL parameter values, prevent hallucinations
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Set


class SemanticExtractor:
    """Extract semantic knowledge from lossless TD JSON"""

    # Parameters that affect operator behavior (not UI/metadata)
    FUNCTIONAL_PARAM_PATTERNS = {
        'function', 'method', 'type', 'mode', 'operation',
        'timeslice', 'cook', 'align', 'stretch', 'extend',
        'rate', 'speed', 'freq', 'amplitude', 'phase',
        'width', 'height', 'resolution', 'format',
        'file', 'path', 'name', 'chop', 'dat', 'top', 'sop'
    }

    # Skip pure UI parameters
    UI_PARAMS_TO_SKIP = {
        'nodeX', 'nodeY', 'display', 'comment', 'color',
        'dock', 'viewer', 'current', 'panel'
    }

    def __init__(self):
        self.stats = {
            'operators_found': 0,
            'parameters_extracted': 0,
            'connections_found': 0,
            'examples_processed': 0
        }

    def extract_from_file(self, lossless_json_path: Path) -> Dict[str, Any]:
        """Extract semantic knowledge from a lossless JSON file"""

        print(f"Processing: {lossless_json_path.name}")

        with open(lossless_json_path, 'r', encoding='utf-8') as f:
            lossless_data = json.load(f)

        # Extract semantic knowledge
        semantic = {
            'source_file': str(lossless_json_path),
            'operator_type': self._extract_operator_type(lossless_json_path),
            'examples': []
        }

        # Process each example in the .tox
        examples = self._find_examples(lossless_data)

        for example_name, example_data in examples.items():
            example_semantic = self._extract_example_knowledge(
                example_name,
                example_data
            )
            if example_semantic:
                semantic['examples'].append(example_semantic)
                self.stats['examples_processed'] += 1

        return semantic

    def _extract_operator_type(self, file_path: Path) -> str:
        """Extract operator type from filename (e.g., 'analyzeCHOP')"""
        return file_path.stem.replace('_lossless', '')

    def _find_examples(self, lossless_data: Dict) -> Dict[str, Any]:
        """Find all example networks in the lossless data"""

        examples = {}

        # Lossless JSON has flat structure with 'operators' dict
        if 'operators' not in lossless_data:
            return examples

        operators = lossless_data['operators']

        # Find all operators with 'example' in their name
        for op_path, op_data in operators.items():
            op_name = op_data.get('name', '')

            # Examples typically named: example1, example2, etc.
            if 'example' in op_name.lower():
                examples[op_name] = {
                    'path': op_path,
                    'data': op_data,
                    'all_operators': operators  # Need access to all operators
                }

        return examples

    def _extract_example_knowledge(
        self,
        example_name: str,
        example_data: Dict
    ) -> Dict[str, Any]:
        """Extract knowledge from a single example network"""

        # example_data has: 'path', 'data', 'all_operators'
        example_op = example_data['data']
        all_operators = example_data['all_operators']
        example_path = example_data['path']

        operators = self._extract_operators(example_op, all_operators)
        connections = self._extract_connections(example_op, all_operators)

        if not operators:
            return None

        # Get example description from comment/annotation
        description = self._extract_description(example_op, all_operators)

        return {
            'name': example_name,
            'description': description,
            'operators': operators,
            'connections': connections,
            'network_pattern': self._analyze_network_pattern(operators, connections)
        }

    def _extract_operators(
        self,
        container_data: Dict,
        all_operators: Dict
    ) -> List[Dict[str, Any]]:
        """Extract all operators with their key parameters"""

        operators = []

        # Get children operator names from container
        children_names = container_data.get('children', [])
        container_path = container_data.get('path', '')

        for child_name in children_names:
            # Build child path
            child_path = f"{container_path}/{child_name}"

            # Get child operator from all_operators
            if child_path not in all_operators:
                continue

            child_op = all_operators[child_path]

            op_type = child_op.get('op_type', 'unknown')
            op_name = child_op.get('name', 'unnamed')

            # Skip UI elements (annotations, null ops)
            if 'annotation' in op_type.lower() or op_type == 'null':
                continue

            # Extract functional parameters
            params = self._extract_functional_parameters(child_op)

            operator_info = {
                'name': op_name,
                'type': op_type,
                'parameters': params
            }

            operators.append(operator_info)
            self.stats['operators_found'] += 1

        return operators

    def _extract_functional_parameters(self, operator_data: Dict) -> Dict[str, Any]:
        """Extract parameters that affect operator behavior"""

        functional_params = {}

        if 'parameters' not in operator_data:
            return functional_params

        for param_name, param_value in operator_data['parameters'].items():
            # Skip UI parameters
            if any(skip in param_name.lower() for skip in self.UI_PARAMS_TO_SKIP):
                continue

            # Handle different param value types
            # In lossless JSON, params can be: simple values OR dicts with special keys
            if isinstance(param_value, dict):
                # Skip dict parameters for now (they're complex nested structures)
                continue

            # Check if parameter is functional
            is_functional = any(
                pattern in param_name.lower()
                for pattern in self.FUNCTIONAL_PARAM_PATTERNS
            )

            # Also include parameters with non-default values
            if param_value is not None:
                # Convert to string for comparison
                param_str = str(param_value).lower()
                # Check if value looks non-default
                if param_str not in ['', '0', 'off', 'none', '0.0', 'false']:
                    is_functional = True

            if is_functional and param_value is not None:
                functional_params[param_name] = param_value
                self.stats['parameters_extracted'] += 1

        return functional_params

    def _extract_connections(
        self,
        container_data: Dict,
        all_operators: Dict
    ) -> List[Dict[str, str]]:
        """Extract operator connections (dataflow)"""

        connections = []

        # Get children operator names from container
        children_names = container_data.get('children', [])
        container_path = container_data.get('path', '')

        for child_name in children_names:
            # Build child path
            child_path = f"{container_path}/{child_name}"

            # Get child operator from all_operators
            if child_path not in all_operators:
                continue

            child_op = all_operators[child_path]
            op_name = child_op.get('name', '')

            # Check for input connections
            # In lossless JSON, inputs are: {'0': 'source_op_name', '1': 'another_op', ...}
            inputs = child_op.get('inputs', {})
            for input_idx, source_op_name in inputs.items():
                if source_op_name:  # Non-empty source
                    connections.append({
                        'from': source_op_name,
                        'to': op_name,
                        'to_input': input_idx
                    })
                    self.stats['connections_found'] += 1

        return connections

    def _extract_description(
        self,
        container_data: Dict,
        all_operators: Dict
    ) -> str:
        """Extract description from annotations or comments"""

        description = ""

        # Look for annotation nodes in children
        children_names = container_data.get('children', [])
        container_path = container_data.get('path', '')

        for child_name in children_names:
            child_path = f"{container_path}/{child_name}"

            if child_path not in all_operators:
                continue

            child_op = all_operators[child_path]

            if 'annotation' in child_op.get('op_type', '').lower():
                if 'parameters' in child_op:
                    text = child_op['parameters'].get('text', {}).get('value', '')
                    if text:
                        description = text
                        break

        return description

    def _analyze_network_pattern(
        self,
        operators: List[Dict],
        connections: List[Dict]
    ) -> Dict[str, Any]:
        """Analyze the network topology pattern"""

        # Count operator types
        operator_types = {}
        for op in operators:
            op_type = op['type']
            operator_types[op_type] = operator_types.get(op_type, 0) + 1

        # Analyze topology
        has_parallel = self._has_parallel_paths(connections)
        has_feedback = self._has_feedback_loops(connections)
        chain_length = self._max_chain_length(operators, connections)

        return {
            'operator_count': len(operators),
            'connection_count': len(connections),
            'operator_types': operator_types,
            'has_parallel_paths': has_parallel,
            'has_feedback_loops': has_feedback,
            'max_chain_length': chain_length
        }

    def _has_parallel_paths(self, connections: List[Dict]) -> bool:
        """Check if network has parallel processing paths"""

        # Count outputs per operator
        output_counts = {}
        for conn in connections:
            source = conn['from']
            output_counts[source] = output_counts.get(source, 0) + 1

        return any(count > 1 for count in output_counts.values())

    def _has_feedback_loops(self, connections: List[Dict]) -> bool:
        """Check for feedback loops (cycles in the graph)"""

        # Build adjacency list
        graph = {}
        for conn in connections:
            source = conn['from']
            target = conn['to']
            if source not in graph:
                graph[source] = []
            graph[source].append(target)

        # DFS to detect cycles
        visited = set()
        rec_stack = set()

        def has_cycle(node):
            visited.add(node)
            rec_stack.add(node)

            if node in graph:
                for neighbor in graph[node]:
                    if neighbor not in visited:
                        if has_cycle(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True

            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                if has_cycle(node):
                    return True

        return False

    def _max_chain_length(
        self,
        operators: List[Dict],
        connections: List[Dict]
    ) -> int:
        """Calculate maximum chain length in the network"""

        # Build adjacency list
        graph = {}
        for conn in connections:
            source = conn['from']
            target = conn['to']
            if source not in graph:
                graph[source] = []
            graph[source].append(target)

        # Find all nodes
        all_nodes = set(op['name'] for op in operators)

        # DFS to find longest path
        max_length = 0

        def dfs(node, length):
            nonlocal max_length
            max_length = max(max_length, length)

            if node in graph:
                for neighbor in graph[node]:
                    dfs(neighbor, length + 1)

        # Start from nodes with no inputs (source nodes)
        source_nodes = all_nodes - set(conn['to'] for conn in connections)

        for node in source_nodes:
            dfs(node, 1)

        return max_length if max_length > 0 else len(operators)

    def print_stats(self):
        """Print extraction statistics"""
        print("\n" + "="*70)
        print("SEMANTIC EXTRACTION STATISTICS")
        print("="*70)
        print(f"Examples processed: {self.stats['examples_processed']}")
        print(f"Operators found: {self.stats['operators_found']}")
        print(f"Parameters extracted: {self.stats['parameters_extracted']}")
        print(f"Connections found: {self.stats['connections_found']}")
        print("="*70 + "\n")


def main():
    """Test semantic extraction on a single file"""

    import sys

    if len(sys.argv) < 2:
        print("Usage: python extract_semantic_knowledge.py <lossless_json_file>")
        print("\nExample:")
        print("  python extract_semantic_knowledge.py analyzeCHOP_lossless.json")
        return 1

    input_file = Path(sys.argv[1])

    if not input_file.exists():
        print(f"Error: File not found: {input_file}")
        return 1

    # Extract semantic knowledge
    extractor = SemanticExtractor()
    semantic = extractor.extract_from_file(input_file)

    # Save output
    output_file = input_file.parent / f"{input_file.stem.replace('_lossless', '')}_semantic.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(semantic, f, indent=2)

    print(f"\nSaved semantic knowledge to: {output_file}")

    # Print stats
    extractor.print_stats()

    # Show sample
    print("SAMPLE EXTRACTION:")
    print("-" * 70)
    if semantic['examples']:
        example = semantic['examples'][0]
        print(f"\nExample: {example['name']}")
        if example['description']:
            print(f"Description: {example['description']}")
        print(f"\nOperators ({len(example['operators'])}):")
        for op in example['operators']:
            print(f"  - {op['name']} ({op['type']})")
            if op['parameters']:
                for param_name, param_value in op['parameters'].items():
                    print(f"      {param_name} = {param_value}")
        print(f"\nConnections ({len(example['connections'])}):")
        for conn in example['connections']:
            print(f"  {conn['from']} -> {conn['to']}")
    print("-" * 70)

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
