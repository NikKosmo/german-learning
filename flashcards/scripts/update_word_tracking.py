#!/usr/bin/env python3
"""
Update word_tracking.md based on current deck status
- Updates Status column based on german_vocabulary_b1.md
- Updates Audio column based on audio availability
- Preserves all other metadata (Word Type, IPA, Notes)
- Sets Date Added when status changes to in_deck
- Does NOT add new words automatically
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths
from flashcards.scripts.audio_checker import check_audio as get_audio_filename

"""
NOTE: Do not cache paths.DECK_FILE/WORD_TRACKING_FILE at import time because
tests may monkeypatch these values. Always resolve them at call time.
"""

def check_audio(word):
    """Check if audio exists for word using audio_checker.py"""
    audio_file = get_audio_filename(word)
    if audio_file:
        return f"✅ {audio_file}"
    return "❌ missing"

def read_words_in_deck():
    """
    Get words in deck with two matching strategies:
    - words_set: set of all words (for word-only matching when tracking has no type)
    - words_with_types: dict mapping word to set of types (for homonym matching)
    """
    words_set = set()
    words_with_types = {}

    deck_file = paths.DECK_FILE
    try:
        with open(deck_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Extract German words and word types from table
            for line in content.split('\n'):
                if line.startswith('|') and ('Reverse' in line or 'Cloze' in line):
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 6:
                        word_type = parts[3].strip()  # Word Type column
                        german = parts[5]              # German column
                        # Extract base word (remove cloze markers, take last word)
                        german = german.replace('{{c1::', '').replace('{{c2::', '').replace('}}', '')
                        german = german.split()[-1] if german else ''  # Last word (the actual vocabulary word)
                        if german:
                            word_lower = german.lower()
                            # Add to word-only set
                            words_set.add(word_lower)
                            # Add to type-specific dict
                            if word_type:
                                if word_lower not in words_with_types:
                                    words_with_types[word_lower] = set()
                                words_with_types[word_lower].add(word_type)
    except FileNotFoundError:
        print(f"WARNING: {deck_file} not found")

    return words_set, words_with_types

def update_tracking_file():
    """Update word_tracking.md with current status and audio info"""

    print("Reading current word tracking...")

    # Read existing tracking file
    tracking_file = paths.WORD_TRACKING_FILE
    with open(tracking_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Find table start
    table_start = None
    for i, line in enumerate(lines):
        if line.startswith('| Word | Status |'):
            table_start = i
            break

    if table_start is None:
        print("ERROR: Could not find table header in word_tracking.md")
        return

    # Get words in deck
    print("Checking deck status...")
    words_set, words_with_types = read_words_in_deck()
    print(f"Found {len(words_set)} unique words in deck")

    # Process table rows
    print("\nUpdating word tracking...")
    today = datetime.now().strftime('%Y-%m-%d')

    stats = {
        'in_deck': 0,
        'pending': 0,
        'missing_audio': 0,
        'error': 0
    }

    updated_rows = []
    header_line = lines[table_start]
    separator_line = lines[table_start + 1]

    updated_rows.append(header_line)
    updated_rows.append(separator_line)

    changes = []

    for i in range(table_start + 2, len(lines)):
        line = lines[i].strip()

        # Stop at end of table (empty line or stats section)
        if not line or line == '---' or line.startswith('##'):
            break

        if not line.startswith('|'):
            continue

        # Parse row
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 8:
            continue

        word = parts[1]
        old_status = parts[2]
        old_audio = parts[3]
        ipa = parts[4]
        word_type = parts[5]
        date_added = parts[6]
        notes = parts[7]

        # Update audio
        new_audio = check_audio(word)

        # Update status - two-tier matching strategy
        word_lower = word.lower()
        is_in_deck = False

        if word_type == '—' or not word_type.strip():
            # No word type specified → match on word alone (backward compatibility)
            is_in_deck = word_lower in words_set
        else:
            # Word type specified → match on (word, type) for homonym safety
            is_in_deck = (word_lower in words_with_types and
                         word_type.strip() in words_with_types[word_lower])

        if is_in_deck:
            new_status = 'in_deck'
            # If status changed to in_deck, update date
            if old_status != 'in_deck' and date_added == '—':
                date_added = today
                type_label = f" ({word_type})" if word_type != '—' else ""
                changes.append(f"  {word}{type_label}: {old_status} → in_deck (date: {today})")
            elif old_status != 'in_deck':
                type_label = f" ({word_type})" if word_type != '—' else ""
                changes.append(f"  {word}{type_label}: {old_status} → in_deck")
        else:
            # Not in deck - check audio
            if '✅' in new_audio:
                new_status = 'pending'
            elif old_status == 'error':
                new_status = 'error'  # Preserve error status
            else:
                new_status = 'missing_audio'

        # Track audio changes
        if old_audio != new_audio:
            changes.append(f"  {word}: audio {old_audio} → {new_audio}")

        # Update stats
        stats[new_status] = stats.get(new_status, 0) + 1

        # Write updated row
        updated_rows.append(f"| {word} | {new_status} | {new_audio} | {ipa} | {word_type} | {date_added} | {notes} |\n")

    # Write file
    print(f"\nWriting updated tracking file...")

    with open(tracking_file, 'w', encoding='utf-8') as f:
        # Write header section (everything before table)
        for line in lines[:table_start]:
            f.write(line)

        # Write updated table
        for row in updated_rows:
            f.write(row)

        # Write statistics
        f.write("\n---\n\n")
        f.write("## Statistics\n\n")
        total = sum(stats.values())
        f.write(f"- **Total words:** {total}\n")
        f.write(f"- **In deck:** {stats['in_deck']}\n")
        f.write(f"- **Pending (with audio):** {stats['pending']}\n")
        f.write(f"- **Missing audio:** {stats['missing_audio']}\n")
        if stats['error'] > 0:
            f.write(f"- **Error:** {stats['error']}\n")
        f.write(f"- **Ready to process:** {stats['pending']}\n")

    # Print summary
    print("\n" + "="*60)
    print("WORD TRACKING UPDATED")
    print("="*60)
    print(f"Total words: {total}")
    print(f"In deck: {stats['in_deck']}")
    print(f"Pending (with audio): {stats['pending']}")
    print(f"Missing audio: {stats['missing_audio']}")
    if stats['error'] > 0:
        print(f"Error: {stats['error']}")

    if changes:
        print("\nChanges made:")
        for change in changes:
            print(change)
    else:
        print("\nNo changes detected")

    print("="*60)

if __name__ == '__main__':
    update_tracking_file()
