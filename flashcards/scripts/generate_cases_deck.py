#!/usr/bin/env python3
"""
Generate German Cases Anki deck from markdown file
Reads: german_cases_deck.md
Outputs: german_cases_deck.apkg
Logs: cases_deck_generation_YYYY-MM-DD_HH-MM.log

The MD file is the source of truth - this script only reads, never modifies it.
"""

import genanki
import re
from datetime import datetime
from pathlib import Path
import sys
import shutil
import tempfile

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths

# Configuration
LANGUAGE_PREFIX = "de"  # Language prefix for audio files
MD_FILE = paths.FLASHCARDS_DIR / 'german_cases_deck.md'
OUTPUT_FILE = paths.FLASHCARDS_DIR / 'german_cases_deck.apkg'
DECK_NAME = 'German Cases - Declension & Prepositions'
DECK_ID = 1234567891  # Fixed deck ID for consistency (different from vocabulary deck)

# Generate timestamped log filename
timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
LOG_FILE = paths.FLASHCARDS_SCRIPTS / f'cases_deck_generation_{timestamp}.log'

class Logger:
    """Simple logger that writes to both console and file"""
    def __init__(self, log_file):
        self.log_file = log_file
        self.log_buffer = []

    def log(self, message):
        print(message)
        self.log_buffer.append(message)

    def write_log(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.log_buffer))

logger = Logger(LOG_FILE)

# Shared CSS for all card types
SHARED_CSS = '''
    .card {
        font-family: Arial, sans-serif;
        font-size: 20px;
        text-align: center;
        color: #333;
        background-color: #f9f9f9;
        padding: 30px;
        max-width: 600px;
        margin: 0 auto;
    }

    .front .russian {
        font-size: 32px;
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 15px;
    }
    .front .hint {
        font-size: 16px;
        color: #7f8c8d;
        font-style: italic;
    }

    .back .german-word {
        font-size: 42px;
        margin-bottom: 15px;
        line-height: 1.3;
        color: #2c3e50;
        font-weight: bold;
    }

    .back .case-info {
        font-size: 20px;
        color: #34495e;
        margin-bottom: 20px;
        line-height: 1.5;
    }

    .case-badge {
        display: inline-block;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        margin: 5px;
        font-size: 16px;
    }

    .case-nominativ { background-color: #3498db; color: white; }
    .case-akkusativ { background-color: #e74c3c; color: white; }
    .case-dativ { background-color: #2ecc71; color: white; }
    .case-genitiv { background-color: #9b59b6; color: white; }

    .gender-m { color: #2196F3; font-weight: bold; }
    .gender-f { color: #E91E63; font-weight: bold; }
    .gender-n { color: #4CAF50; font-weight: bold; }

    hr {
        border: none;
        border-top: 2px solid #ecf0f1;
        margin: 25px 0;
    }

    .example {
        text-align: left;
        margin: 20px 0;
        padding: 15px;
        background-color: #fff;
        border-radius: 8px;
        border-left: 4px solid #3498db;
    }
    .example-de {
        font-size: 20px;
        color: #2c3e50;
        margin-bottom: 8px;
        font-style: italic;
    }
    .example-de strong {
        color: #2196F3;
        font-weight: bold;
        text-decoration: underline;
    }
    .example-ru {
        font-size: 17px;
        color: #7f8c8d;
    }

    .notes {
        font-size: 15px;
        color: #95a5a6;
        margin-top: 15px;
        font-style: italic;
        text-align: left;
    }

    .pattern-explanation {
        font-size: 18px;
        color: #34495e;
        background-color: #ecf0f1;
        padding: 10px;
        border-radius: 5px;
        margin: 15px 0;
    }

    .cloze {
        font-weight: bold;
        color: #2c3e50;
    }
'''

