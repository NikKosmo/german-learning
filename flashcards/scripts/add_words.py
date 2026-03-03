#!/usr/bin/env python3
"""
Add new words to the German vocabulary pipeline.

Steps for each word:
1. Generates audio file using Piper TTS
2. Adds word row to word_tracking.md with status pending/missing_audio

Usage:
    python3 add_words.py --words "bearbeiten zuverlässig gedeckt"
    python3 add_words.py --words "aufräumen" --word-type Verb
    python3 add_words.py --file words.txt
    python3 add_words.py --words "etwas" --dry-run
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "audio" / "generated_audio" / "scripts"))

import paths

AUDIO_SCRIPTS_DIR = PROJECT_ROOT / "audio" / "generated_audio" / "scripts"


def word_in_tracking(word: str) -> bool:
    """Check if word already exists in word_tracking.md (case-insensitive)."""
    content = paths.WORD_TRACKING_FILE.read_text(encoding="utf-8")
    word_lower = word.lower()
    for line in content.splitlines():
        if line.startswith("|") and not line.startswith("|---") and "| Word |" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) > 1 and parts[1].lower() == word_lower:
                return True
    return False


def append_to_tracking(word: str, audio_filename: str | None, word_type: str = "—") -> None:
    """Append a new word row to the table in word_tracking.md."""
    content = paths.WORD_TRACKING_FILE.read_text(encoding="utf-8")

    if audio_filename:
        audio_col = f"✅ {audio_filename}"
        status = "pending"
    else:
        audio_col = "❌ missing"
        status = "missing_audio"

    new_row = f"| {word} | {status} | {audio_col} | — | {word_type} | — | — |"

    lines = content.splitlines()
    last_table_line = -1
    in_table = False
    for i, line in enumerate(lines):
        if "| Word | Status |" in line:
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            last_table_line = i
        elif in_table and not line.startswith("|"):
            break

    if last_table_line == -1:
        print(f"ERROR: Could not find word table in {paths.WORD_TRACKING_FILE}")
        return

    lines.insert(last_table_line + 1, new_row)
    paths.WORD_TRACKING_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_audio(word: str) -> tuple[bool, str | None, str]:
    """
    Generate audio for a word using AudioGenerator.

    Returns:
        (success, audio_filename, message)
    """
    from generate_audio import AudioGenerator

    try:
        generator = AudioGenerator(
            model_dir=AUDIO_SCRIPTS_DIR,
            output_dir=paths.AUDIO_GENERATED,
        )
    except FileNotFoundError as e:
        return False, None, f"Generator init failed: {e}"

    success, message = generator.process_word(word)
    if success:
        capitalized = generator.capitalize_word(word)
        filename_base = capitalized.replace(" ", "_")
        audio_filename = f"{filename_base}.wav"
        return True, audio_filename, message
    return False, None, message


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add words to German vocabulary pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --words "bearbeiten zuverlässig gedeckt"
  %(prog)s --words "aufräumen" --word-type Verb
  %(prog)s --file words.txt --word-type Noun
  %(prog)s --words "etwas" --dry-run
        """,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--words", help="Space-separated words to add")
    input_group.add_argument("--file", type=Path, help="File with one word per line")

    parser.add_argument(
        "--word-type",
        default="—",
        help="Word type for all words (Nomen, Verb, Adjektiv, Phrasal Verb, etc.)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without making changes",
    )

    args = parser.parse_args()

    # Collect words
    words: list[str] = []
    if args.words:
        words = [w.strip() for w in args.words.split() if w.strip()]
    elif args.file:
        lines = args.file.read_text(encoding="utf-8").splitlines()
        words = [line.strip() for line in lines if line.strip()]

    if not words:
        print("No words to process.")
        sys.exit(1)

    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"\n📚 {mode}Adding {len(words)} word(s) to German vocabulary pipeline")
    print("=" * 60)

    skipped = 0
    added_with_audio = 0
    added_missing_audio = 0

    for word in words:
        print(f"\n🔤  {word}")

        if word_in_tracking(word):
            print("     ⚠️  Already in word_tracking.md — skipping")
            skipped += 1
            continue

        if args.dry_run:
            print("     [DRY RUN] Would generate audio → Piper TTS")
            print("     [DRY RUN] Would add to word_tracking.md as pending")
            continue

        success, audio_filename, message = generate_audio(word)
        if success:
            print(f"     ✅ Audio: {message}")
            added_with_audio += 1
        else:
            print(f"     ❌ Audio failed: {message}")
            added_missing_audio += 1

        append_to_tracking(word, audio_filename, args.word_type)
        status_str = "pending (with audio)" if audio_filename else "missing_audio"
        print(f"     📋 Added to word_tracking.md: {status_str}")

    print("\n" + "=" * 60)
    if not args.dry_run:
        total = added_with_audio + added_missing_audio
        print(
            f"Done: {total} added ({added_with_audio} with audio, {added_missing_audio} missing audio)"
        )
        if skipped:
            print(f"Skipped (already in tracking): {skipped}")
        if added_with_audio > 0:
            print("\nNext step: run card_generator.py to generate flashcards")
            print("  python3 flashcards/scripts/card_generator.py")


if __name__ == "__main__":
    main()
