#!/usr/bin/env python3
"""
German Sentence/Paragraph Audio Generation Tool using Piper TTS

A flexible tool for generating German audio from sentences, paragraphs, or longer text.

Usage:
    # Direct text input
    python3 generate_sentence.py --text "Guten Tag, wie geht es dir?" --output test.wav

    # From file
    python3 generate_sentence.py --input-file paragraph.txt --output paragraph.wav

    # Custom settings
    python3 generate_sentence.py --text "Hallo Welt" --output hello.wav --length-scale 1.2 --quality high
"""

import argparse
import subprocess
import sys
from pathlib import Path


def generate_sentence_audio(
    text: str,
    output_path: Path,
    model_dir: Path,
    model_name: str = "de_DE-thorsten-high",
    length_scale: float = 1.5
) -> tuple[bool, str]:
    """
    Generate audio for given text (sentence or paragraph)

    Args:
        text: German text to synthesize
        output_path: Output file path (e.g., Path("output.wav"))
        model_dir: Directory containing Piper model files
        model_name: Model name (default: de_DE-thorsten-high)
        length_scale: Speech speed (1.0=normal, 1.5=50% slower)

    Returns:
        (success: bool, message: str)
    """
    model_file = model_dir / f"{model_name}.onnx"
    config_file = model_dir / f"{model_name}.onnx.json"

    # Validate model files
    if not model_file.exists():
        return False, f"Model file not found: {model_file}"
    if not config_file.exists():
        return False, f"Config file not found: {config_file}"

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3", "-m", "piper",
        "--model", str(model_file),
        "--config", str(config_file),
        "--length-scale", str(length_scale),
        "--output_file", str(output_path)
    ]

    try:
        result = subprocess.run(
            cmd,
            input=text,
            text=True,
            capture_output=True,
            check=True,
            timeout=120  # 2 minutes for longer texts
        )

        # Check file was created
        if output_path.exists():
            size_kb = output_path.stat().st_size / 1024
            word_count = len(text.split())
            return True, f"Generated {output_path.name} ({size_kb:.1f} KB, {word_count} words)"
        else:
            return False, f"File not created: {output_path}"

    except subprocess.CalledProcessError as e:
        return False, f"Generation failed: {e.stderr}"
    except subprocess.TimeoutExpired:
        return False, "Timeout after 120s"
    except Exception as e:
        return False, f"Error: {str(e)}"


def read_text_from_file(filepath: Path) -> str:
    """Read text from file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"❌ Error reading file {filepath}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate German audio from sentences or paragraphs using Piper TTS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --text "Guten Tag!" --output hello.wav
  %(prog)s --input-file paragraph.txt --output paragraph.wav
  %(prog)s --text "Hallo" --output test.wav --length-scale 1.2 --quality low
        """
    )

    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--text',
        help='Text to generate (sentence or paragraph)'
    )
    input_group.add_argument(
        '--input-file',
        type=Path,
        help='Input file containing text'
    )

    # Output options
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output audio file (e.g., output.wav)'
    )

    # Model options
    parser.add_argument(
        '--model-dir',
        type=Path,
        default=Path(__file__).parent,  # Same directory as script
        help='Directory containing Piper model files (default: same as script location)'
    )
    parser.add_argument(
        '--quality',
        choices=['low', 'high'],
        default='high',
        help='Model quality (default: high)'
    )
    parser.add_argument(
        '--length-scale',
        type=float,
        default=1.5,
        help='Speech speed (1.0=normal, 1.5=50%% slower, default: 1.5)'
    )

    args = parser.parse_args()

    # Get text
    if args.text:
        text = args.text.strip()
    else:
        text = read_text_from_file(args.input_file)

    if not text:
        print("❌ No text to process")
        sys.exit(1)

    # Determine model name
    model_name = f"de_DE-thorsten-{args.quality}"

    # Print header
    print("=" * 70)
    print("German Sentence Audio Generation (Piper TTS)")
    print("=" * 70)
    print(f"Model: {model_name}")
    print(f"Speed: {args.length_scale}x (1.0=normal, higher=slower)")
    print(f"Output: {args.output}")
    print(f"Text length: {len(text.split())} words, {len(text)} characters")
    print("=" * 70)
    print()

    # Show text preview (first 200 chars)
    preview = text if len(text) <= 200 else text[:200] + "..."
    print(f"Text: {preview}")
    print()

    # Generate audio
    success, message = generate_sentence_audio(
        text=text,
        output_path=args.output,
        model_dir=args.model_dir,
        model_name=model_name,
        length_scale=args.length_scale
    )

    if success:
        print(f"✅ {message}")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"❌ {message}")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