def create_note_models():
    """Create all note models for German cases deck"""

    models = {}

    # Model 1: Case Preposition RU→DE
    models['prep_ru_de'] = genanki.Model(
        1607392330,
        'German Case Preposition (RU→DE)',
        fields=[
            {'name': 'ID'},
            {'name': 'Russian'},
            {'name': 'Preposition'},
            {'name': 'Case'},
            {'name': 'Example_DE'},
            {'name': 'Example_RU'},
            {'name': 'Notes'},
            {'name': 'Audio'},
        ],
        templates=[{
            'name': 'Card',
            'qfmt': '''
                <div class="front">
                    <div class="russian">{{Russian}}</div>
                    <div class="hint">(предлог + падеж)</div>
                </div>
            ''',
            'afmt': '''
                <div class="back">
                    <div class="german-word">{{Preposition}}</div>
                    <div class="case-info">{{Case}}</div>
                    <hr>
                    <div class="example">
                        <div class="example-de">{{Example_DE}}</div>
                        <div class="example-ru">{{Example_RU}}</div>
                    </div>
                    <div class="notes">{{Notes}}</div>
                    {{Audio}}
                </div>
            ''',
        }],
        css=SHARED_CSS
    )

    # Model 1b: Case Preposition DE→RU
    models['prep_de_ru'] = genanki.Model(
        1607392330,  # Same model ID since it's bidirectional
        'German Case Preposition (RU→DE)',
        fields=[
            {'name': 'ID'},
            {'name': 'Russian'},
            {'name': 'Preposition'},
            {'name': 'Case'},
            {'name': 'Example_DE'},
            {'name': 'Example_RU'},
            {'name': 'Notes'},
            {'name': 'Audio'},
        ],
        templates=[{
            'name': 'Card 2',
            'qfmt': '''
                <div class="front">
                    <div class="russian">{{Preposition}}</div>
                    <div class="hint">(предлог • {{Case}})</div>
                </div>
            ''',
            'afmt': '''
                <div class="back">
                    <div class="german-word">{{Russian}}</div>
                    <hr>
                    <div class="example">
                        <div class="example-de">{{Example_DE}}</div>
                        <div class="example-ru">{{Example_RU}}</div>
                    </div>
                    <div class="notes">{{Notes}}</div>
                    {{Audio}}
                </div>
            ''',
        }],
        css=SHARED_CSS
    )

    # Model 2: Case Declension Cloze
    models['declension_cloze'] = genanki.Model(
        1607392331,
        'German Case Declension (Cloze)',
        fields=[
            {'name': 'ID'},
            {'name': 'Cloze_Text'},
            {'name': 'Case_Gender'},
            {'name': 'Pattern_Explanation'},
            {'name': 'Translation_RU'},
            {'name': 'Notes'},
        ],
        templates=[{
            'name': 'Card',
            'qfmt': '''
                <div class="front">
                    <div class="russian" style="font-size: 28px;">{{cloze:Cloze_Text}}</div>
                    <div class="hint">(артикль и окончание)</div>
                </div>
            ''',
            'afmt': '''
                <div class="back">
                    <div class="german-word" style="font-size: 32px;">{{cloze:Cloze_Text}}</div>
                    <div class="case-info">{{Case_Gender}}</div>
                    <div class="pattern-explanation">{{Pattern_Explanation}}</div>
                    <hr>
                    <div class="example-ru" style="text-align: center; font-size: 20px;">{{Translation_RU}}</div>
                    <div class="notes">{{Notes}}</div>
                </div>
            ''',
        }],
        model_type=genanki.Model.CLOZE,
        css=SHARED_CSS
    )

    # Model 3: Case Translation RU→DE
    models['translation_ru_de'] = genanki.Model(
        1607392332,
        'German Case Translation (RU↔DE)',
        fields=[
            {'name': 'ID'},
            {'name': 'Russian'},
            {'name': 'German'},
            {'name': 'Example_DE'},
            {'name': 'Example_RU'},
            {'name': 'Notes'},
            {'name': 'Audio'},
        ],
        templates=[{
            'name': 'Card',
            'qfmt': '''
                <div class="front">
                    <div class="russian">{{Russian}}</div>
                    <div class="hint">(перевод)</div>
                </div>
            ''',
            'afmt': '''
                <div class="back">
                    <div class="german-word" style="font-size: 28px;">{{German}}</div>
                    <hr>
                    <div class="notes">{{Notes}}</div>
                    {{Audio}}
                </div>
            ''',
        }],
        css=SHARED_CSS
    )

    # Model 3b: Case Translation DE→RU
    models['translation_de_ru'] = genanki.Model(
        1607392332,  # Same model ID since it's bidirectional
        'German Case Translation (RU↔DE)',
        fields=[
            {'name': 'ID'},
            {'name': 'Russian'},
            {'name': 'German'},
            {'name': 'Example_DE'},
            {'name': 'Example_RU'},
            {'name': 'Notes'},
            {'name': 'Audio'},
        ],
        templates=[{
            'name': 'Card 2',
            'qfmt': '''
                <div class="front">
                    <div class="russian">{{German}}</div>
                    <div class="hint">(перевод)</div>
                </div>
            ''',
            'afmt': '''
                <div class="back">
                    <div class="german-word" style="font-size: 28px;">{{Russian}}</div>
                    <hr>
                    <div class="notes">{{Notes}}</div>
                    {{Audio}}
                </div>
            ''',
        }],
        css=SHARED_CSS
    )

    # Model 4: Case Identification Cloze (without misleading article hint)
    models['case_id_cloze'] = genanki.Model(
        1607392333,
        'German Case Identification (Cloze)',
        fields=[
            {'name': 'ID'},
            {'name': 'Cloze_Text'},
            {'name': 'Case_Gender'},
            {'name': 'Pattern_Explanation'},
            {'name': 'Translation_RU'},
            {'name': 'Notes'},
        ],
        templates=[{
            'name': 'Card',
            'qfmt': '''
                <div class="front">
                    <div class="russian" style="font-size: 28px;">{{cloze:Cloze_Text}}</div>
                    <div class="hint">(падеж)</div>
                </div>
            ''',
            'afmt': '''
                <div class="back">
                    <div class="german-word" style="font-size: 32px;">{{cloze:Cloze_Text}}</div>
                    <div class="case-info">{{Case_Gender}}</div>
                    <div class="pattern-explanation">{{Pattern_Explanation}}</div>
                    <hr>
                    <div class="example-ru" style="text-align: center; font-size: 20px;">{{Translation_RU}}</div>
                    <div class="notes">{{Notes}}</div>
                </div>
            ''',
        }],
        model_type=genanki.Model.CLOZE,
        css=SHARED_CSS
    )

    return models

