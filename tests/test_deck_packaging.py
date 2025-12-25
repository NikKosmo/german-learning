"""Tests for deck packaging round-trip (MD -> .apkg -> JSON)."""

import importlib
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TEST_CARDS = [
    {
        "id": "00000001",
        "card_type": "Reverse RU→DE",
        "word_type": "Noun",
        "russian": "dog",
        "german": "der Hund",
        "extra": "Plural: die Hunde",
        "example_de": "Der Hund bellt.",
        "example_ru": "The dog barks.",
        "notes": "—",
        "audio": "Hund.wav",
    },
    {
        "id": "00000002",
        "card_type": "Reverse DE→RU",
        "word_type": "Noun",
        "russian": "cat",
        "german": "die Katze",
        "extra": "Plural: die Katzen",
        "example_de": "Die Katze schläft.",
        "example_ru": "The cat sleeps.",
        "notes": "—",
        "audio": "—",
    },
    {
        "id": "00000003",
        "card_type": "Cloze",
        "word_type": "Noun",
        "russian": "car",
        "german": "{{c1::das}} Auto",
        "extra": "Plural: die Autos",
        "example_de": "Das Auto ist neu.",
        "example_ru": "The car is new.",
        "notes": "—",
        "audio": "—",
    },
    {
        "id": "00000004",
        "card_type": "Reverse RU→DE",
        "word_type": "Verb",
        "russian": "go",
        "german": "gehen",
        "extra": "ist gegangen",
        "example_de": "Ich gehe nach Hause.",
        "example_ru": "I go home.",
        "notes": "—",
        "audio": "gehen.mp3",
    },
    {
        "id": "00000005",
        "card_type": "Reverse DE→RU",
        "word_type": "Verb",
        "russian": "see",
        "german": "sehen",
        "extra": "hat gesehen",
        "example_de": "Ich sehe dich.",
        "example_ru": "I see you.",
        "notes": "—",
        "audio": "—",
    },
    {
        "id": "00000006",
        "card_type": "Reverse RU→DE",
        "word_type": "Adjective",
        "russian": "fast",
        "german": "schnell",
        "extra": "schneller am schnellsten",
        "example_de": "Das ist schnell.",
        "example_ru": "That is fast.",
        "notes": "—",
        "audio": "—",
    },
    {
        "id": "00000007",
        "card_type": "Reverse DE→RU",
        "word_type": "Adjective",
        "russian": "old",
        "german": "alt",
        "extra": "älter am ältesten",
        "example_de": "Das ist alt.",
        "example_ru": "That is old.",
        "notes": "—",
        "audio": "—",
    },
    {
        "id": "00000008",
        "card_type": "Reverse RU→DE",
        "word_type": "Preposition",
        "russian": "with",
        "german": "mit",
        "extra": "+ Dativ",
        "example_de": "Ich komme mit dir.",
        "example_ru": "I come with you.",
        "notes": "—",
        "audio": "—",
    },
    {
        "id": "00000009",
        "card_type": "Reverse DE→RU",
        "word_type": "Preposition",
        "russian": "without",
        "german": "ohne",
        "extra": "+ Akkusativ",
        "example_de": "Ohne dich.",
        "example_ru": "Without you.",
        "notes": "—",
        "audio": "—",
    },
    {
        "id": "00000010",
        "card_type": "Reverse RU→DE",
        "word_type": "Adverb",
        "russian": "yesterday",
        "german": "gestern",
        "extra": "—",
        "example_de": "Gestern war es kalt.",
        "example_ru": "Yesterday it was cold.",
        "notes": "—",
        "audio": "—",
    },
    {
        "id": "00000011",
        "card_type": "Reverse DE→RU",
        "word_type": "Adverb",
        "russian": "today",
        "german": "heute",
        "extra": "—",
        "example_de": "Heute ist Sonntag.",
        "example_ru": "Today is Sunday.",
        "notes": "—",
        "audio": "—",
    },
]


