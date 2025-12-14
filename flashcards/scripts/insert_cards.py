#!/usr/bin/env python3
"""
Insert cards from pending_cards.json into german_vocabulary_b1.md
STABLE SCRIPT - Should not need modifications

Reads: pending_cards.json
Updates: german_vocabulary_b1.md
"""

import json
import sys
import hashlib
import time
from datetime import datetime
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths

# File paths
PENDING_CARDS = paths.FLASHCARDS_SCRIPTS / 'pending_cards.json'

# Required fields for each card (id will be generated, not required in JSON)
REQUIRED_FIELDS = [
    'card_type', 'word_type', 'russian', 'german',
    'extra', 'example_de', 'example_ru', 'notes', 'audio'
]

def validate_json_structure(data):
    """Validate JSON has correct structure"""
    if not isinstance(data, dict):
        return False, "Root must be an object"

    if 'cards' not in data:
        return False, "Missing 'cards' array"

    if not isinstance(data['cards'], list):
        return False, "'cards' must be an array"

    if len(data['cards']) == 0:
        return False, "'cards' array is empty"

    # Validate each card has required fields
    for i, card in enumerate(data['cards']):
        if not isinstance(card, dict):
            return False, f"Card {i} is not an object"

        for field in REQUIRED_FIELDS:
            if field not in card:
                return False, f"Card {i} missing required field: {field}"

    return True, "Valid"

def generate_card_id(german_word, card_type):
    """Generate unique 8-character hash for card ID"""
    timestamp = str(time.time())
    content = f"{german_word}_{card_type}_{timestamp}"
    hash_obj = hashlib.sha256(content.encode('utf-8'))
    return hash_obj.hexdigest()[:8]

def load_pending_cards():
    """Load and validate pending_cards.json"""
    print(f"Reading {PENDING_CARDS}...")

    try:
        with open(PENDING_CARDS, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {PENDING_CARDS} not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}")
        sys.exit(1)

    # Validate structure
    valid, message = validate_json_structure(data)
    if not valid:
        print(f"ERROR: Invalid JSON structure: {message}")
        sys.exit(1)

    print(f"✅ Valid JSON structure")
    print(f"✅ Found {len(data['cards'])} cards to insert")

    return data['cards']

def expand_reverse_card(card):
    """
    If card_type is 'Reverse', expand into two separate cards:
    - Reverse RU→DE
    - Reverse DE→RU

    Otherwise return list with single card.
    """
    if card['card_type'] == 'Reverse':
        # Create two cards with same data, different card_type
        card_ru_de = card.copy()
        card_ru_de['card_type'] = 'Reverse RU→DE'

        card_de_ru = card.copy()
        card_de_ru['card_type'] = 'Reverse DE→RU'

        return [card_ru_de, card_de_ru]
    else:
        # Cloze cards or other types - return as-is
        return [card]

def card_to_markdown_row(card):
    """Transform card JSON to markdown table row with generated ID"""
    # Generate unique ID based on German word and card type
    card_id = generate_card_id(card['german'], card['card_type'])

    return f"| {card_id} | {card['card_type']} | {card['word_type']} | {card['russian']} | {card['german']} | {card['extra']} | {card['example_de']} | {card['example_ru']} | {card['notes']} | {card['audio']} |"

def insert_cards_into_deck(cards):
    """Append card rows to end of german_vocabulary_b1.md"""
    DECK_FILE = paths.DECK_FILE
    print(f"\nReading {DECK_FILE}...")

    try:
        with open(DECK_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"ERROR: {DECK_FILE} not found")
        sys.exit(1)

    # Expand 'Reverse' cards into RU→DE and DE→RU pairs
    print(f"Expanding {len(cards)} JSON entries...")
    expanded_cards = []
    for card in cards:
        expanded_cards.extend(expand_reverse_card(card))

    print(f"✅ Expanded to {len(expanded_cards)} total cards (Reverse entries became 2 cards each)")

    # Convert cards to markdown rows
    print(f"Converting {len(expanded_cards)} cards to markdown...")
    card_rows = [card_to_markdown_row(card) for card in expanded_cards]

    # Append rows to end of file
    print(f"Appending {len(card_rows)} rows to end of file...")
    with open(DECK_FILE, 'a', encoding='utf-8') as f:
        for row in card_rows:
            f.write(row + '\n')

    print(f"✅ Appended {len(card_rows)} card rows")

    return len(card_rows)

def update_deck_metadata(card_count):
    """Update deck info (total cards, generation date)"""
    print(f"\nUpdating deck metadata...")

    DECK_FILE = paths.DECK_FILE
    with open(DECK_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    # Count actual cards in the table
    actual_count = 0
    for line in lines:
        # Count table rows (skip header and separator)
        if line.startswith('|') and not line.startswith('| ID |') and not line.startswith('|-'):
            actual_count += 1

    # Update "Total cards" line
    for i, line in enumerate(lines):
        if line.startswith('- Total cards:'):
            old_metadata_count = int(line.split(':')[1].strip())
            lines[i] = f'- Total cards: {actual_count}'
            print(f"✅ Updated card count: {old_metadata_count} (old metadata) → {actual_count} (actual cards in file)")
            print(f"   Added this session: {card_count} cards")
            break

    # Update "Generated" date
    today = datetime.now().strftime('%Y-%m-%d')
    for i, line in enumerate(lines):
        if line.startswith('- Generated:'):
            lines[i] = f'- Generated: {today}'
            print(f"✅ Updated generation date: {today}")
            break

    # Write back
    with open(DECK_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

def main():
    print("=" * 60)
    print("INSERT CARDS INTO DECK")
    print("=" * 60)
    print()

    # Load pending cards
    cards = load_pending_cards()

    # Insert into deck
    card_count = insert_cards_into_deck(cards)

    # Update metadata
    update_deck_metadata(card_count)

    print()
    print("=" * 60)
    print("INSERTION COMPLETE")
    print("=" * 60)
    print(f"Inserted: {card_count} cards")
    print(f"Updated: {paths.DECK_FILE}")
    print()
    print("Next steps:")
    print("1. Review the inserted cards in german_vocabulary_b1.md")
    print("2. Run: python3 generate_deck_from_md.py")
    print("3. Import german_vocabulary_b1.apkg into Anki")
    print("=" * 60)

if __name__ == '__main__':
    main()
