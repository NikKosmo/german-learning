"""Tests for insert_cards.py core helpers.

We avoid running main() and only test pure functions using tmp paths.
"""

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_validate_json_structure_happy_and_error_cases():
    mod = importlib.import_module("flashcards.scripts.insert_cards")
    good = {
        "cards": [
            {
                "card_type": "Reverse",
                "word_type": "Noun",
                "russian": "шаг",
                "german": "der Schritt",
                "extra": "Plural: die Schritte",
                "example_de": "Ich mache einen Schritt.",
                "example_ru": "Я делаю шаг.",
                "notes": "—",
                "audio": "de_schritt.mp3",
            }
        ]
    }
    ok, msg = mod.validate_json_structure(good)
    assert ok, msg

    # Root must be object
    ok, msg = mod.validate_json_structure([good])
    assert not ok and "Root" in msg
    # Missing cards
    ok, msg = mod.validate_json_structure({})
    assert not ok and "Missing 'cards'" in msg
    # cards must be list
    ok, msg = mod.validate_json_structure({"cards": {}})
    assert not ok and "must be an array" in msg
    # empty list
    ok, msg = mod.validate_json_structure({"cards": []})
    assert not ok and "array is empty" in msg
    # missing field
    bad_card = {"card_type": "Reverse"}
    ok, msg = mod.validate_json_structure({"cards": [bad_card]})
    assert not ok and "missing required field" in msg


def test_expand_reverse_card_and_markdown_row(monkeypatch):
    mod = importlib.import_module("flashcards.scripts.insert_cards")

    card = {
        "card_type": "Reverse",
        "word_type": "Noun",
        "russian": "шаг",
        "german": "der Schritt",
        "extra": "Plural: die Schritte",
        "example_de": "Ich mache einen Schritt.",
        "example_ru": "Я делаю шаг.",
        "notes": "—",
        "audio": "de_schritt.mp3",
    }

    expanded = mod.expand_reverse_card(card)
    assert len(expanded) == 2
    types = {c["card_type"] for c in expanded}
    assert types == {"Reverse RU→DE", "Reverse DE→RU"}

    # Ensure markdown row format; freeze generate_card_id for predictability
    monkeypatch.setattr(mod, "generate_card_id", lambda g, ct: "deadbeef")
    row = mod.card_to_markdown_row(expanded[0])
    assert row.startswith("| deadbeef | ")
    assert "| Noun |" in row
    assert row.endswith("| de_schritt.mp3 |")


def test_update_deck_metadata_counts_and_updates(tmp_paths, monkeypatch):
    deck, _ = tmp_paths
    mod = importlib.import_module("flashcards.scripts.insert_cards")

    # Prepare deck with metadata headers and two existing card rows
    content = (
        "# Deck\n\n"
        "- Total cards: 0\n"
        "- Generated: 2000-01-01\n\n"
        "| ID | Card Type | Word Type | Russian | German | Extra | Example_DE | Example_RU | Notes | Audio |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        "| 11111111 | Reverse RU→DE | Noun | шаг | der Schritt | — | — | — | — | de_schritt.mp3 |\n"
        "| 22222222 | Reverse DE→RU | Verb | идти | gehen | — | — | — | — | de_gehen.mp3 |\n"
    )
    deck.write_text(content, encoding="utf-8")

    # Run update_deck_metadata simulating that we added 1 new card this session
    mod.update_deck_metadata(1)

    updated = deck.read_text(encoding="utf-8")
    # Total cards should match actual table rows (2)
    assert "- Total cards: 2" in updated
    # Generated should be updated to today (YYYY-MM-DD) pattern
    import re
    assert re.search(r"- Generated: \d{4}-\d{2}-\d{2}", updated)
