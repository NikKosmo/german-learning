#!/usr/bin/env python3
"""
Test script to verify metadata sync fix
Validates that insert_cards.py correctly counts actual cards
"""

import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths

DECK_FILE = paths.DECK_FILE

def count_actual_cards():
    """Count actual card rows in the deck file"""
    with open(DECK_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    actual_count = 0
    for line in lines:
        # Count table rows (skip header and separator)
        if line.startswith('|') and not line.startswith('| ID |') and not line.startswith('|-'):
            actual_count += 1

    return actual_count

def get_metadata_count():
    """Get card count from metadata"""
    with open(DECK_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    for line in lines:
        if line.startswith('- Total cards:'):
            return int(line.split(':')[1].strip())

    return None

def main():
    print("=" * 60)
    print("METADATA SYNC VERIFICATION")
    print("=" * 60)
    print()

    actual = count_actual_cards()
    metadata = get_metadata_count()

    print(f"Actual cards in table:  {actual}")
    print(f"Metadata card count:    {metadata}")
    print()

    if actual == metadata:
        print("✅ SYNC OK - Metadata matches actual card count")
        return 0
    else:
        diff = actual - metadata
        print(f"❌ SYNC ERROR - Metadata is off by {diff} cards")
        print()
        print("Run insert_cards.py with empty pending_cards.json to fix:")
        print('  echo \'{"cards": []}\' > pending_cards.json')
        print('  python3 insert_cards.py')
        return 1

if __name__ == '__main__':
    sys.exit(main())
