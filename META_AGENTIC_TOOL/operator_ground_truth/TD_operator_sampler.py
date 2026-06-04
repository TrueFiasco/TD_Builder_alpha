"""
TouchDesigner Operator Sampler - Text DAT Script
=================================================
Run this inside TouchDesigner to generate ground-truth .tox files
for every operator type with captured default and perturbed parameters.

SETUP:
1. Create a Text DAT in TouchDesigner
2. Paste this script
3. Add a "Run Script" button or run from textport: exec(op('text1').text)

OUTPUT:
- C:/TD_Projects/META_AGENTIC_TOOL/operator_ground_truth/tox/
  - {FAMILY}_{optype}.tox (one per operator)
- C:/TD_Projects/META_AGENTIC_TOOL/operator_ground_truth/params/
  - {FAMILY}_{optype}_defaults.json
  - {FAMILY}_{optype}_perturbed.json

Each .tox contains a COMP with:
- op_default: operator with default values (won't show in .parm)
- op_perturbed: operator with all params changed (WILL show in .parm)
"""

import json
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

OUTPUT_BASE = "C:/TD_Projects/META_AGENTIC_TOOL/operator_ground_truth"
TOX_DIR = f"{OUTPUT_BASE}/tox"
PARAMS_DIR = f"{OUTPUT_BASE}/params"

# Create output directories
os.makedirs(TOX_DIR, exist_ok=True)
os.makedirs(PARAMS_DIR, exist_ok=True)

# Load operator types from pre-generated list
OPERATOR_TYPES_PATH = f"{OUTPUT_BASE}/operator_types.json"

# ============================================================================
# OPERATOR TYPE MAPPINGS
# ============================================================================

# Some operators have non-standard create names
# Format: 'KB_name': 'td_create_name'
CREATE_NAME_OVERRIDES = {
    # CHOPs
    'Ableton_Link_CHOP': 'abletonlinkCHOP',
    'Audio_Band_EQ_CHOP': 'audiobandeqCHOP',
    'Audio_Binaural_CHOP': 'audiobinauralCHOP',
    'Audio_Device_In_CHOP': 'audiodeviceinCHOP',
    'Audio_Device_Out_CHOP': 'audiodeviceoutCHOP',
    'Audio_Dynamics_CHOP': 'audiodynamicsCHOP',
    'Audio_File_In_CHOP': 'audiofileinCHOP',
    'Audio_File_Out_CHOP': 'audiofileoutCHOP',
    'Audio_Filter_CHOP': 'audiofilterCHOP',
    'Audio_Movie_CHOP': 'audiomovieCHOP',
    'Audio_Oscillator_CHOP': 'audiooscillatorCHOP',
    'Audio_Para_EQ_CHOP': 'audioparaeqCHOP',
    'Audio_Play_CHOP': 'audioplayCHOP',
    'Audio_Render_CHOP': 'audiorenderCHOP',
    'Audio_Spectrum_CHOP': 'audiospectrumCHOP',
    'Audio_Stream_In_CHOP': 'audiostreaminCHOP',
    'Audio_Stream_Out_CHOP': 'audiostreamoutCHOP',
    'Audio_VST_CHOP': 'audiovstCHOP',
    'Mouse_In_CHOP': 'mouseinCHOP',
    'Keyboard_In_CHOP': 'keyboardinCHOP',
    'MIDI_In_CHOP': 'midiinCHOP',
    'MIDI_Out_CHOP': 'midioutCHOP',
    'OSC_In_CHOP': 'oscinCHOP',
    'OSC_Out_CHOP': 'oscoutCHOP',
    # TOPs
    'Movie_File_In_TOP': 'moviefileinTOP',
    'Movie_File_Out_TOP': 'moviefileoutTOP',
    'Video_Device_In_TOP': 'videodeviceinTOP',
    'Video_Device_Out_TOP': 'videodeviceoutTOP',
    'Video_Stream_In_TOP': 'videostreaminTOP',
    'Video_Stream_Out_TOP': 'videostreamoutTOP',
    'Render_Pick_TOP': 'renderpickTOP',
    'Render_Pass_TOP': 'renderpassTOP',
    # SOPs
    'Add_SOP': 'addSOP',
    'Copy_SOP': 'copySOP',
    # COMPs
    'Base_COMP': 'baseCOMP',
    'Geometry_COMP': 'geometryCOMP',
    'Camera_COMP': 'cameraCOMP',
    'Light_COMP': 'lightCOMP',
    # DATs
    'Text_DAT': 'textDAT',
    'Table_DAT': 'tableDAT',
    'Script_DAT': 'scriptDAT',
    'CHOP_Execute_DAT': 'chopexecuteDAT',
    'DAT_Execute_DAT': 'datexecuteDAT',
    'Panel_Execute_DAT': 'panelexecuteDAT',
    # MATs
    'Phong_MAT': 'phongMAT',
    'PBR_MAT': 'pbrMAT',
    'GLSL_MAT': 'glslMAT',
    'Constant_MAT': 'constantMAT',
}

