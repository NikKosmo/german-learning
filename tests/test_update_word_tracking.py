"""Tests for update_word_tracking.py logic using temporary files.

Covers:
- Deck word extraction: cloze removal and last-word logic
- Word-only vs (word,type) matching
- Lowercasing and homonym safety
- Status transitions: in_deck, pending, missing_audio, and preserving error
- Date update when status changes to in_deck
"""

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def write_deck(md_path: Path, rows: list[str]):
    header = (
        "| ID | Card Type | Word Type | Russian | German | Extra | Example_DE | Example_RU | Notes | Audio |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    md_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def write_tracking(md_path: Path, rows: list[str]):
    header = (
        "# Word Tracking\n\n"
        "| Word | Status | Audio | IPA | Word Type | Date Added | Notes |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    md_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def read_tracking_rows(md_path: Path) -> list[str]:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    # Return only table body rows
    body = []
    in_table = False
    for line in lines:
        if line.startswith("| Word | Status |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table:
            if not line or line == '---' or line.startswith('##'):
                break
            if line.startswith('|'):
                body.append(line)
    return body


def test_read_words_in_deck_extraction(tmp_paths, monkeypatch):
    deck, _ = tmp_paths

    # One cloze noun and one reverse with article; ensure last word extracted and lowercased
    rows = [
        "| 00000001 | Cloze | Noun | шаг | {{c1::der}} Schritt | — | — | — | — | de_schritt.mp3 |",
        "| 00000002 | Reverse RU→DE | Noun | вопрос | die Frage | — | — | — | — | de_frage.mp3 |",
    ]
    write_deck(deck, rows)

    uwt = importlib.import_module("flashcards.scripts.update_word_tracking")
    words_set, words_with_types = uwt.read_words_in_deck()

    assert 'schritt' in words_set
    assert 'frage' in words_set
    assert words_with_types['schritt'] == {'Noun'}
    assert 'Noun' in words_with_types['frage']


def test_update_tracking_statuses_and_dates(tmp_paths, monkeypatch):
    deck, tracking = tmp_paths

    # Deck contains Schritt (noun) and die Frage (noun)
    write_deck(
        deck,
        [
            "| 00000001 | Reverse RU→DE | Noun | шаг | der Schritt | — | — | — | — | de_schritt.mp3 |",
            "| 00000002 | Reverse RU→DE | Noun | вопрос | die Frage | — | — | — | — | de_frage.mp3 |",
        ],
    )

    # Tracking has three rows: Schritt with type, Frage without type (—), and Fehler in error state
    write_tracking(
        tracking,
        [
            "| Schritt | missing_audio | ❌ missing | — | Noun | — | — |",
            "| Frage | pending | ✅ de_old.mp3 | — | — | — | has audio but not in deck? |",
            "| Fehler | error | ❌ missing | — | Noun | — | should stay error |",
        ],
    )

    # Mock audio: pretend Frage has audio, Schritt has audio, Fehler no audio
    uwt = importlib.import_module("flashcards.scripts.update_word_tracking")
    monkeypatch.setattr(uwt, "get_audio_filename", lambda w: {
        'Schritt': 'de_schritt.mp3',
        'Frage': 'de_frage.mp3',
    }.get(w, None))

    # Run update
    uwt.update_tracking_file()

    rows = read_tracking_rows(tracking)
    # Collect row data for asserts
    def parse_row(r):
        parts = [p.strip() for p in r.split('|')]
        return {
            'word': parts[1],
            'status': parts[2],
            'audio': parts[3],
            'ipa': parts[4],
            'type': parts[5],
            'date': parts[6],
            'notes': parts[7],
        }

    data = {parse_row(r)['word']: parse_row(r) for r in rows}

    # Schritt is in deck -> status becomes in_deck and date is set (not '—')
    assert data['Schritt']['status'] == 'in_deck'
    assert data['Schritt']['date'] != '—'
    assert data['Schritt']['audio'].startswith('✅')

    # Frage has type placeholder '—' in tracking -> uses word-only match; it is in deck -> in_deck
    assert data['Frage']['status'] == 'in_deck'
    # Error stays error regardless of audio
    assert data['Fehler']['status'] == 'error'