def parse_md_table(md_file):
    """Parse markdown table and extract card data"""
    logger.log(f"Reading MD file: {md_file}")

    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        logger.log(f"ERROR: File not found: {md_file}")
        logger.write_log()
        sys.exit(1)
    except Exception as e:
        logger.log(f"ERROR: Failed to read file: {e}")
        logger.write_log()
        sys.exit(1)

    # Find table section
    lines = content.split('\n')
    table_start = None

    for i, line in enumerate(lines):
        if line.startswith('| ID | Card Type'):
            table_start = i
            break

    if table_start is None:
        logger.log("ERROR: Could not find table header in MD file")
        logger.write_log()
        sys.exit(1)

    logger.log(f"Found table at line {table_start + 1}")

    # Skip header and separator lines
    data_start = table_start + 2
    cards = []

    for i, line in enumerate(lines[data_start:], start=data_start):
        line = line.strip()
        if not line or not line.startswith('|'):
            break  # End of table

        # Parse table row
        parts = [p.strip() for p in line.split('|')[1:-1]]  # Remove first and last empty elements

        if len(parts) != 10:
            logger.log(f"WARNING: Line {i + 1} has {len(parts)} columns (expected 10), skipping: {line[:50]}...")
            continue

        card = {
            'ID': parts[0],
            'Card_Type': parts[1],
            'Word_Type': parts[2],  # Not used for model selection, just metadata
            'Russian': parts[3],
            'German': parts[4],
            'Extra': parts[5],
            'Example_DE': parts[6],
            'Example_RU': parts[7],
            'Notes': parts[8],
            'Audio': parts[9],
        }

        cards.append(card)

    logger.log(f"Parsed {len(cards)} cards from table")
    return cards

def get_model_key(card_type):
    """Determine which note model to use based on card type.

    For cases deck, we use Card Type column directly (no word_types dependency).
    """

    # Preposition cards
    if card_type == 'Preposition RU→DE':
        return 'prep_ru_de'
    elif card_type == 'Preposition DE→RU':
        return 'prep_de_ru'

    # Declension cloze cards
    elif card_type == 'Cloze Declension':
        return 'declension_cloze'

    # Case identification cloze cards
    elif card_type == 'Case ID Cloze':
        return 'case_id_cloze'

    # Translation cards
    elif card_type == 'Translation RU→DE':
        return 'translation_ru_de'
    elif card_type == 'Translation DE→RU':
        return 'translation_de_ru'

    else:
        return None

def create_note_from_card(card, models):
    """Create a genanki Note from card data"""

    model_key = get_model_key(card['Card_Type'])

    if model_key not in models:
        logger.log(f"WARNING: Unknown card type '{card['Card_Type']}' for card {card['ID']}, skipping")
        return None

    model = models[model_key]

    # Build fields based on model type
    if 'prep' in model_key:
        # Preposition cards
        fields = [
            card['ID'],
            card['Russian'],
            card['German'],  # Preposition
            card['Extra'],   # Case (+ Dativ, etc.)
            card['Example_DE'],
            card['Example_RU'],
            card['Notes'],
            f"[sound:{card['Audio']}]" if card['Audio'] != '—' else '',
        ]

    elif 'declension_cloze' in model_key or 'case_id_cloze' in model_key:
        # Declension cloze cards or Case ID cloze cards (same field structure)
        fields = [
            card['ID'],
            card['German'],  # Cloze_Text with {{c1::}} format
            card['Extra'],   # Case_Gender (e.g., "Akkusativ • Maskulinum")
            card['Russian'],  # Pattern_Explanation
            card['Example_RU'],  # Translation_RU
            card['Notes'],
        ]

    elif 'translation' in model_key:
        # Translation cards
        fields = [
            card['ID'],
            card['Russian'],
            card['German'],
            card['Example_DE'],  # Not used currently
            card['Example_RU'],  # Not used currently
            card['Notes'],
            f"[sound:{card['Audio']}]" if card['Audio'] != '—' else '',
        ]

    else:
        logger.log(f"WARNING: Unhandled model type '{model_key}' for card {card['ID']}, skipping")
        return None

    # Create note with GUID set to our ID
    try:
        note = genanki.Note(
            model=model,
            fields=fields,
            guid=card['ID']  # Use our ID hash as GUID for Anki matching
        )
        return note
    except Exception as e:
        logger.log(f"ERROR: Failed to create note for card {card['ID']}: {e}")
        logger.log(f"  Model: {model_key}, Fields: {fields}")
        return None

