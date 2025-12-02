#!/usr/bin/env python3
"""
Audio file checker utility for German flashcard generation.
Checks if audio files exist before creating cards.

Supports two audio sources:
1. Generated WAV files (audio/generated_audio/) - Piper TTS generated
2. Legacy MP3 files (audio/words_from_duolinguo/) - Original Duolingo files

Priority: WAV files are checked first, then MP3 files.

Usage:
    from audio_checker import check_audio, get_audio_path

    audio_path = check_audio("Tisch")
    if audio_path:
        print(f"Audio found: {audio_path}")
    else:
        print("Audio missing!")
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths

# Audio directories (checked in priority order)
AUDIO_DIRS = [
    {
        'path': paths.AUDIO_GENERATED,
        'extension': '.wav',
        'description': 'Generated (Piper TTS)'
    },
    {
        'path': paths.AUDIO_DUOLINGO,
        'extension': '.mp3',
        'description': 'Legacy (Duolingo)'
    }
]

def check_audio(word):
    """
    Check if audio file exists for a given German word.
    Checks both WAV (generated) and MP3 (legacy) directories.

    Uses case-insensitive matching to handle different word casings:
    - "sehr" (lowercase adverb) → "Sehr.mp3"
    - "Mann" (capitalized noun) → "Mann.mp3"
    - "Frau" (capitalized) → "frau.mp3" (if file is lowercase)

    Args:
        word (str): German word to check (e.g., "Tisch", "Büro", "sehr")

    Returns:
        str: Filename if audio exists (e.g., "Tisch.wav" or "Sehr.mp3"), None otherwise
    """
    if not word:
        return None

    # Try multiple casing variations
    variations = [
        word[0].upper() + word[1:],  # Capitalize first letter (most common for audio files)
        word,                         # Exact match
        word.lower(),                # All lowercase
        word.upper(),                # All uppercase
    ]

    # Remove duplicates while preserving order
    variations = list(dict.fromkeys(variations))

    # Check each audio directory in priority order
    for audio_dir in AUDIO_DIRS:
        # Try each variation
        for variant in variations:
            filename = f"{variant}{audio_dir['extension']}"
            filepath = audio_dir['path'] / filename

            if filepath.exists():
                return filename

        # If no exact match found, do case-insensitive search in directory
        if audio_dir['path'].exists():
            try:
                files = [f.name for f in audio_dir['path'].iterdir() if f.is_file()]
                word_lower = word.lower()

                for file in files:
                    # Check if filename (without extension) matches word (case-insensitive)
                    file_base = Path(file).stem.lower()
                    if file_base == word_lower and file.endswith(audio_dir['extension']):
                        return file  # Return actual filename with correct casing
            except OSError:
                pass  # Directory access error, continue to next

    return None

def get_audio_field(word):
    """
    Get Anki-formatted audio field for a word.

    Args:
        word (str): German word (e.g., "Tisch")

    Returns:
        str: Anki audio format "[sound:Tisch.mp3]" or empty string if missing
    """
    audio_file = check_audio(word)
    if audio_file:
        return f"[sound:{audio_file}]"
    return ""

def check_multiple_words(words):
    """
    Check audio availability for multiple words.

    Args:
        words (list): List of German words to check

    Returns:
        dict: {
            'found': [(word, filename), ...],
            'missing': [word, ...]
        }
    """
    found = []
    missing = []

    for word in words:
        audio = check_audio(word)
        if audio:
            found.append((word, audio))
        else:
            missing.append(word)

    return {
        'found': found,
        'missing': missing
    }

def print_audio_report(words, word_type="words"):
    """
    Print a formatted report of audio availability.

    Args:
        words (list): List of German words to check
        word_type (str): Description of word type (e.g., "nouns", "verbs")
    """
    result = check_multiple_words(words)

    print(f"\n🎵 Audio Availability Report for {len(words)} {word_type}")
    print("=" * 60)

    print(f"\n✅ Found ({len(result['found'])})")
    for word, filename in result['found']:
        print(f"   • {word:20} → {filename}")

    if result['missing']:
        print(f"\n❌ Missing ({len(result['missing'])})")
        for word in result['missing']:
            print(f"   • {word}")
        print(f"\n⚠️  Add missing words to audio/MISSING_AUDIO.md")
    else:
        print(f"\n✅ All audio files present!")

    print("=" * 60)

    return result


if __name__ == "__main__":
    # Test with example words
    test_words = ["Tisch", "Baum", "Stadt", "Straße", "Buch", "Fenster", "Büro", "Männer"]
    print_audio_report(test_words, "test nouns")
