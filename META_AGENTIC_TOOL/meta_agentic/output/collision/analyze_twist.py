import requests
import json
import math

API_URL = "http://127.0.0.1:9981/api/td/server/exec"
MAX_TWIST_PER_STEP = math.pi / 32  # ≈ 0.098 radians ≈ 5.6°

def get_color_values(major_indices):
    """Get Color(0) values for given major indices at minorIndex=0 in ring 0"""
    rows = [1 + idx * 32 for idx in major_indices]

    # Build tuple expression
    expr = "(" + ", ".join([f"op('/cord_physics/popto_glsl_torus')[{row}, 4].val" for row in rows]) + ")"

    payload = {"script": expr}
    response = requests.post(API_URL, headers={"Content-Type": "application/json"}, data=json.dumps(payload))

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            return [float(v) for v in data["data"]["result"]]
    return None

def analyze_twist():
    """Analyze twist angles across all spine points"""
    print("Analyzing torus twist (Color(0) column)...\n")

    # Sample all major indices (0-511)
    batch_size = 10  # Process in batches to avoid overwhelming the API
    all_values = []
    all_indices = []

    for start in range(0, 512, batch_size):
        end = min(start + batch_size, 512)
        indices = list(range(start, end))
        values = get_color_values(indices)

        if values:
            all_values.extend(values)
            all_indices.extend(indices)
            print(f"Sampled majorIndex {start}-{end-1}")
        else:
            print(f"Failed to get data for majorIndex {start}-{end-1}")
            break

    if len(all_values) < 512:
        print(f"\nWarning: Only got {len(all_values)} values out of 512")
        return

    # Calculate twist differences
    print("\n" + "="*80)
    print("TWIST ANALYSIS - Checking for excessive twist (>0.098 rad/step)")
    print("="*80 + "\n")

    excessive_twist = []

    for i in range(len(all_values) - 1):
        diff = all_values[i+1] - all_values[i]
        abs_diff = abs(diff)

        if abs_diff > MAX_TWIST_PER_STEP:
            excessive_twist.append({
                'from_major': all_indices[i],
                'to_major': all_indices[i+1],
                'from_value': all_values[i],
                'to_value': all_values[i+1],
                'difference': diff,
                'abs_difference': abs_diff,
                'ratio': abs_diff / MAX_TWIST_PER_STEP
            })

    # Report findings
    if excessive_twist:
        print(f"Found {len(excessive_twist)} locations with excessive twist:\n")

        for item in excessive_twist:
            print(f"majorIndex {item['from_major']} -> {item['to_major']}:")
            print(f"  Twist: {item['from_value']:.4f} -> {item['to_value']:.4f}")
            print(f"  Difference: {item['difference']:.4f} rad ({abs(item['difference']) * 180 / math.pi:.2f} deg)")
            print(f"  Exceeds limit by: {item['ratio']:.2f}x")
            print(f"  Row range: {1 + item['from_major']*32} -> {1 + item['to_major']*32}")
            print()
    else:
        print("No excessive twist found! All transitions are smooth.")

    # Statistics
    print("\n" + "="*80)
    print("STATISTICS")
    print("="*80 + "\n")

    diffs = [abs(all_values[i+1] - all_values[i]) for i in range(len(all_values) - 1)]
    print(f"Total spine points sampled: {len(all_values)}")
    print(f"Mean twist per step: {sum(diffs)/len(diffs):.4f} rad ({sum(diffs)/len(diffs) * 180/math.pi:.2f} deg)")
    print(f"Max twist per step: {max(diffs):.4f} rad ({max(diffs) * 180/math.pi:.2f} deg)")
    print(f"Min twist per step: {min(diffs):.6f} rad ({min(diffs) * 180/math.pi:.4f} deg)")
    print(f"Threshold: {MAX_TWIST_PER_STEP:.4f} rad ({MAX_TWIST_PER_STEP * 180/math.pi:.2f} deg)")

    # Check for discontinuities (jumps > pi)
    print("\n" + "="*80)
    print("DISCONTINUITY CHECK (jumps > pi)")
    print("="*80 + "\n")

    discontinuities = []
    for i in range(len(all_values) - 1):
        diff = abs(all_values[i+1] - all_values[i])
        if diff > math.pi:
            discontinuities.append({
                'from_major': all_indices[i],
                'to_major': all_indices[i+1],
                'from_value': all_values[i],
                'to_value': all_values[i+1],
                'difference': diff
            })

    if discontinuities:
        print(f"Found {len(discontinuities)} discontinuities:\n")
        for item in discontinuities:
            print(f"majorIndex {item['from_major']} -> {item['to_major']}:")
            print(f"  Twist: {item['from_value']:.4f} -> {item['to_value']:.4f}")
            print(f"  Jump: {item['difference']:.4f} rad ({item['difference'] * 180/math.pi:.2f} deg)")
            print()
    else:
        print("No discontinuities found.")

if __name__ == "__main__":
    analyze_twist()