def write_deck(md_path: Path):
    header = (
        "| ID | Card Type | Word Type | Russian | German | Extra | Example_DE | Example_RU | Notes | Audio |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for card in TEST_CARDS:
        rows.append(
            "| {id} | {card_type} | {word_type} | {russian} | {german} | {extra} | "
            "{example_de} | {example_ru} | {notes} | {audio} |".format(**card)
        )
    md_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def index_cards_by_id(data: dict) -> dict:
    return {card["fields"]["ID"]: card for card in data["cards"]}


@pytest.fixture
def deck_roundtrip(tmp_path, monkeypatch):
    import paths

    flashcards_dir = tmp_path / "flashcards"
    scripts_dir = flashcards_dir / "scripts"
    audio_root = tmp_path / "audio"
    generated_dir = audio_root / "generated_audio"
    duolingo_dir = audio_root / "words_from_duolingo"

    scripts_dir.mkdir(parents=True)
    generated_dir.mkdir(parents=True)
    duolingo_dir.mkdir(parents=True)

    deck_md = flashcards_dir / "german_vocabulary_b1.md"
    write_deck(deck_md)

    # Audio mocking strategy: create dummy files and point audio paths to temp dirs.
    (generated_dir / "Hund.wav").write_bytes(b"RIFF----")
    (duolingo_dir / "gehen.mp3").write_bytes(b"ID3----")

    monkeypatch.setattr(paths, "FLASHCARDS_DIR", flashcards_dir, raising=False)
    monkeypatch.setattr(paths, "FLASHCARDS_SCRIPTS", scripts_dir, raising=False)
    monkeypatch.setattr(paths, "AUDIO_GENERATED", generated_dir, raising=False)
    monkeypatch.setattr(paths, "AUDIO_DUOLINGO", duolingo_dir, raising=False)
    monkeypatch.setattr(paths, "DECK_FILE", deck_md, raising=False)

    gen_mod = importlib.reload(importlib.import_module("flashcards.scripts.generate_deck_from_md"))
    gen_mod.logger.log_file = scripts_dir / "deck_generation_test.log"
    gen_mod.main()

    apkg_path = gen_mod.OUTPUT_FILE

    unpack_mod = importlib.reload(importlib.import_module("flashcards.scripts.unpack_deck"))
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    output_file = temp_dir / "deck_data.json"
    monkeypatch.setattr(unpack_mod, "TEMP_DIR", temp_dir, raising=False)
    monkeypatch.setattr(unpack_mod, "OUTPUT_FILE", output_file, raising=False)
    monkeypatch.setattr(sys, "argv", ["unpack_deck.py", str(apkg_path)])
    unpack_mod.main()

    data = json.loads(output_file.read_text(encoding="utf-8"))
    return {
        "data": data,
        "cards_by_id": index_cards_by_id(data),
    }


def test_round_trip_integrity(deck_roundtrip):
    data = deck_roundtrip["data"]
    cards_by_id = deck_roundtrip["cards_by_id"]

    assert data["total_cards"] == len(TEST_CARDS)
    assert set(cards_by_id.keys()) == {card["id"] for card in TEST_CARDS}

    verb_card = cards_by_id["00000004"]
    assert verb_card["fields"]["Infinitive"] == "gehen"
    assert verb_card["fields"]["Perfekt"] == "ist gegangen"
    assert verb_card["fields"]["Example_DE"] == "Ich gehe nach Hause."


def test_model_coverage(deck_roundtrip):
    data = deck_roundtrip["data"]
    model_names = {card["model_name"] for card in data["cards"]}

    assert model_names == {
        "German Noun (RU→DE)",
        "German Noun (DE→RU)",
        "German Noun Gender Cloze",
        "German Verb (RU→DE)",
        "German Verb (DE→RU)",
        "German Adjective (RU→DE)",
        "German Adjective (DE→RU)",
        "German Preposition (RU→DE)",
        "German Preposition (DE→RU)",
        "German Adverb (RU→DE)",
        "German Adverb (DE→RU)",
    }


def test_audio_handling(deck_roundtrip):
    cards_by_id = deck_roundtrip["cards_by_id"]

    assert cards_by_id["00000001"]["fields"]["Audio"] == "[sound:de_Hund.wav]"
    assert cards_by_id["00000004"]["fields"]["Audio"] == "[sound:de_gehen.mp3]"
    assert cards_by_id["00000002"]["fields"]["Audio"] == ""


def test_field_transformations(deck_roundtrip):
    cards_by_id = deck_roundtrip["cards_by_id"]

    noun_card = cards_by_id["00000001"]
    assert noun_card["fields"]["Article"] == "der"
    assert noun_card["fields"]["Noun"] == "Hund"
    assert noun_card["fields"]["Gender"] == "m"

    cloze_card = cards_by_id["00000003"]
    assert cloze_card["fields"]["Cloze_German"] == "{{c1::das}} Auto"

    prep_card = cards_by_id["00000008"]
    assert prep_card["fields"]["Preposition"] == "mit"
    assert prep_card["fields"]["Case"] == "+ Dativ"