# Operators to skip (abstract, deprecated, documentation, or problematic)
SKIP_OPERATORS = {
    # Documentation pages, not real operators
    'Anatomy_of_a_CHOP',
    'Anatomy_of_a_SOP',
    'Anatomy_of_a_TOP',
    'Anatomy_of_a_DAT',
    'Anatomy_of_a_COMP',
    'Anatomy_of_a_MAT',
    # "Write a" tutorial pages
    'Write_a_CPlusPlus_CHOP',
    'Write_a_Shared_Memory_CHOP',
    'Write_a_CPlusPlus_TOP',
    'Write_a_GLSL_TOP',
    'Write_a_Shared_Memory_TOP',
    'Write_a_CPlusPlus_POP',
    # Deprecated or version-specific
    'CUDA_TOP',
    'FreeD_CHOP',
    'Stype_CHOP',
    'wrnchAI_CHOP',
    'Gradient_TOP',  # Use Ramp TOP
    'Layer_TOP',
    'Simple_Render_TOP',  # Use Render TOP
    'Fuse_SOP',  # Deprecated
    'Mirror_SOP',  # Use Transform
    'Normals_SOP',  # Use Attribute Create
    'Scatter_SOP',  # Use Sprinkle
    'Analyze_DAT',
    'Build_a_List_COMP',
    'Geo_COMP',  # Use Geometry_COMP
    'Impulse_Force_COMP',
    # POP operators that don't exist
    'Add_POP',
    'Attractor_POP',
    'Collision_POP',
    'Drag_POP',
    'Force_POP',
    'GLSL_Create_POP',
    'Kill_POP',
    'Line_Thick_POP',
    'Source_POP',
    'Velocity_POP',
    # Problematic names
    'Art-Net_DAT',  # Hyphen in name causes issues
    # Operators with special create requirements
    'Band_EQ_CHOP',
    'EtherDream_CHOP',
    'Helios_DAC_CHOP',
    'Parametric_EQ_CHOP',
    'RealSense_CHOP',
    'Scan_CHOP',
    'SVG_TOP',
    'Font_SOP',
    'Indices_DAT',
    'UDT_In_DAT',
    'UDT_Out_DAT',
    'Web_DAT',
}

# ============================================================================
# PARAMETER CAPTURE FUNCTIONS
# ============================================================================

def capture_param_value(par):
    """Capture a parameter's current value in serializable form."""
    try:
        if par.isPulse:
            return {'type': 'pulse', 'value': None}
        elif par.isOP:
            return {'type': 'op', 'value': str(par.val) if par.val else ''}
        elif par.isFloat:
            return {'type': 'float', 'value': par.val}
        elif par.isInt:
            return {'type': 'int', 'value': par.val}
        elif par.isString:
            return {'type': 'string', 'value': par.val}
        elif par.isToggle:
            return {'type': 'toggle', 'value': par.val}
        elif par.isMenu:
            return {
                'type': 'menu',
                'value': par.val,
                'menuIndex': par.menuIndex,
                'menuNames': list(par.menuNames) if par.menuNames else [],
                'menuLabels': list(par.menuLabels) if par.menuLabels else []
            }
        else:
            return {'type': 'unknown', 'value': str(par.val)}
    except Exception as e:
        return {'type': 'error', 'error': str(e)}


