#!/usr/bin/env python3
"""
Test different speech speeds with Piper TTS using --length-scale parameter
Higher length_scale = slower speech (default is 1.0)
"""

import subprocess
from pathlib import Path

# Test with the Bremen sentence
TEST_SENTENCE = "Der Esel ging nach Bremen und wollte dort Stadtmusikant werden."

# Test different speeds
SPEEDS = [
    {"scale": 1.0, "name": "normal", "description": "Normal speed (default)"},
    {"scale": 1.2, "name": "slow_20", "description": "20% slower"},
    {"scale": 1.5, "name": "slow_50", "description": "50% slower"},
    {"scale": 1.8, "name": "slow_80", "description": "80% slower"},
]

def generate_with_speed(length_scale, speed_name, description):
    """Generate audio with specified speed"""
    script_dir = Path(__file__).parent
    model_path = script_dir / "de_DE-thorsten-high.onnx"
    config_path = script_dir / "de_DE-thorsten-high.onnx.json"
    output_file = script_dir / f"speed_test_{speed_name}.wav"

    cmd = [
        "python3", "-m", "piper",
        "--model", str(model_path),
        "--config", str(config_path),
        "--length-scale", str(length_scale),
        "--output_file", str(output_file)
    ]

    try:
        result = subprocess.run(
            cmd,
            input=TEST_SENTENCE,
            text=True,
            capture_output=True,
            check=True
        )

        size = output_file.stat().st_size / 1024
        print(f"✅ {description:25} (scale={length_scale}) → {output_file.name:25} ({size:.1f} KB)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed: {e.stderr}")
        return False

def main():
    print("Piper TTS Speed Test (High Quality)")
    print("=" * 80)
    print(f"Sentence: {TEST_SENTENCE}")
    print()
    print("Testing different speeds...")
    print()

    for speed in SPEEDS:
        generate_with_speed(speed["scale"], speed["name"], speed["description"])

    print()
    print("=" * 80)
    print("Listen to the files and choose your preferred speed!")
    print()
    print("Recommendations for language learning:")
    print("  • Beginners (A1-A2): 1.5-1.8 (slower speech)")
    print("  • Intermediate (B1): 1.2-1.5 (slightly slower)")
    print("  • Advanced (B2+): 1.0 (normal native speed)")

if __name__ == "__main__":
    main()
