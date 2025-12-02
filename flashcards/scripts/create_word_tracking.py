#!/usr/bin/env python3
"""
Create word_tracking.md from cleaned_german_words.md
Checks audio availability and deck status
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths
from audio_checker import check_audio as get_audio_filename

# Paths
CLEANED_WORDS = paths.CLEANED_WORDS_FILE
WORD_TRACKING = paths.WORD_TRACKING_FILE
DECK_FILE = paths.DECK_FILE

# Note: Audio checking now handled by audio_checker.py

def read_cleaned_words():
    """Read all words from cleaned list"""
    words = []
    with open(CLEANED_WORDS, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Format: "123. word" - extract word only
            parts = line.split('.', 1)
            if len(parts) == 2:
                word = parts[1].strip()
                if word:
                    words.append(word)
    return words

def read_words_in_deck():
    """Get set of words already in deck (lowercase for comparison)"""
    in_deck = set()
    try:
        with open(DECK_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            # Extract German words from table (column 5)
            for line in content.split('\n'):
                if line.startswith('|') and 'Reverse' in line or 'Cloze' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 6:
                        german = parts[5]  # German column
                        # Extract base word (remove articles, cloze markers)
                        german = german.replace('der ', '').replace('die ', '').replace('das ', '')
                        german = german.replace('{{c1::', '').replace('}}', '')
                        german = german.split()[0] if german else ''  # First word
                        if german:
                            in_deck.add(german.lower())
    except FileNotFoundError:
        pass
    return in_deck

def check_audio(word):
    """Check if audio exists for word using audio_checker.py"""
    audio_file = get_audio_filename(word)
    if audio_file:
        return f"✅ {audio_file}"
    return "❌ missing"

def create_tracking_file():
    """Create word_tracking.md"""
    print("Reading cleaned words list...")
    words = read_cleaned_words()
    print(f"Found {len(words)} words")

    print("\nChecking deck status...")
    in_deck = read_words_in_deck()
    print(f"Found {len(in_deck)} words already in deck")

    print("\nGenerating word_tracking.md...")

    # Count statuses
    stats = {
        'in_deck': 0,
        'pending': 0,
        'missing_audio': 0
    }

    with open(WORD_TRACKING, 'w', encoding='utf-8') as f:
        # Header
        f.write("# Word Tracking\n\n")
        f.write("**Purpose:** Track all words from cleaned list and their processing status\n\n")
        f.write("**Status values:**\n")
        f.write("- `in_deck` - Already added to german_vocabulary_b1.md\n")
        f.write("- `pending` - Not processed yet, has audio\n")
        f.write("- `missing_audio` - No audio file found\n")
        f.write("- `error` - Generation/validation failed\n\n")
        f.write("---\n\n")

        # Table header
        f.write("| Word | Status | Audio | IPA | Word Type | Date Added | Notes |\n")
        f.write("|------|--------|-------|-----|-----------|------------|-------|\n")

        # Process each word
        for word in words:
            word_lower = word.lower()

            # Determine status
            if word_lower in in_deck:
                status = 'in_deck'
                date_added = '2025-11-08'
                stats['in_deck'] += 1
            else:
                # Check audio
                audio_check = check_audio(word)
                if '✅' in audio_check:
                    status = 'pending'
                    stats['pending'] += 1
                else:
                    status = 'missing_audio'
                    stats['missing_audio'] += 1
                date_added = '—'

            audio = check_audio(word)

            # Write row (IPA column initially empty)
            f.write(f"| {word} | {status} | {audio} | — | — | {date_added} | — |\n")

        # Footer with stats
        f.write("\n---\n\n")
        f.write("## Statistics\n\n")
        f.write(f"- **Total words:** {len(words)}\n")
        f.write(f"- **In deck:** {stats['in_deck']}\n")
        f.write(f"- **Pending (with audio):** {stats['pending']}\n")
        f.write(f"- **Missing audio:** {stats['missing_audio']}\n")
        f.write(f"- **Ready to process:** {stats['pending']}\n")

    print("\n" + "="*60)
    print("WORD TRACKING FILE CREATED")
    print("="*60)
    print(f"File: {WORD_TRACKING}")
    print(f"Total words: {len(words)}")
    print(f"In deck: {stats['in_deck']}")
    print(f"Pending (with audio): {stats['pending']}")
    print(f"Missing audio: {stats['missing_audio']}")
    print("="*60)

if __name__ == '__main__':
    create_tracking_file()
