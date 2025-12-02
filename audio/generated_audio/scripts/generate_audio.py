#!/usr/bin/env python3
"""
German Audio Generation Tool using Piper TTS

A flexible, reusable tool for generating German audio files.
Independent of word_tracking.md - can be used for any word list.

Usage:
    # Single word
    python3 generate_audio.py --word "wissen" --output audio/generated_audio/

    # Multiple words
    python3 generate_audio.py --words "wissen sagen denken" --output audio/generated_audio/

    # From file (one word per line)
    python3 generate_audio.py --input-file words.txt --output audio/generated_audio/

    # Custom settings
    python3 generate_audio.py --input-file words.txt --output audio/generated_audio/ \
        --length-scale 1.5 --model-dir audio/piper_test/
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


class AudioGenerator:
    """Generates German audio files using Piper TTS"""

    def __init__(
        self,
        model_dir: Path,
        output_dir: Path,
        length_scale: float = 1.5,
        model_name: str = "de_DE-thorsten-high"
    ):
        self.model_dir = Path(model_dir)
        self.output_dir = Path(output_dir)
        self.length_scale = length_scale
        self.model_name = model_name

        # Model files
        self.model_file = self.model_dir / f"{model_name}.onnx"
        self.config_file = self.model_dir / f"{model_name}.onnx.json"

        # Validate model files exist
        if not self.model_file.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_file}")
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file}")

        # Create output directory if needed
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_audio(self, text: str, output_filename: str) -> Tuple[bool, str]:
        """
        Generate audio for given text

        Args:
            text: German text to synthesize
            output_filename: Output filename (e.g., "Wissen.wav")

        Returns:
            (success: bool, message: str)
        """
        output_path = self.output_dir / output_filename

        cmd = [
            "python3", "-m", "piper",
            "--model", str(self.model_file),
            "--config", str(self.config_file),
            "--length-scale", str(self.length_scale),
            "--output_file", str(output_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                input=text,
                text=True,
                capture_output=True,
                check=True,
                timeout=30
            )

            # Check file was created
            if output_path.exists():
                size_kb = output_path.stat().st_size / 1024
                return True, f"Generated {output_filename} ({size_kb:.1f} KB)"
            else:
                return False, f"File not created: {output_filename}"

        except subprocess.CalledProcessError as e:
            return False, f"Generation failed: {e.stderr}"
        except subprocess.TimeoutExpired:
            return False, f"Timeout after 30s"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def capitalize_word(self, word: str) -> str:
        """
        Capitalize first letter of word for filename
        Examples: "wissen" -> "Wissen", "der Mann" -> "Der Mann"
        """
        if not word:
            return word
        return word[0].upper() + word[1:]

    def process_word(self, word: str) -> Tuple[bool, str]:
        """Process a single word: generate audio and return result"""
        word = word.strip()
        if not word:
            return False, "Empty word"

        # Create filename: capitalize first letter, add .wav
        filename = f"{self.capitalize_word(word)}.wav"

        return self.generate_audio(word, filename)


def read_words_from_file(filepath: Path) -> List[str]:
    """Read words from file (one word per line)"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            words = [line.strip() for line in f if line.strip()]
        return words
    except Exception as e:
        print(f"❌ Error reading file {filepath}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate German audio files using Piper TTS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --word "wissen" --output audio/generated_audio/
  %(prog)s --words "wissen sagen denken" --output audio/generated_audio/
  %(prog)s --input-file words.txt --output audio/generated_audio/
  %(prog)s --input-file words.txt --output audio/generated_audio/ --length-scale 1.2
        """
    )

    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--word',
        help='Single word to generate'
    )
    input_group.add_argument(
        '--words',
        help='Space-separated list of words'
    )
    input_group.add_argument(
        '--input-file',
        type=Path,
        help='Input file with one word per line'
    )

    # Output options
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output directory for audio files'
    )

    # Model options
    parser.add_argument(
        '--model-dir',
        type=Path,
        default=Path(__file__).parent.parent.parent / 'piper_test',
        help='Directory containing Piper model files (default: audio/piper_test/)'
    )
    parser.add_argument(
        '--model-name',
        default='de_DE-thorsten-high',
        help='Model name (default: de_DE-thorsten-high)'
    )
    parser.add_argument(
        '--length-scale',
        type=float,
        default=1.5,
        help='Speech speed (1.0=normal, 1.5=50%% slower, default: 1.5)'
    )

    args = parser.parse_args()

    # Collect words to process
    words: List[str] = []
    if args.word:
        words = [args.word]
    elif args.words:
        words = args.words.split()
    elif args.input_file:
        words = read_words_from_file(args.input_file)

    if not words:
        print("❌ No words to process")
        sys.exit(1)

    # Initialize generator
    try:
        generator = AudioGenerator(
            model_dir=args.model_dir,
            output_dir=args.output,
            length_scale=args.length_scale,
            model_name=args.model_name
        )
    except Exception as e:
        print(f"❌ Failed to initialize generator: {e}")
        sys.exit(1)

    # Print header
    print("=" * 70)
    print("German Audio Generation (Piper TTS)")
    print("=" * 70)
    print(f"Model: {args.model_name}")
    print(f"Speed: {args.length_scale}x (1.0=normal, higher=slower)")
    print(f"Output: {args.output}/")
    print(f"Words to process: {len(words)}")
    print("=" * 70)
    print()

    # Process all words
    success_count = 0
    failed_words = []

    for i, word in enumerate(words, 1):
        success, message = generator.process_word(word)

        status = "✅" if success else "❌"
        print(f"{status} [{i:3d}/{len(words)}] {word:20s} - {message}")

        if success:
            success_count += 1
        else:
            failed_words.append((word, message))

    # Print summary
    print()
    print("=" * 70)
    print(f"Completed: {success_count}/{len(words)} files generated")
    print(f"Success rate: {success_count/len(words)*100:.1f}%")

    if failed_words:
        print()
        print("Failed words:")
        for word, message in failed_words:
            print(f"  - {word}: {message}")

    print("=" * 70)

    sys.exit(0 if success_count == len(words) else 1)


if __name__ == "__main__":
    main()
