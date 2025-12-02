#!/usr/bin/env python3
"""
Generate German sentence audio using Piper TTS with both low and high quality
Test with a sentence from Die Bremer Stadtmusikanten (public domain, 1819)
"""

import subprocess
from pathlib import Path

# Test sentence from Bremen Town Musicians (Die Bremer Stadtmusikanten)
# Public domain fairy tale by Brothers Grimm
SENTENCE = "Der Esel ging nach Bremen und wollte dort Stadtmusikant werden."

# Models to test
MODELS = [
    {"name": "low", "file": "de_DE-thorsten-low.onnx"},
    {"name": "high", "file": "de_DE-thorsten-high.onnx"}
]

def generate_audio_quality(quality_name, model_file, output_file):
    """Generate audio with specified quality"""
    script_dir = Path(__file__).parent
    model_path = script_dir / model_file
    config_path = script_dir / f"{model_file}.json"
    output_path = script_dir / output_file

    # Use piper command line
    cmd = [
        "python3", "-m", "piper",
        "--model", str(model_path),
        "--config", str(config_path),
        "--output_file", str(output_path)
    ]

    try:
        result = subprocess.run(
            cmd,
            input=SENTENCE,
            text=True,
            capture_output=True,
            check=True
        )

        # Get file size
        size = output_path.stat().st_size
        size_kb = size / 1024

        print(f"✅ {quality_name:5} quality: {output_file:25} ({size_kb:.1f} KB)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate {quality_name} quality: {e.stderr}")
        return False
    except FileNotFoundError as e:
        print(f"❌ Model not found: {model_file}")
        print(f"   Download from: https://huggingface.co/Thorsten-Voice/Piper/resolve/main/{model_file}")
        return False

def main():
    print("Piper TTS Sentence Quality Comparison")
    print("=" * 70)
    print(f"Sentence: {SENTENCE}")
    print(f"Length: {len(SENTENCE.split())} words")
    print()

    for model in MODELS:
        output_file = f"bremen_sentence_{model['name']}.wav"
        generate_audio_quality(model['name'], model['file'], output_file)

    print()
    print("=" * 70)
    print("Files generated in: audio/piper_test/")

if __name__ == "__main__":
    main()