def main():
    logger.log("=" * 70)
    logger.log("GERMAN CASES ANKI DECK GENERATION FROM MD")
    logger.log("=" * 70)
    logger.log(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.log("")

    # Create note models
    logger.log("Creating note models...")
    models = create_note_models()
    logger.log(f"Created {len(models)} note models")
    logger.log("")

    # Parse MD file
    cards = parse_md_table(MD_FILE)
    logger.log("")

    # Create deck
    logger.log(f"Creating deck: {DECK_NAME}")
    deck = genanki.Deck(DECK_ID, DECK_NAME)

    # Process each card
    logger.log("Processing cards...")
    successful = 0
    skipped = 0

    for card in cards:
        note = create_note_from_card(card, models)
        if note:
            deck.add_note(note)
            successful += 1
        else:
            skipped += 1

    logger.log(f"Successfully processed: {successful} cards")
    if skipped > 0:
        logger.log(f"Skipped: {skipped} cards (see warnings above)")
    logger.log("")

    # Collect media files (audio) with language prefix
    logger.log("Collecting media files...")
    media_files = []
    unique_audio = set()
    audio_mapping = {}  # original_filename -> prefixed_filename

    for card in cards:
        audio_file = card.get('Audio', '').strip()
        if audio_file and audio_file != '—':
            unique_audio.add(audio_file)

    # Create temp directory for prefixed audio files
    temp_dir = Path(tempfile.mkdtemp())

    # Build full paths to audio files (check both audio directories)
    audio_dirs = [paths.AUDIO_DUOLINGO, paths.AUDIO_GENERATED]

    for audio_file in unique_audio:
        found = False
        for audio_dir in audio_dirs:
            audio_path = audio_dir / audio_file
            if audio_path.exists():
                # Create prefixed filename
                prefixed_name = f"{LANGUAGE_PREFIX}_{audio_file}"
                prefixed_path = temp_dir / prefixed_name

                # Copy to temp with new name
                shutil.copy2(audio_path, prefixed_path)
                media_files.append(str(prefixed_path))
                audio_mapping[audio_file] = prefixed_name

                logger.log(f"  ✅ {audio_file} → {prefixed_name}")
                found = True
                break

        if not found:
            logger.log(f"  ⚠️  {audio_file} (not found)")

    logger.log(f"Found {len(media_files)} audio files")
    logger.log("")

    # Update all notes to reference prefixed audio files
    if audio_mapping:
        logger.log("Updating card audio references...")
        updated_count = 0
        for note in deck.notes:
            for field_idx, field_value in enumerate(note.fields):
                # Check if field contains [sound:filename] format
                if '[sound:' in field_value:
                    # Extract filename from [sound:filename]
                    match = re.search(r'\[sound:([^\]]+)\]', field_value)
                    if match:
                        original_filename = match.group(1)
                        if original_filename in audio_mapping:
                            # Replace with prefixed filename
                            prefixed_filename = audio_mapping[original_filename]
                            note.fields[field_idx] = f'[sound:{prefixed_filename}]'
                            updated_count += 1
        logger.log(f"Updated {updated_count} audio references in cards")
        logger.log("")

    # Generate package
    logger.log(f"Generating package: {OUTPUT_FILE}")
    try:
        genanki.Package(deck, media_files=media_files).write_to_file(OUTPUT_FILE)
        logger.log("✅ Package generated successfully!")
    except Exception as e:
        logger.log(f"❌ ERROR: Failed to generate package: {e}")
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.write_log()
        sys.exit(1)
    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

    logger.log("")
    logger.log("=" * 70)
    logger.log("SUMMARY")
    logger.log("=" * 70)
    logger.log(f"Input: {MD_FILE}")
    logger.log(f"Output: {OUTPUT_FILE}")
    logger.log(f"Deck: {DECK_NAME}")
    logger.log(f"Total cards: {successful}")
    logger.log(f"Log file: {LOG_FILE}")
    logger.log("")
    logger.log(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.log("=" * 70)

    # Write log file
    logger.write_log()
    logger.log(f"\nLog saved to: {LOG_FILE}")

if __name__ == '__main__':
    main()
