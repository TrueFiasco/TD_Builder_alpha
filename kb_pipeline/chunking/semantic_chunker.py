"""
Semantic Chunking for TouchDesigner Knowledge Base

Implements hierarchical chunking strategy:
- Tier 1: Operator Overview (high-level semantic unit)
- Tier 2: Parameter Groups (medium granularity)
- Tier 3: Individual Parameters (fine detail)
- Tier 4: Real Example Networks (contextual)

This improves search quality by:
- Preserving context through parent-child relationships
- Reducing false positives by separating concerns
- Enabling hierarchical retrieval (overview first, drill down if needed)
"""

from typing import List, Dict, Any, Optional
import hashlib
import json


class SemanticChunker:
    """Creates hierarchical chunks from TouchDesigner operator data."""

    def __init__(self):
        self.chunk_types = {
            'operator_overview': 1,
            'parameter_group': 2,
            'parameter_detail': 3,
            'real_example': 4
        }

    def create_hierarchical_chunks(self, operator_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create hierarchical chunks for an operator.

        Args:
            operator_data: Operator info from td_universal_parsed.json or similar
                Expected keys: name, family, summary, parameters, etc.

        Returns:
            List of chunk dicts with id, text, meta, chunk_type, parent_chunk
        """
        chunks = []
        operator_name = operator_data.get('name', 'Unknown')

        # Tier 1: Operator Overview
        overview_chunk = self._create_overview_chunk(operator_data)
        chunks.append(overview_chunk)

        # Tier 2: Parameter Groups (if parameters exist)
        parameters = operator_data.get('parameters', [])
        if parameters:
            # Handle both list and dict formats
            if isinstance(parameters, list):
                param_groups = self._group_parameters_list(parameters, operator_data.get('family', 'UNKNOWN'))
            else:
                param_groups = self._group_parameters(parameters, operator_data.get('family', 'UNKNOWN'))

            for group_name, group_params in param_groups.items():
                group_chunk = self._create_param_group_chunk(
                    operator_name,
                    group_name,
                    group_params,
                    parent_id=overview_chunk['id']
                )
                chunks.append(group_chunk)

                # Tier 3: Individual Parameters
                for param in group_params:
                    param_chunk = self._create_param_detail_chunk(
                        operator_name,
                        param,
                        parent_id=group_chunk['id']
                    )
                    chunks.append(param_chunk)

        # Tier 4: Real Examples (if available)
        examples = operator_data.get('examples', [])
        for idx, example in enumerate(examples):
            example_chunk = self._create_example_chunk(
                operator_name,
                example,
                idx,
                parent_id=overview_chunk['id']
            )
            chunks.append(example_chunk)

        return chunks

    def _create_overview_chunk(self, operator_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Tier 1: Operator Overview chunk."""
        operator_name = operator_data.get('name', 'Unknown')
        family = operator_data.get('family', 'UNKNOWN')
        summary = operator_data.get('summary', '')

        # Build comprehensive overview text
        text_parts = [
            f"{operator_name} ({family})",
            f"Summary: {summary}"
        ]

        # Add parameter count if available
        params = operator_data.get('parameters', {})
        if params:
            text_parts.append(f"Parameters: {len(params)}")

        # Add examples count if available
        examples = operator_data.get('examples', [])
        if examples:
            text_parts.append(f"Examples available: {len(examples)}")

        text = "\n".join(text_parts)
        chunk_id = self._generate_chunk_id(f"overview::{operator_name}")

        return {
            'id': chunk_id,
            'text': text,
            'chunk_type': 'operator_overview',
            'parent_chunk': None,
            'meta': {
                'operator_name': operator_name,
                'family': family,
                'source': 'docs',
                'tier': 1,
                'chunk_type': 'operator_overview'
            }
        }

    def _group_parameters_list(self, parameters: List[Dict], family: str) -> Dict[str, List[Dict]]:
        """
        Group parameters from list format based on section.

        Returns dict of {group_name: [param_dicts]}
        """
        groups = {}

        for param in parameters:
            # Use section from parameter
            section = param.get('section', 'General')

            # Simplify section names (remove "Parameters - " prefix if present)
            section = section.replace('Parameters - ', '').replace(' Page', '')

            if not section or section.strip() == '':
                # Fallback grouping based on parameter code
                param_code = param.get('code', '')
                section = self._infer_param_group(param_code, family)

            if section not in groups:
                groups[section] = []

            groups[section].append(param)

        return groups

    def _group_parameters(self, parameters: Dict[str, Any], family: str) -> Dict[str, List[Dict]]:
        """
        Group parameters from dict format based on section or common patterns.

        Returns dict of {group_name: [param_dicts]}
        """
        groups = {}

        for param_name, param_info in parameters.items():
            # Try to use 'section' from parameter if available
            section = None
            if isinstance(param_info, dict):
                section = param_info.get('section') or param_info.get('display_section')

            # Fallback grouping based on common patterns
            if not section:
                section = self._infer_param_group(param_name, family)

            if section not in groups:
                groups[section] = []

            # Convert to list format
            param_dict = param_info if isinstance(param_info, dict) else {'value': param_info}
            param_dict['code'] = param_name
            groups[section].append(param_dict)

        return groups

    def _infer_param_group(self, param_name: str, family: str) -> str:
        """Infer parameter group from name and operator family."""
        param_lower = param_name.lower()

        # Common parameter groups
        if any(x in param_lower for x in ['speed', 'play', 'cue', 'time']):
            return 'Timing & Playback'
        elif any(x in param_lower for x in ['size', 'scale', 'translate', 'rotate', 'transform']):
            return 'Transform'
        elif any(x in param_lower for x in ['color', 'alpha', 'opacity', 'blend']):
            return 'Appearance'
        elif any(x in param_lower for x in ['input', 'output', 'source', 'target']):
            return 'Input/Output'
        elif any(x in param_lower for x in ['filter', 'smooth', 'interpolate']):
            return 'Filtering'
        else:
            return 'General'

    def _create_param_group_chunk(self, operator_name: str, group_name: str,
                                   group_params: List[Dict], parent_id: str) -> Dict[str, Any]:
        """Create Tier 2: Parameter Group chunk."""
        param_names = [p.get('code', p.get('display_name', 'unknown')) for p in group_params]

        text = f"{operator_name} - {group_name}\n"
        text += f"Parameters: {', '.join(param_names[:10])}"  # Limit to 10 for brevity
        if len(param_names) > 10:
            text += f" (and {len(param_names) - 10} more)"

        chunk_id = self._generate_chunk_id(f"paramgroup::{operator_name}::{group_name}")

        return {
            'id': chunk_id,
            'text': text,
            'chunk_type': 'parameter_group',
            'parent_chunk': parent_id,
            'meta': {
                'operator_name': operator_name,
                'parameter_group': group_name,
                'parameter_count': len(param_names),
                'parameters': param_names,
                'tier': 2,
                'chunk_type': 'parameter_group'
            }
        }

    def _create_param_detail_chunk(self, operator_name: str, param: Dict[str, Any],
                                   parent_id: str) -> Dict[str, Any]:
        """Create Tier 3: Individual Parameter chunk."""
        param_code = param.get('code', 'unknown')
        display_name = param.get('display_name', param_code)
        description = param.get('description', '')
        default = param.get('default', '')

        text_parts = [
            f"{operator_name} - Parameter: {display_name}",
            f"Code: {param_code}"
        ]

        if description:
            # Truncate long descriptions
            desc = description[:200] + '...' if len(description) > 200 else description
            text_parts.append(f"Description: {desc}")

        if default:
            text_parts.append(f"Default: {default}")

        text = "\n".join(text_parts)
        chunk_id = self._generate_chunk_id(f"param::{operator_name}::{param_code}")

        return {
            'id': chunk_id,
            'text': text,
            'chunk_type': 'parameter_detail',
            'parent_chunk': parent_id,
            'meta': {
                'operator_name': operator_name,
                'parameter': param_code,
                'display_name': display_name,
                'tier': 3,
                'chunk_type': 'parameter_detail'
            }
        }

    def _create_example_chunk(self, operator_name: str, example: Dict[str, Any],
                              idx: int, parent_id: str) -> Dict[str, Any]:
        """Create Tier 4: Real Example chunk."""
        example_name = example.get('example_name', f'example_{idx}')
        topic = example.get('topic', '')
        operators = example.get('operators', [])

        text_parts = [
            f"{operator_name} - Example: {example_name}",
        ]

        if topic:
            text_parts.append(f"Topic: {topic}")

        # Include info about operators used
        if operators:
            op_list = []
            for op in operators[:5]:  # Limit to 5
                if isinstance(op, dict):
                    op_name = op.get('name', op.get('type', 'unknown'))
                    op_type = op.get('type', '')
                    op_list.append(f"{op_name} ({op_type})")
                else:
                    op_list.append(str(op))

            text_parts.append(f"Operators: {', '.join(op_list)}")

        text = "\n".join(text_parts)
        chunk_id = self._generate_chunk_id(f"example::{operator_name}::{example_name}::{idx}")

        return {
            'id': chunk_id,
            'text': text,
            'chunk_type': 'real_example',
            'parent_chunk': parent_id,
            'meta': {
                'operator_name': operator_name,
                'example_name': example_name,
                'example_id': idx,
                'tier': 4,
                'chunk_type': 'real_example'
            }
        }

    def _generate_chunk_id(self, content: str) -> str:
        """Generate stable chunk ID from content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# Convenience function
def create_hierarchical_chunks(operator_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create hierarchical chunks for an operator.

    Args:
        operator_data: Operator info dict

    Returns:
        List of chunk dicts
    """
    chunker = SemanticChunker()
    return chunker.create_hierarchical_chunks(operator_data)


# Example usage
if __name__ == '__main__':
    # Test with sample operator data
    sample_operator = {
        'name': 'Speed CHOP',
        'family': 'CHOP',
        'summary': 'Controls the playback speed of channels over time',
        'parameters': {
            'speed': {
                'display_name': 'Speed',
                'description': 'Playback speed multiplier',
                'default': 1.0,
                'section': 'Speed Control'
            },
            'play': {
                'display_name': 'Play',
                'description': 'Start/stop playback',
                'default': 1,
                'section': 'Speed Control'
            },
            'independent': {
                'display_name': 'Independent',
                'description': 'Use independent timeline',
                'default': 0,
                'section': 'Settings'
            }
        },
        'examples': [
            {
                'example_name': 'speedCHOP/example1',
                'topic': 'Basic speed control',
                'operators': [
                    {'name': 'speed1', 'type': 'speedCHOP'},
                    {'name': 'noise1', 'type': 'noiseCHOP'}
                ]
            }
        ]
    }

    chunks = create_hierarchical_chunks(sample_operator)

    print(f"Created {len(chunks)} chunks for {sample_operator['name']}:\n")
    for chunk in chunks:
        print(f"Tier {chunk['meta']['tier']}: {chunk['chunk_type']}")
        print(f"  ID: {chunk['id']}")
        print(f"  Text: {chunk['text'][:100]}...")
        print(f"  Parent: {chunk['parent_chunk']}")
        print()
