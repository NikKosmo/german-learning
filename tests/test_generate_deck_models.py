"""Tests for model selection logic in generate_deck_from_md.py

We focus on get_model_key which now relies on WordType helpers and
get_model_category. genanki is mocked via conftest.fake_genanki fixture.
"""

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_get_model_key_basic_mappings(fake_genanki):
    mod = importlib.import_module("flashcards.scripts.generate_deck_from_md")

    f = mod.get_model_key

    # Directional mappings for Reverse cards
    assert f('Reverse RU→DE', 'Noun') == 'noun_ru_de'
    assert f('Reverse DE→RU', 'Noun') == 'noun_de_ru'
    assert f('Reverse RU→DE', 'Verb') == 'verb_ru_de'
    assert f('Reverse DE→RU', 'Verb') == 'verb_de_ru'
    assert f('Reverse RU→DE', 'Adjective') == 'adj_ru_de'
    assert f('Reverse DE→RU', 'Adjective/Adverb') == 'adj_de_ru'  # compounds resolve to adjective
    assert f('Reverse RU→DE', 'Preposition') == 'prep_ru_de'

    # Adverb/basic/pronoun categories map to adv_*
    assert f('Reverse RU→DE', 'Adverb') == 'adv_ru_de'
    assert f('Reverse DE→RU', 'Article') == 'adv_de_ru'
    assert f('Reverse RU→DE', 'Conjunction') == 'adv_ru_de'
    assert f('Reverse DE→RU', 'Particle') == 'adv_de_ru'
    assert f('Reverse RU→DE', 'Pronoun') == 'adv_ru_de'
    assert f('Reverse DE→RU', 'Possessive') == 'adv_de_ru'
    assert f('Reverse RU→DE', 'Question Word') == 'adv_ru_de'


def test_get_model_key_cloze_and_invalid(fake_genanki):
    mod = importlib.import_module("flashcards.scripts.generate_deck_from_md")
    f = mod.get_model_key

    # Cloze is always noun_cloze regardless of type
    assert f('Cloze', 'Noun') == 'noun_cloze'
    assert f('Cloze', 'Adjective/Adverb') == 'noun_cloze'

    # Invalid word type raises ValueError via WordType.validate_strict
    import pytest
    with pytest.raises(ValueError):
        f('Reverse RU→DE', 'noun')  # wrong case

    # Unknown direction yields None
    assert f('Something Else', 'Noun') is None