def capture_all_params(op):
    """Capture all parameters from an operator."""
    params = {}
    for par in op.pars():
        try:
            params[par.name] = {
                'value': capture_param_value(par),
                'default': par.default,
                'page': par.page.name if par.page else '',
                'label': par.label,
                'readOnly': par.readOnly,
                'expression': par.expr if hasattr(par, 'mode') and par.mode == ParMode.EXPRESSION else None,
            }
        except Exception as e:
            params[par.name] = {'error': str(e)}
    return params


def perturb_all_params(op):
    """
    Set every parameter to a non-default value.
    This forces TD to write them to .parm files.
    Returns dict of perturbed values.
    """
    perturbed = {}

    for par in op.pars():
        try:
            # Use readOnly (not isReadOnly) - TD Python API
            if par.readOnly or par.isPulse:
                perturbed[par.name] = capture_param_value(par)
                continue

            original = par.val
            default = par.default

            if par.isFloat:
                # Nudge by small amount
                new_val = (default if default is not None else 0) + 0.12345
                par.val = new_val
            elif par.isInt:
                new_val = (default if default is not None else 0) + 1
                par.val = new_val
            elif par.isString:
                new_val = (default if default else '') + '_perturbed'
                par.val = new_val
            elif par.isToggle:
                new_val = not (default if default is not None else False)
                par.val = new_val
            elif par.isMenu:
                # Cycle to next menu item
                current_idx = par.menuIndex
                num_items = len(par.menuNames) if par.menuNames else 1
                new_idx = (current_idx + 1) % num_items
                par.menuIndex = new_idx
            elif par.isOP:
                # Can't easily perturb OP references
                pass

            perturbed[par.name] = capture_param_value(par)

        except Exception as e:
            perturbed[par.name] = {'type': 'error', 'error': str(e)}

    return perturbed


# ============================================================================
# MAIN SAMPLING FUNCTION
# ============================================================================

def get_td_create_name(kb_name, family):
    """Convert KB operator name to TouchDesigner create name."""
    if kb_name in CREATE_NAME_OVERRIDES:
        return CREATE_NAME_OVERRIDES[kb_name]

    # Default conversion: Remove underscores, lowercase base, keep suffix
    # e.g., Blur_TOP -> blurTOP
    if '_' in kb_name:
        parts = kb_name.rsplit('_', 1)
        base = parts[0].replace('_', '').lower()
        suffix = parts[1]
        return f"{base}{suffix}"
    else:
        return kb_name.lower()


