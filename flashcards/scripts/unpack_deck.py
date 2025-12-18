#!/usr/bin/env python3
"""
Unpack Anki .apkg deck to JSON format

Usage:
    python3 unpack_deck.py <deck.apkg>
    python3 unpack_deck.py  # defaults to german_vocabulary_b1.apkg

Output:
    temp/deck_data.json - Complete card data with all fields
"""

import sqlite3
import zipfile
import json
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

try:
    import zstandard
    HAS_ZSTANDARD = True
except ImportError:
    HAS_ZSTANDARD = False

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths

# Configuration
DEFAULT_APKG = paths.FLASHCARDS_DIR / 'german_vocabulary_b1.apkg'
TEMP_DIR = PROJECT_ROOT / 'temp'
OUTPUT_FILE = TEMP_DIR / 'deck_data.json'

def extract_apkg(apkg_path, extract_to):
    """Extract .apkg file (it's a ZIP) to temporary directory"""
    print(f"Extracting {apkg_path.name}...")

    try:
        with zipfile.ZipFile(apkg_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"✅ Extracted to {extract_to}")
        return True
    except zipfile.BadZipFile:
        print(f"❌ ERROR: {apkg_path} is not a valid .apkg file")
        return False
    except Exception as e:
        print(f"❌ ERROR: Failed to extract: {e}")
        return False

def get_models_from_collection(db_path):
    """Extract model definitions from collection

    Handles both old format (JSON in col table) and new format (separate tables)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if we have the new schema (separate notetypes table)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notetypes'")
    has_notetypes_table = cursor.fetchone() is not None

    model_fields = {}

    if has_notetypes_table:
        # New format (Anki 2.1.50+): notetypes and fields are in separate tables
        cursor.execute("SELECT id, name, config FROM notetypes")
        notetypes = cursor.fetchall()

        for notetype_id, notetype_name, config_json in notetypes:
            # Get field names for this notetype
            cursor.execute("SELECT name, ord FROM fields WHERE ntid = ? ORDER BY ord", (notetype_id,))
            fields = cursor.fetchall()
            field_names = [field[0] for field in fields]

            model_fields[str(notetype_id)] = {
                'name': notetype_name,
                'fields': field_names
            }
    else:
        # Old format: models are stored as JSON in the col table
        cursor.execute("SELECT models FROM col")
        models_json = cursor.fetchone()[0]
        models = json.loads(models_json)

        # Parse models to get field names by model ID
        for model_id, model_data in models.items():
            model_name = model_data['name']
            field_names = [field['name'] for field in model_data['flds']]
            model_fields[model_id] = {
                'name': model_name,
                'fields': field_names
            }

    conn.close()
    return model_fields

def unpack_notes(db_path):
    """Extract all notes from Anki database"""
    print(f"Reading database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get model definitions first
    models = get_models_from_collection(db_path)

    # Query all notes
    cursor.execute("SELECT id, guid, mid, flds, tags FROM notes")
    rows = cursor.fetchall()

    print(f"Found {len(rows)} notes in database")

    cards = []
    for row in rows:
        note_id, guid, model_id, fields_str, tags = row

        # Split fields (separated by \x1f)
        field_values = fields_str.split('\x1f')

        # Get model info
        model_id_str = str(model_id)
        if model_id_str not in models:
            print(f"⚠️  Warning: Unknown model ID {model_id}")
            continue

        model_info = models[model_id_str]
        model_name = model_info['name']
        field_names = model_info['fields']

        # Map field names to values
        fields_dict = {}
        for i, field_name in enumerate(field_names):
            if i < len(field_values):
                # Clean up HTML tags and audio references for readability
                value = field_values[i].strip()
                fields_dict[field_name] = value
            else:
                fields_dict[field_name] = ''

        card = {
            'note_id': note_id,
            'guid': guid,
            'model_id': model_id,
            'model_name': model_name,
            'tags': tags,
            'fields': fields_dict
        }

        cards.append(card)

    conn.close()
    return cards

def get_deck_info(db_path):
    """Get deck name and ID from database

    Handles both old format (JSON in col table) and new format (separate tables)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if we have the new schema (separate decks table)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='decks'")
    has_decks_table = cursor.fetchone() is not None

    deck_info = []

    if has_decks_table:
        # New format (Anki 2.1.50+): decks in separate table
        cursor.execute("SELECT id, name FROM decks")
        decks = cursor.fetchall()
        for deck_id, deck_name in decks:
            deck_info.append({
                'id': deck_id,
                'name': deck_name
            })
    else:
        # Old format: decks stored as JSON in col table
        cursor.execute("SELECT decks FROM col")
        decks_json = cursor.fetchone()[0]
        decks = json.loads(decks_json)

        for deck_id, deck_data in decks.items():
            deck_info.append({
                'id': int(deck_id),
                'name': deck_data['name']
            })

    conn.close()
    return deck_info

