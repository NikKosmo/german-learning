"""
Tests for flashcards/scripts/word_types.py

Focus: WordType enum is the single source of truth. 100% coverage target for
this module's public API as required in temp/test_requirements.md.
"""

import importlib
import sys
from pathlib import Path
import pytest


# Ensure project root on sys.path for imports like flashcards.scripts.word_types
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


mod = importlib.import_module("flashcards.scripts.word_types")
WordType = mod.WordType
get_model_category = mod.get_model_category


def test_enum_has_expected_members_and_exact_values():
    """Enum contains exactly the expected values with exact case-sensitive strings."""
    expected = {
        "Noun",
        "Verb",
        "Adjective",
        "Adverb",
        "Preposition",
        "Conjunction",
        "Article",
        "Pronoun",
        "Particle",
        "Possessive",
        "Question Word",
        # compound
        "Adjective/Adverb",
        "Adverb/Particle",
    }

    values = {wt.value for wt in WordType}
    assert values == expected, "WordType enum values must match the expected set exactly"

    # No duplicates by definition; double-check defensively
    assert len(values) == len(list(WordType)), "Enum must not contain duplicate values"


def test_compound_types_are_alphabetically_ordered():
    """Compound enum values must be in alphabetical order as per implementation note."""
    compounds = [v for v in WordType.all_values() if "/" in v]
    assert compounds, "There should be at least one compound type"
    for c in compounds:
        parts = c.split("/")
        assert parts == sorted(parts), f"Compound type '{c}' must be alphabetically ordered"


@pytest.mark.parametrize(
    "valid",
    [
        *WordType.all_values(),
        "—",  # placeholder allowed
        "",   # empty allowed
        None,  # None treated as empty
    ],
)
def test_validate_strict_accepts_valid_inputs(valid):
    """validate_strict must accept all enum values, placeholder, and empty/None without raising."""
    # Should not raise
    mod.WordType.validate_strict(valid)


@pytest.mark.parametrize(
    "bad, expected_snippet",
    [
        ("noun", "Case mismatch!"),  # wrong capitalization
        (" Noun", "Extra whitespace"),  # leading space
        ("Noun ", "Extra whitespace"),  # trailing space
        ("Modal Verb", "Must be one of:"),  # outdated / unsupported type
        ("Noun (m)", "Must be one of:"),  # outdated format
    ],
)
def test_validate_strict_rejects_invalid_inputs_with_helpful_message(bad, expected_snippet):
    with pytest.raises(ValueError) as ei:
        WordType.validate_strict(bad, context="(unit-test)")
    msg = str(ei.value)
    assert expected_snippet in msg
    # Always includes the original bad value for clarity
    assert bad in msg


def test_is_noun_and_is_verb_exact_match():
    assert WordType.is_noun(WordType.NOUN.value)
    assert not WordType.is_noun(WordType.VERB.value)
    assert WordType.is_verb(WordType.VERB.value)
    assert not WordType.is_verb(WordType.NOUN.value)


def test_is_adjective_and_is_adverb_include_compounds():
    assert WordType.is_adjective(WordType.ADJECTIVE.value)
    assert WordType.is_adjective(WordType.ADJECTIVE_ADVERB.value)
    assert not WordType.is_adjective(WordType.ADVERB.value)

    assert WordType.is_adverb(WordType.ADVERB.value)
    assert WordType.is_adverb(WordType.ADJECTIVE_ADVERB.value)
    assert WordType.is_adverb(WordType.ADVERB_PARTICLE.value)
    assert not WordType.is_adverb(WordType.ADJECTIVE.value)


def test_is_preposition_article_groups_and_pronoun_groups():
    assert WordType.is_preposition(WordType.PREPOSITION.value)
    assert not WordType.is_preposition(WordType.ADVERB.value)

    # Article/Conjunction/Particle grouped as "basic"
    assert WordType.is_article_conjunction_particle(WordType.ARTICLE.value)
    assert WordType.is_article_conjunction_particle(WordType.CONJUNCTION.value)
    assert WordType.is_article_conjunction_particle(WordType.PARTICLE.value)
    assert not WordType.is_article_conjunction_particle(WordType.NOUN.value)

    # Pronoun/Possessive/Question Word grouped as "pronoun"
    assert WordType.is_pronoun_possessive_question(WordType.PRONOUN.value)
    assert WordType.is_pronoun_possessive_question(WordType.POSSESSIVE.value)
    assert WordType.is_pronoun_possessive_question(WordType.QUESTION_WORD.value)
    assert not WordType.is_pronoun_possessive_question(WordType.ADJECTIVE.value)


def test_get_primary_type_and_contains_type_behavior():
    assert WordType.get_primary_type("—") is None
    assert WordType.get_primary_type("") is None
    assert WordType.get_primary_type(WordType.ADJECTIVE.value) == "Adjective"
    assert WordType.get_primary_type(WordType.ADJECTIVE_ADVERB.value) == "Adjective"

    assert WordType.contains_type(WordType.ADJECTIVE_ADVERB.value, WordType.ADJECTIVE)
    assert WordType.contains_type(WordType.ADJECTIVE_ADVERB.value, WordType.ADVERB)
    assert not WordType.contains_type(WordType.ADJECTIVE_ADVERB.value, WordType.NOUN)


@pytest.mark.parametrize(
    "wt, expected",
    [
        (WordType.NOUN.value, "noun"),
        (WordType.VERB.value, "verb"),
        (WordType.ADJECTIVE.value, "adjective"),
        (WordType.ADJECTIVE_ADVERB.value, "adjective"),
        (WordType.ADVERB.value, "adverb"),
        (WordType.ADVERB_PARTICLE.value, "adverb"),
        (WordType.PREPOSITION.value, "preposition"),
        (WordType.ARTICLE.value, "basic"),
        (WordType.CONJUNCTION.value, "basic"),
        (WordType.PARTICLE.value, "basic"),
        (WordType.PRONOUN.value, "pronoun"),
        (WordType.POSSESSIVE.value, "pronoun"),
        (WordType.QUESTION_WORD.value, "pronoun"),
    ],
)
def test_get_model_category_mapping(wt, expected):
    assert get_model_category(wt) == expected


def test_get_model_category_rejects_invalid_input():
    with pytest.raises(ValueError):
        get_model_category("noun")  # wrong case
