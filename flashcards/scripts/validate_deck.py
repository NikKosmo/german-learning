#!/usr/bin/env python3
"""
Validate unpacked deck against source MD file

Usage:
    python3 validate_deck.py
    # Reads: temp/deck_data.json + german_vocabulary_b1.md
    # Outputs: temp/validation_report_YYYY-MM-DD_HH-MM.md

Validation checks:
1. Orphaned cards (in deck, not in MD source)
2. Missing cards (in MD, not in deck)
3. Gender/article consistency
4. Empty required fields
5. Invalid cloze syntax
6. Duplicate IDs
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths

# Configuration
TEMP_DIR = PROJECT_ROOT / 'temp'
DECK_DATA_FILE = TEMP_DIR / 'deck_data.json'
MD_SOURCE_FILE = paths.DECK_FILE
timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
REPORT_FILE = TEMP_DIR / f'validation_report_{timestamp}.md'

def load_deck_data():
    """Load unpacked deck data from JSON"""
    print(f"Loading deck data: {DECK_DATA_FILE}")

    if not DECK_DATA_FILE.exists():
        print(f"❌ ERROR: Deck data not found: {DECK_DATA_FILE}")
        print("Run unpack_deck.py first!")
        sys.exit(1)

    with open(DECK_DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"✅ Loaded {data['total_cards']} cards from deck")
    return data

def parse_md_source():
    """Parse the markdown source file and extract card IDs"""
    print(f"Loading source MD: {MD_SOURCE_FILE}")

    if not MD_SOURCE_FILE.exists():
        print(f"❌ ERROR: Source MD file not found: {MD_SOURCE_FILE}")
        sys.exit(1)

    with open(MD_SOURCE_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find table section
    lines = content.split('\n')
    table_start = None

    for i, line in enumerate(lines):
        if line.startswith('| ID | Card Type'):
            table_start = i
            break

    if table_start is None:
        print("❌ ERROR: Could not find table header in MD file")
        sys.exit(1)

    # Skip header and separator lines
    data_start = table_start + 2
    md_ids = set()
    md_cards = {}

    for i, line in enumerate(lines[data_start:], start=data_start):
        line = line.strip()
        if not line or not line.startswith('|'):
            break  # End of table

        # Parse table row
        parts = [p.strip() for p in line.split('|')[1:-1]]

        if len(parts) != 10:
            continue

        card_id = parts[0]
        md_ids.add(card_id)

        # Store full card data for comparison
        md_cards[card_id] = {
            'ID': parts[0],
            'Card_Type': parts[1],
            'Word_Type': parts[2],
            'Russian': parts[3],
            'German': parts[4],
            'Extra': parts[5],
            'Example_DE': parts[6],
            'Example_RU': parts[7],
            'Notes': parts[8],
            'Audio': parts[9],
        }

    print(f"✅ Found {len(md_ids)} unique card IDs in source")
    return md_ids, md_cards

def validate_gender_article(card):
    """Check if gender matches article in noun cards"""
    fields = card['fields']

    # Only check cards with Article field
    if 'Article' not in fields:
        return None

    article = fields.get('Article', '').strip().lower()
    gender = fields.get('Gender', '').strip().lower()

    if not article or not gender:
        return None

    # Check consistency
    expected_gender = {
        'der': 'm',
        'die': 'f',
        'das': 'n'
    }

    if article in expected_gender:
        if gender != expected_gender[article]:
            return f"Article '{article}' doesn't match gender '{gender}' (expected '{expected_gender[article]}')"

    return None

def validate_empty_fields(card):
    """Check for empty required fields"""
    fields = card['fields']
    issues = []

    # Fields that shouldn't be empty
    required_fields = ['Example_DE', 'Example_RU', 'Notes']

    for field_name in required_fields:
        if field_name in fields:
            value = fields[field_name].strip()
            # Remove HTML tags for checking
            value_clean = re.sub(r'<[^>]+>', '', value)
            if not value_clean or value_clean == '—':
                issues.append(f"Empty field: {field_name}")

    return issues if issues else None

def validate_cloze_syntax(card):
    """Validate cloze deletion syntax"""
    if 'Cloze' not in card['model_name']:
        return None

    fields = card['fields']

    # Find cloze field
    cloze_field = None
    for field_name, field_value in fields.items():
        if 'cloze' in field_name.lower() or '{{c' in field_value:
            cloze_field = field_value
            break

    if not cloze_field:
        return "No cloze syntax found in cloze card"

    # Check for valid cloze syntax
    if not re.search(r'\{\{c\d+::.+?\}\}', cloze_field):
        return f"Invalid cloze syntax: {cloze_field[:50]}..."

    return None

def generate_report(deck_data, md_ids, md_cards, orphaned, missing, validation_issues):
    """Generate markdown validation report"""
    print(f"Generating report: {REPORT_FILE}")

    lines = []
    lines.append("# Deck Validation Report")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"- **Cards in deck:** {deck_data['total_cards']}")
    lines.append(f"- **Unique IDs in source MD:** {len(md_ids)}")
    lines.append(f"- **Orphaned cards** (in deck, not in MD): **{len(orphaned)}**")
    lines.append(f"- **Missing cards** (in MD, not in deck): **{len(missing)}**")
    lines.append("")

    # Orphaned cards (main use case)
    if orphaned:
        lines.append("## 🗑️ Orphaned Cards (DELETE THESE IN ANKI)")
        lines.append("")
        lines.append(f"**Total: {len(orphaned)} cards**")
        lines.append("")
        lines.append("These cards exist in your Anki deck but are NOT in the source MD file.")
        lines.append("They were likely removed from the source for a reason (excluded categories, errors, etc.)")
        lines.append("")

        for i, card in enumerate(orphaned, 1):
            fields = card['fields']
            guid = card['guid']

            lines.append(f"### {i}. `{guid}`")
            lines.append("")

            # Show all relevant fields
            if 'Russian' in fields:
                lines.append(f"- **Russian:** {fields['Russian']}")

            # German field (handle different card types)
            if 'German' in fields:
                lines.append(f"- **German:** {fields['German']}")
            elif 'Cloze_German' in fields:
                lines.append(f"- **German:** {fields['Cloze_German']}")
            elif 'Infinitive' in fields:
                lines.append(f"- **German:** {fields['Infinitive']}")
            elif 'Base' in fields:
                lines.append(f"- **German:** {fields['Base']}")
            elif 'Preposition' in fields:
                lines.append(f"- **German:** {fields['Preposition']}")

            # Article for nouns
            if 'Article' in fields and fields['Article']:
                lines.append(f"- **Article:** {fields['Article']}")
            if 'Noun' in fields and fields['Noun']:
                lines.append(f"- **Noun:** {fields['Noun']}")

            # Extra info
            if 'Plural' in fields and fields['Plural']:
                lines.append(f"- **Plural:** {fields['Plural']}")
            if 'Perfekt' in fields and fields['Perfekt']:
                lines.append(f"- **Perfekt:** {fields['Perfekt']}")
            if 'Case' in fields and fields['Case']:
                lines.append(f"- **Case:** {fields['Case']}")

            lines.append(f"- **Card Type:** {card['model_name']}")

            if 'Example_DE' in fields and fields['Example_DE']:
                lines.append(f"- **Example (DE):** {fields['Example_DE'][:100]}...")
            if 'Example_RU' in fields and fields['Example_RU']:
                lines.append(f"- **Example (RU):** {fields['Example_RU'][:100]}...")

            if 'Notes' in fields and fields['Notes']:
                lines.append(f"- **Notes:** {fields['Notes'][:150]}...")

            lines.append("")
            lines.append("---")
            lines.append("")
    else:
        lines.append("## ✅ Orphaned Cards")
        lines.append("")
        lines.append("No orphaned cards found! All cards in deck exist in source MD.")
        lines.append("")

    # Missing cards
    if missing:
        lines.append("## ⚠️ Missing Cards (IN MD, NOT IN DECK)")
        lines.append("")
        lines.append(f"**Total: {len(missing)} IDs**")
        lines.append("")
        lines.append("These IDs exist in source MD but were not found in the deck.")
        lines.append("This might indicate a deck generation issue.")
        lines.append("")
        for card_id in missing:
            if card_id in md_cards:
                card_data = md_cards[card_id]
                lines.append(f"- `{card_id}` - {card_data['German']} ({card_data['Russian']})")
            else:
                lines.append(f"- `{card_id}`")
        lines.append("")
    else:
        lines.append("## ✅ Missing Cards")
        lines.append("")
        lines.append("No missing cards! All IDs from source MD exist in deck.")
        lines.append("")

    # Validation issues
    lines.append("## 🔍 Validation Issues")
    lines.append("")

    # Duplicate IDs
    if 'duplicate_ids' in validation_issues and validation_issues['duplicate_ids']:
        lines.append("### ❌ Duplicate IDs")
        lines.append("")
        for guid, count in validation_issues['duplicate_ids'].items():
            lines.append(f"- `{guid}` appears {count} times")
        lines.append("")
    else:
        lines.append("### ✅ Duplicate IDs")
        lines.append("No duplicate IDs found.")
        lines.append("")

    # Gender/Article mismatches
    if 'gender_mismatches' in validation_issues and validation_issues['gender_mismatches']:
        lines.append("### ❌ Gender/Article Mismatches")
        lines.append("")
        for issue in validation_issues['gender_mismatches']:
            lines.append(f"- **Card `{issue['guid']}`**: {issue['message']}")
        lines.append("")
    else:
        lines.append("### ✅ Gender/Article Consistency")
        lines.append("All noun cards have consistent gender/article pairs.")
        lines.append("")

    # Empty fields
    if 'empty_fields' in validation_issues and validation_issues['empty_fields']:
        lines.append("### ⚠️ Empty Required Fields")
        lines.append("")
        for issue in validation_issues['empty_fields']:
            lines.append(f"- **Card `{issue['guid']}`**: {', '.join(issue['issues'])}")
        lines.append("")
    else:
        lines.append("### ✅ Empty Fields")
        lines.append("No empty required fields found.")
        lines.append("")

    # Cloze syntax
    if 'cloze_errors' in validation_issues and validation_issues['cloze_errors']:
        lines.append("### ❌ Invalid Cloze Syntax")
        lines.append("")
        for issue in validation_issues['cloze_errors']:
            lines.append(f"- **Card `{issue['guid']}`**: {issue['message']}")
        lines.append("")
    else:
        lines.append("### ✅ Cloze Syntax")
        lines.append("All cloze cards have valid syntax.")
        lines.append("")

    # Write report
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"✅ Report generated: {REPORT_FILE}")

def main():
    print("=" * 70)
    print("DECK VALIDATOR")
    print("=" * 70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load deck data
    deck_data = load_deck_data()
    print()

    # Load source MD
    md_ids, md_cards = parse_md_source()
    print()

    # Extract deck IDs (GUIDs)
    deck_ids = set()
    deck_cards_by_id = {}

    for card in deck_data['cards']:
        guid = card['guid']
        deck_ids.add(guid)
        deck_cards_by_id[guid] = card

    print(f"Unique card IDs in deck: {len(deck_ids)}")
    print()

    # Find orphaned and missing cards
    print("Analyzing differences...")
    orphaned_ids = deck_ids - md_ids
    missing_ids = md_ids - deck_ids

    orphaned_cards = [deck_cards_by_id[guid] for guid in orphaned_ids]
    orphaned_cards.sort(key=lambda c: c['guid'])  # Sort by ID for consistent output

    print(f"Orphaned cards (in deck, not in MD): {len(orphaned_ids)}")
    print(f"Missing cards (in MD, not in deck): {len(missing_ids)}")
    print()

    # Run validation checks
    print("Running validation checks...")
    validation_issues = {
        'duplicate_ids': {},
        'gender_mismatches': [],
        'empty_fields': [],
        'cloze_errors': []
    }

    # Check for duplicate IDs
    id_counts = defaultdict(int)
    for card in deck_data['cards']:
        id_counts[card['guid']] += 1

    for guid, count in id_counts.items():
        if count > 1:
            validation_issues['duplicate_ids'][guid] = count

    # Validate each card
    for card in deck_data['cards']:
        guid = card['guid']

        # Gender/article check
        gender_issue = validate_gender_article(card)
        if gender_issue:
            validation_issues['gender_mismatches'].append({
                'guid': guid,
                'message': gender_issue
            })

        # Empty fields check
        empty_issue = validate_empty_fields(card)
        if empty_issue:
            validation_issues['empty_fields'].append({
                'guid': guid,
                'issues': empty_issue
            })

        # Cloze syntax check
        cloze_issue = validate_cloze_syntax(card)
        if cloze_issue:
            validation_issues['cloze_errors'].append({
                'guid': guid,
                'message': cloze_issue
            })

    print("✅ Validation complete")
    print()

    # Generate report
    generate_report(deck_data, md_ids, md_cards, orphaned_cards, missing_ids, validation_issues)

    print()
    print("=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)
    print(f"Report saved to: {REPORT_FILE}")
    print()
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

if __name__ == '__main__':
    main()
