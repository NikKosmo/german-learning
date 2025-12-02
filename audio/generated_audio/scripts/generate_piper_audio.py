#!/usr/bin/env python3
"""
Generate German audio using Piper TTS with de_DE-thorsten-high voice
Test script for 5 words with IPA transcriptions
"""

import subprocess
import os
from pathlib import Path

# Test words with their IPA transcriptions
TEST_WORDS = [
    {"word": "wissen", "ipa": "/ˈvɪsn̩/"},
    {"word": "sagen", "ipa": "/ˈzaːɡn̩/"},
    {"word": "denken", "ipa": "/ˈdɛŋkn̩/"},
    {"word": "stehen", "ipa": "/ˈʃteːən/"},
    {"word": "sollen", "ipa": "/ˈzɔlən/"},
]

# Voice model to use
VOICE = "de_DE-thorsten-high"

def download_voice_if_needed():
    """Download the voice model if not already present"""
    print(f"Downloading {VOICE} voice model...")
    # Piper will auto-download the model when first used
    pass

def generate_audio(word, output_dir):
    """Generate audio for a word using piper command line"""
    output_file = output_dir / f"{word}.wav"

    # Use local model files
    model_file = output_dir / "de_DE-thorsten-high.onnx"
    config_file = output_dir / "de_DE-thorsten-high.onnx.json"

    # Use piper command line tool
    # We'll use the word itself (text), not IPA, as piper handles German text natively
    cmd = [
        "python3", "-m", "piper",
        "--model", str(model_file),
        "--config", str(config_file),
        "--output_file", str(output_file)
    ]

    try:
        # Pass the word as stdin
        result = subprocess.run(
            cmd,
            input=word,
            text=True,
            capture_output=True,
            check=True
        )
        print(f"✅ Generated: {output_file.name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate {word}: {e.stderr}")
        return False
    except FileNotFoundError:
        print("❌ piper command not found. Trying alternative method...")
        return generate_audio_alt(word, output_file, model_file, config_file)

def generate_audio_alt(word, output_file, model_file, config_file):
    """Alternative method using piper Python API directly"""
    try:
        from piper import PiperVoice

        # Load voice from local model files
        voice = PiperVoice.load(str(model_file), config_path=str(config_file), use_cuda=False)

        # Synthesize and write WAV file
        with open(output_file, 'wb') as f:
            voice.synthesize_stream_raw(word, f)

        print(f"✅ Generated: {output_file.name}")
        return True
    except Exception as e:
        print(f"❌ Failed with alternative method: {e}")
        return False

def main():
    # Setup output directory
    script_dir = Path(__file__).parent
    output_dir = script_dir

    print(f"Piper TTS Audio Generation")
    print(f"=" * 50)
    print(f"Voice: {VOICE}")
    print(f"Output directory: {output_dir}")
    print()

    download_voice_if_needed()

    # Generate audio for each test word
    success_count = 0
    for item in TEST_WORDS:
        word = item["word"]
        ipa = item["ipa"]
        print(f"Generating: {word} {ipa}")
        if generate_audio(word, output_dir):
            success_count += 1

    print()
    print(f"=" * 50)
    print(f"Completed: {success_count}/{len(TEST_WORDS)} files generated")
    print()
    print("Test words with IPA:")
    for item in TEST_WORDS:
        print(f"  {item['word']:10} - {item['ipa']}")

if __name__ == "__main__":
    main()