def decompress_anki21b(extract_dir):
    """Decompress collection.anki21b if it exists (Anki 2.1.50+)

    Returns path to the database to use (either decompressed or original)
    """
    anki21b_path = extract_dir / 'collection.anki21b'
    anki2_path = extract_dir / 'collection.anki2'

    if anki21b_path.exists():
        print(f"Found newer format: collection.anki21b (compressed)")

        if not HAS_ZSTANDARD:
            print(f"⚠️  WARNING: zstandard library not installed")
            print(f"   Install with: pip install zstandard")
            print(f"   Falling back to collection.anki2 (may have incomplete data)")
            return anki2_path

        print(f"Decompressing collection.anki21b...")
        decompressed_path = extract_dir / 'collection_decompressed.anki2'

        try:
            dctx = zstandard.ZstdDecompressor()
            with open(anki21b_path, 'rb') as ifh:
                with open(decompressed_path, 'wb') as ofh:
                    dctx.copy_stream(ifh, ofh)
            print(f"✅ Decompressed successfully")
            return decompressed_path
        except Exception as e:
            print(f"❌ ERROR: Failed to decompress: {e}")
            print(f"   Falling back to collection.anki2")
            return anki2_path
    else:
        print(f"Using collection.anki2 (old format)")
        return anki2_path

def main():
    print("=" * 70)
    print("ANKI DECK UNPACKER")
    print("=" * 70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Get input file
    if len(sys.argv) > 1:
        apkg_path = Path(sys.argv[1])
        if not apkg_path.is_absolute():
            apkg_path = Path.cwd() / apkg_path
    else:
        apkg_path = DEFAULT_APKG
        print(f"No input file specified, using default: {apkg_path.name}")

    if not apkg_path.exists():
        print(f"❌ ERROR: File not found: {apkg_path}")
        sys.exit(1)

    print()

    # Create temp directory if it doesn't exist
    TEMP_DIR.mkdir(exist_ok=True)

    # Extract to temporary directory
    extract_dir = Path(tempfile.mkdtemp())

    try:
        if not extract_apkg(apkg_path, extract_dir):
            sys.exit(1)

        print()

        # Decompress collection.anki21b if it exists, otherwise use collection.anki2
        collection_db = decompress_anki21b(extract_dir)
        if not collection_db.exists():
            print(f"❌ ERROR: No valid collection database found in package")
            sys.exit(1)

        print()

        # Get deck info
        deck_info = get_deck_info(collection_db)
        print(f"Deck(s): {', '.join(d['name'] for d in deck_info)}")
        print()

        # Unpack all notes
        cards = unpack_notes(collection_db)

        # Prepare output data
        output_data = {
            'source_file': str(apkg_path),
            'extracted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'decks': deck_info,
            'total_cards': len(cards),
            'cards': cards
        }

        # Write to JSON
        print()
        print(f"Writing output to: {OUTPUT_FILE}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Successfully unpacked {len(cards)} cards")

    finally:
        # Cleanup temp extraction directory
        shutil.rmtree(extract_dir, ignore_errors=True)

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Input: {apkg_path}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Total cards: {len(cards)}")
    print()
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

if __name__ == '__main__':
    main()