def sample_operator(kb_name, family, parent_op):
    """
    Create a sample COMP containing default and perturbed versions of an operator.
    Returns (success, error_message)
    """
    if kb_name in SKIP_OPERATORS:
        return False, "Skipped (documentation/abstract)"

    td_create_name = get_td_create_name(kb_name, family)
    safe_name = kb_name.replace(' ', '_')

    try:
        # Create container COMP
        container = parent_op.create(baseCOMP, f'sample_{safe_name}')
        container.viewer = False

        # Try to create the operator with default values
        try:
            op_default = container.create(td_create_name, 'op_default')
        except Exception as e:
            container.destroy()
            return False, f"Cannot create {td_create_name}: {e}"

        # Capture default parameters
        defaults = capture_all_params(op_default)

        # Create second instance for perturbing
        op_perturbed = container.create(td_create_name, 'op_perturbed')

        # Perturb all parameters
        perturbed = perturb_all_params(op_perturbed)

        # Save JSONs
        defaults_path = f"{PARAMS_DIR}/{family}_{safe_name}_defaults.json"
        perturbed_path = f"{PARAMS_DIR}/{family}_{safe_name}_perturbed.json"

        defaults_output = {
            'operator': kb_name,
            'family': family,
            'td_create_name': td_create_name,
            'param_count': len(defaults),
            'parameters': defaults
        }

        perturbed_output = {
            'operator': kb_name,
            'family': family,
            'td_create_name': td_create_name,
            'param_count': len(perturbed),
            'parameters': perturbed
        }

        with open(defaults_path, 'w', encoding='utf-8') as f:
            json.dump(defaults_output, f, indent=2, default=str)

        with open(perturbed_path, 'w', encoding='utf-8') as f:
            json.dump(perturbed_output, f, indent=2, default=str)

        # Save .tox
        tox_path = f"{TOX_DIR}/{family}_{safe_name}.tox"
        container.save(tox_path)

        # Clean up (optional - comment out to keep in project)
        container.destroy()

        return True, None

    except Exception as e:
        # Clean up on error
        try:
            container.destroy()
        except:
            pass
        return False, str(e)


def run_sampling(families=None, limit_per_family=None):
    """
    Main entry point. Run the sampling process.

    Args:
        families: List of families to process, or None for all
        limit_per_family: Max operators per family (for testing), or None for all
    """
    # Load operator types
    try:
        with open(OPERATOR_TYPES_PATH, 'r', encoding='utf-8') as f:
            op_data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Operator types file not found: {OPERATOR_TYPES_PATH}")
        print("Run extract_all_operators.py first!")
        return

    operators = op_data.get('operators', {})

    if families is None:
        families = list(operators.keys())

    # Get or create workspace
    workspace = op('/project1')

    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }

    total = sum(len(operators.get(f, [])) for f in families)
    processed = 0

    print(f"=" * 60)
    print(f"TouchDesigner Operator Sampler")
    print(f"=" * 60)
    print(f"Output: {OUTPUT_BASE}")
    print(f"Families: {families}")
    print(f"Total operators: {total}")
    print(f"=" * 60)

    for family in families:
        family_ops = operators.get(family, [])

        if limit_per_family:
            family_ops = family_ops[:limit_per_family]

        print(f"\n[{family}] Processing {len(family_ops)} operators...")

        for op_info in family_ops:
            kb_name = op_info['name']
            processed += 1

            success, error = sample_operator(kb_name, family, workspace)

            if success:
                results['success'].append(kb_name)
                status = "OK"
            elif error and "Skipped" in error:
                results['skipped'].append(kb_name)
                status = "SKIP"
            else:
                results['failed'].append({'name': kb_name, 'error': error})
                status = "FAIL"

            print(f"  [{processed}/{total}] {kb_name}: {status}")

    # Summary
    print(f"\n" + "=" * 60)
    print(f"COMPLETE")
    print(f"=" * 60)
    print(f"Success: {len(results['success'])}")
    print(f"Failed:  {len(results['failed'])}")
    print(f"Skipped: {len(results['skipped'])}")

    # Save results log
    results_path = f"{OUTPUT_BASE}/sampling_results.json"
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {results_path}")

    if results['failed']:
        print(f"\nFailed operators:")
        for fail in results['failed'][:10]:
            print(f"  {fail['name']}: {fail['error']}")
        if len(results['failed']) > 10:
            print(f"  ... and {len(results['failed']) - 10} more")

    return results


# ============================================================================
# RUN
# ============================================================================

# Test with just a few operators first:
# run_sampling(families=['CHOP'], limit_per_family=5)

# Run all:
# run_sampling()

# Run specific families:
# run_sampling(families=['CHOP', 'TOP'])

print("Operator Sampler loaded. Run with:")
print("  run_sampling()  # All operators")
print("  run_sampling(families=['CHOP'], limit_per_family=5)  # Test run")
