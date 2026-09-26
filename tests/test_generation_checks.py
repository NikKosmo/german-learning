"""Deterministic checks that guard new generated cards before LLM validation."""

import importlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

cg = importlib.import_module("flashcards.scripts.card_generator")


def _card(**changes):
    card = {
        "card_type": "Reverse",
        "word_type": "Verb",
        "russian": "идти",
        "german": "gehen",
        "extra": "ist gegangen",
        "example_de": "Ich gehe nach Hause.",
        "example_ru": "Я иду домой.",
        "notes": "Неправильный глагол.",
    }
    card.update(changes)
    return card


def _noun_cards(word="Tisch"):
    common = {
        "word_type": "Noun",
        "russian": "стол",
        "extra": "die Tische",
        "example_de": "Der Tisch ist neu.",
        "example_ru": "Стол новый.",
        "notes": "Мужской род.",
    }
    return [
        {**common, "card_type": "Reverse", "german": f"der {word}"},
        {**common, "card_type": "Cloze", "german": f"{{{{c1::der}}}} {word}"},
    ]


def test_prompt_has_all_deterministic_rules_and_no_audio(monkeypatch):
    schema_path = cg.PENDING_CARDS_SCHEMA
    assert schema_path is not None
    source = Path(schema_path).read_text(encoding="utf-8")
    assert '"audio"' not in source
    prompts: list[str] = []
    monkeypatch.setattr(cg, "HAS_SDK", False)
    monkeypatch.setattr(
        cg,
        "run_claude",
        lambda prompt, **_kwargs: (
            prompts.append(prompt) or json.dumps({"cards": [_card()]}, ensure_ascii=False)
        ),
    )
    cg.generate_card_data({"word": "gehen", "word_type": "Verb"})
    prompt = prompts[0]
    for phrase in (
        "Cloze markup {{...}}",
        '"die <Plural>" or "— (kein Plural)"',
        '"— (keine Steigerung)"',
        '"+ Akkusativ / + Dativ"',
        '"hat geschwommen / ist geschwommen"',
        'All remaining types except Adjective and Adjective/Adverb: "—"',
        "Adjective and Adjective/Adverb",
        'must end\n   with the tracking word "gehen"',
    ):
        assert phrase in prompt
    assert "Audio file:" not in prompt


def test_schema_rejects_model_audio_field():
    schema_path = cg.PENDING_CARDS_SCHEMA
    assert schema_path is not None
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"cards": [{**_card(), "audio": "gehen.mp3"}]}, schema)


def test_check_enforces_shape_language_forms_and_table_safety(monkeypatch):
    monkeypatch.setattr(cg, "lookup_noun_inflection", lambda _word: None)
    cards = _noun_cards("Mist")
    cards[0]["german"] = "Der Tisch ist groß"
    cards[1]["example_de"] = "{{c1::Der}} Tisch ist neu."
    cards[0]["russian"] = "стол, table"
    cards[0]["notes"] = "x" * 201
    cards[0]["extra"] = "Plural: Tische | falsch"
    complaints = cg.check_generated_cards({"word": "Tisch", "word_type": "Noun"}, cards)
    assert any("noun Reverse" in complaint for complaint in complaints)
    assert any("cloze markup" in complaint for complaint in complaints)
    assert any("Cyrillic without Latin" in complaint for complaint in complaints)
    assert any("200 characters" in complaint for complaint in complaints)
    assert any("table-breaking" in complaint for complaint in complaints)


@pytest.mark.parametrize(
    "card",
    [
        _noun_cards("Mist")[0] | {"extra": "die —"},
        _noun_cards("Mist")[0] | {"extra": "die — (selten)"},
        _card(word_type="Adjective", extra="— — am besten"),
        _card(word_type="Adjective", extra="besser — am —"),
        _card(extra="ist —"),
        _card(extra="hat — / ist —"),
        _card(extra="hat gegangen / ist —"),
    ],
)
def test_check_rejects_placeholder_forms(monkeypatch, card):
    monkeypatch.setattr(cg, "lookup_noun_inflection", lambda _word: None)
    word_info = (
        {"word": "Mist", "word_type": "Noun"}
        if card["word_type"] == "Noun"
        else {
            "word": "gehen",
            "word_type": card["word_type"],
        }
    )
    complaints = cg.check_generated_cards(word_info, [card])
    assert any("wrong format" in complaint and "expected" in complaint for complaint in complaints)


def test_check_compares_word_type_and_non_noun_headword(monkeypatch):
    monkeypatch.setattr(cg, "lookup_noun_inflection", lambda _word: None)
    card = _card(word_type="Adverb", german="gehen jetzt", extra="—")
    complaints = cg.check_generated_cards({"word": "gehen", "word_type": "Verb"}, [card])
    assert any("word_type" in complaint for complaint in complaints)
    assert any("does not end" in complaint for complaint in complaints)


def test_non_noun_headword_is_required_and_case_insensitive(monkeypatch):
    monkeypatch.setattr(cg, "lookup_noun_inflection", lambda _word: None)
    assert any(
        "does not end" in complaint
        for complaint in cg.check_generated_cards(
            {"word": "gehen", "word_type": "Verb"}, [_card(german="")]
        )
    )
    assert (
        cg.check_generated_cards(
            {"word": "tja", "word_type": "Particle"},
            [_card(word_type="Particle", german="Tja", extra="—")],
        )
        == []
    )


def test_check_recognizes_unicode_latin_letters(monkeypatch):
    monkeypatch.setattr(cg, "lookup_noun_inflection", lambda _word: None)
    complaints = cg.check_generated_cards(
        {"word": "gehen", "word_type": "Verb"},
        [_card(russian="ученик é", example_ru="Это éé.")],
    )
    assert any("russian must" in complaint for complaint in complaints)
    assert any("example_ru" in complaint for complaint in complaints)


def test_single_wiktionary_plural_overrides_model_value(monkeypatch):
    monkeypatch.setattr(
        cg, "lookup_noun_inflection", lambda _word: [cg.NounInflectionEntry("m", ("—",))]
    )
    cards = _noun_cards("Mist")
    cards[0]["extra"] = "Plural: Miste"
    assert cg.check_generated_cards({"word": "Mist", "word_type": "Noun"}, cards) == []
    assert {card["extra"] for card in cards} == {"— (kein Plural)"}


def test_multiple_wiktionary_plurals_and_genus_are_checked(monkeypatch):
    monkeypatch.setattr(
        cg,
        "lookup_noun_inflection",
        lambda _word: [cg.NounInflectionEntry("f", ("Lüfte", "Lüften"))],
    )
    cards = _noun_cards("Luft")
    cards[0]["german"] = "die Luft"
    cards[1]["german"] = "{{c1::die}} Luft"
    cards[0]["extra"] = cards[1]["extra"] = "die Lufts"
    complaints = cg.check_generated_cards({"word": "Luft", "word_type": "Noun"}, cards)
    assert any("plural" in complaint for complaint in complaints)
    assert any("die Lüfte" in complaint for complaint in complaints)

    wrong_gender = _noun_cards("Luft")
    complaints = cg.check_generated_cards({"word": "Luft", "word_type": "Noun"}, wrong_gender)
    assert any("Wiktionary gives Luft as die (f)" in complaint for complaint in complaints)


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("Mist", [cg.NounInflectionEntry("m", ("—",))]),
        ("Atem", [cg.NounInflectionEntry("m", ("—",))]),
        (
            "Luft",
            [cg.NounInflectionEntry("f", ("Lüfte",)), cg.NounInflectionEntry("m", ("Lüfte",))],
        ),
        ("Tisch", [cg.NounInflectionEntry("m", ("Tische",))]),
        ("Leute", [cg.NounInflectionEntry("0", ("Leute",))]),
        (
            "Magnet",
            [cg.NounInflectionEntry("m", ("Magnete",)), cg.NounInflectionEntry("m", ("Magneten",))],
        ),
        (
            "Band",
            [
                cg.NounInflectionEntry("n", ("Bänder", "Bande")),
                cg.NounInflectionEntry("m", ("Bände",)),
                cg.NounInflectionEntry("f", ("Bands",)),
                cg.NounInflectionEntry("n", ("—",)),
            ],
        ),
        (
            "Kiefer",
            [
                cg.NounInflectionEntry("f", ("Kiefern",)),
                cg.NounInflectionEntry("m", ("Kiefer",)),
                cg.NounInflectionEntry("n", ("Kiefer",)),
            ],
        ),
        ("Tafel", [cg.NounInflectionEntry("f", ("Tafeln",))]),
        ("Eltern", [cg.NounInflectionEntry("0", ("Eltern",))]),
    ],
)
def test_noun_lookup_uses_saved_real_parsetree_fixtures(monkeypatch, word, expected):
    payload = json.loads(
        (PROJECT_ROOT / "tests/fixtures" / f"{word}.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(
        cg.add_words,
        "fetch_parse_payload",
        lambda *_args: payload,
    )
    assert cg.lookup_noun_inflection(word) == expected


def test_plural_only_noun_accepts_die_plural_from_real_page(monkeypatch):
    payload = json.loads((PROJECT_ROOT / "tests/fixtures/Leute.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cg.add_words, "fetch_parse_payload", lambda *_args: payload)
    cards = _noun_cards("Leute")
    cards[0]["german"] = "die Leute"
    cards[1]["german"] = "{{c1::die}} Leute"
    cards[0]["extra"] = cards[1]["extra"] = "die Leute"
    assert cg.check_generated_cards({"word": "Leute", "word_type": "Noun"}, cards) == []


def test_check_failure_retries_without_calling_validator(monkeypatch, tmp_path):
    attempts: list[str | None] = []
    validations: list[object] = []
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    monkeypatch.setattr(
        cg,
        "generate_card_data",
        lambda _info, retry_feedback=None: attempts.append(retry_feedback) or [_card()],
    )
    monkeypatch.setattr(cg, "check_generated_cards", lambda *_args: ["bad fields"])
    monkeypatch.setattr(cg, "validate_card_data", lambda *_args: validations.append(1))
    outcome = cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})
    assert outcome.failure_kind == cg.FAILURE_GENERATION_ERROR
    assert attempts == [None, "bad fields"]
    assert validations == []


def test_only_malformed_model_output_value_error_retries(monkeypatch, tmp_path):
    attempts: list[str | None] = []

    def generate(_info, retry_feedback=None):
        attempts.append(retry_feedback)
        if len(attempts) == 1:
            raise cg.MalformedModelOutputError("failed schema validation")
        return [_card()]

    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    monkeypatch.setattr(cg, "generate_card_data", generate)
    monkeypatch.setattr(cg, "check_generated_cards", lambda *_args: [])
    monkeypatch.setattr(cg, "validate_card_data", lambda *_args: (True, "", True))
    outcome = cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})
    assert outcome.cards[0]["audio"] == "Gehen.mp3"
    assert attempts[0] is None
    assert "failed schema validation" in (attempts[1] or "")


def test_non_model_value_error_does_not_regenerate(monkeypatch, tmp_path):
    attempts: list[object] = []
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    monkeypatch.setattr(
        cg,
        "generate_card_data",
        lambda *_args, **_kwargs: (
            attempts.append(1) or (_ for _ in ()).throw(ValueError("invalid configuration"))
        ),
    )
    outcome = cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})
    assert outcome.failure_kind == cg.FAILURE_GENERATION_ERROR
    assert attempts == [1]


def test_empty_generation_is_retried_as_a_generation_check_failure(monkeypatch, tmp_path):
    attempts: list[str | None] = []
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    monkeypatch.setattr(
        cg,
        "generate_card_data",
        lambda _info, retry_feedback=None: attempts.append(retry_feedback) or [],
    )
    outcome = cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})
    assert outcome.failure_kind == cg.FAILURE_GENERATION_ERROR
    assert attempts == [None, "no cards generated"]


def test_validator_reject_after_check_failure_stays_pending(monkeypatch, tmp_path):
    attempts: list[str | None] = []
    quarantines: list[object] = []
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    monkeypatch.setattr(
        cg,
        "generate_card_data",
        lambda _info, retry_feedback=None: attempts.append(retry_feedback) or [_card()],
    )
    monkeypatch.setattr(
        cg,
        "check_generated_cards",
        lambda *_args: ["bad form"] if len(attempts) == 1 else [],
    )
    monkeypatch.setattr(cg, "validate_card_data", lambda *_args: (False, "translation", True))
    monkeypatch.setattr(cg, "quarantine_word", lambda *_args: quarantines.append(1) or True)
    outcome = cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})
    assert outcome.failure_kind == cg.FAILURE_GENERATION_ERROR
    assert quarantines == []


def test_wiktionary_or_generation_exception_does_not_regenerate(monkeypatch, tmp_path):
    attempts: list[object] = []
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    monkeypatch.setattr(
        cg,
        "generate_card_data",
        lambda *_args, **_kwargs: (
            attempts.append(1) or (_ for _ in ()).throw(RuntimeError("timeout"))
        ),
    )
    outcome = cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})
    assert outcome.failure_kind == cg.FAILURE_GENERATION_ERROR
    assert attempts == [1]

    attempts.clear()
    monkeypatch.setattr(
        cg, "generate_card_data", lambda *_args, **_kwargs: attempts.append(1) or [_card()]
    )
    monkeypatch.setattr(
        cg,
        "check_generated_cards",
        lambda *_args: (_ for _ in ()).throw(cg.NounLookupError("Wiktionary unreachable: timeout")),
    )
    outcome = cg.process_word({"word": "Mist", "word_type": "Noun", "audio": "Mist.mp3"})
    assert outcome.failure_kind == cg.FAILURE_GENERATION_ERROR
    assert attempts == [1]


def test_second_check_failure_is_logged(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    monkeypatch.setattr(cg, "generate_card_data", lambda *_args, **_kwargs: [_card()])
    complaints = iter([["first reason"], ["second reason"]])
    monkeypatch.setattr(cg, "check_generated_cards", lambda *_args: next(complaints))
    cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})
    output = capsys.readouterr().out
    assert "Generation check failed for 'gehen' on retry: second reason" in output


def test_missing_card_field_is_a_generation_check_failure(monkeypatch):
    monkeypatch.setattr(cg, "lookup_noun_inflection", lambda _word: None)
    incomplete = _card()
    del incomplete["notes"]
    complaints = cg.check_generated_cards({"word": "gehen", "word_type": "Verb"}, [incomplete])
    assert any("missing required fields: notes" in complaint for complaint in complaints)


def test_magnet_cloze_must_match_reverse_headword(monkeypatch):
    monkeypatch.setattr(cg, "lookup_noun_inflection", lambda _word: None)
    cards = _noun_cards("Magnet")
    cards[1]["german"] = "{{c1::der}} Magnet zieht Eisen an."
    complaints = cg.check_generated_cards({"word": "Magnet", "word_type": "Noun"}, cards)
    assert any("noun Cloze german" in complaint for complaint in complaints)


def test_successful_cards_get_tracking_audio_after_validation(monkeypatch):
    monkeypatch.setattr(cg, "check_generated_cards", lambda *_args: [])
    monkeypatch.setattr(cg, "generate_card_data", lambda *_args, **_kwargs: [_card()])
    monkeypatch.setattr(cg, "validate_card_data", lambda *_args: (True, "", True))
    outcome = cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})
    assert outcome.cards[0]["audio"] == "Gehen.mp3"


def test_tracking_audio_reaches_markdown_and_built_package(monkeypatch, tmp_path):
    import paths

    flashcards_dir = tmp_path / "flashcards"
    scripts_dir = flashcards_dir / "scripts"
    audio_dir = tmp_path / "audio"
    scripts_dir.mkdir(parents=True)
    audio_dir.mkdir()
    (audio_dir / "Hund.mp3").write_bytes(b"ID3")
    deck = flashcards_dir / "german_vocabulary_b1.md"
    deck.write_text(
        "- Total cards: 0\n- Words: 0\n- Generated: 2000-01-01\n\n"
        "| ID | Card Type | Word Type | Russian | German | Extra | Example_DE | "
        "Example_RU | Notes | Audio |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "FLASHCARDS_DIR", flashcards_dir, raising=False)
    monkeypatch.setattr(paths, "FLASHCARDS_SCRIPTS", scripts_dir, raising=False)
    monkeypatch.setattr(paths, "AUDIO_DUOLINGO", audio_dir, raising=False)
    monkeypatch.setattr(paths, "AUDIO_GENERATED", audio_dir, raising=False)
    monkeypatch.setattr(paths, "DECK_FILE", deck, raising=False)
    monkeypatch.setattr(cg, "generate_card_data", lambda *_args, **_kwargs: _noun_cards("Hund"))
    monkeypatch.setattr(cg, "check_generated_cards", lambda *_args: [])
    monkeypatch.setattr(cg, "validate_card_data", lambda *_args: (True, "", True))
    cards = cg.process_word({"word": "Hund", "word_type": "Noun", "audio": "Hund.mp3"}).cards
    insert = importlib.reload(importlib.import_module("flashcards.scripts.insert_cards"))
    insert.insert_cards_into_deck(cards)
    assert "| Hund.mp3 |" in deck.read_text(encoding="utf-8")

    generator = importlib.reload(
        importlib.import_module("flashcards.scripts.generate_deck_from_md")
    )
    generator.logger.log_file = scripts_dir / "generation.log"
    generator.main()
    unpack = importlib.reload(importlib.import_module("flashcards.scripts.unpack_deck"))
    output_dir = tmp_path / "unpacked"
    output_dir.mkdir()
    monkeypatch.setattr(unpack, "TEMP_DIR", output_dir, raising=False)
    monkeypatch.setattr(unpack, "OUTPUT_FILE", output_dir / "deck.json", raising=False)
    monkeypatch.setattr(sys, "argv", ["unpack_deck.py", str(generator.OUTPUT_FILE)])
    unpack.main()
    package = json.loads((output_dir / "deck.json").read_text(encoding="utf-8"))
    assert any("[sound:de_Hund.mp3]" in card["fields"].values() for card in package["cards"])


def test_validator_payload_excludes_generator_control_fields(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(
        cg,
        "_ask_validators",
        lambda prompt: (prompts.append(prompt) or "Codex", (True, []), []),
    )
    cg.validate_card_data("gehen", [{**_card(), "audio": "Gehen.mp3"}])
    assert '"word_type"' not in prompts[0]
    assert '"card_type"' not in prompts[0]
    assert '"audio"' not in prompts[0]
    assert '"field": "german"' in prompts[0]
    assert "field must be one of the fields actually sent above" in prompts[0]


def test_validator_prompt_offers_only_fields_sent(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(
        cg,
        "_ask_validators",
        lambda prompt: (prompts.append(prompt) or "Codex", (True, []), []),
    )

    cg.validate_card_data("gehen", [_card()], wiktionary_extra_authoritative=True)

    assert '"extra"' not in prompts[0]
    allowed_fields_line = next(
        line
        for line in prompts[0].splitlines()
        if line
        == "russian, german, example_de, example_ru, notes, general. Use general only for an issue that does not belong to one field."
    )
    allowed_fields = allowed_fields_line.split(". Use general", 1)[0].split(", ")
    assert allowed_fields.count("general") == 1


def _blut_cards():
    cards = _noun_cards("Blut")
    cards[0]["german"] = "das Blut"
    cards[1]["german"] = "{{c1::das}} Blut"
    cards[0]["extra"] = cards[1]["extra"] = "die Blüten"
    return cards


def test_real_blut_page_hides_its_sourced_plural_and_retains_other_feedback(monkeypatch, tmp_path):
    """The saved page drives both the sourced-plural pass and rejection path."""
    payload = json.loads((PROJECT_ROOT / "tests/fixtures/Blut.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cg.add_words, "fetch_parse_payload", lambda *_args: payload)
    assert cg.lookup_noun_inflection("Blut") == [cg.NounInflectionEntry("n", ("Blute",))]

    prompts: list[str] = []
    verdicts = tmp_path / "validator_verdicts.jsonl"
    monkeypatch.setattr(
        cg,
        "generate_card_data",
        lambda *_args, **_kwargs: _blut_cards(),
    )
    validator_verdicts = iter(
        [
            (False, [{"field": "extra", "problem": "plural should be Blüten"}]),
            (
                False,
                [
                    {"field": "extra", "problem": "plural should be Blüten"},
                    {"field": "russian", "problem": "неточно"},
                ],
            ),
            (
                False,
                [
                    {"field": "extra", "problem": "plural should be Blüten"},
                    {"field": "russian", "problem": "неточно"},
                ],
            ),
        ]
    )
    monkeypatch.setattr(
        cg,
        "_ask_validators",
        lambda prompt: (
            prompts.append(prompt) or "Codex",
            next(validator_verdicts),
            [],
        ),
    )
    parked: list[tuple[str, str, str]] = []
    monkeypatch.setattr(cg, "quarantine_word", lambda *args: parked.append(args) or True)
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed_words.txt")
    monkeypatch.setattr(cg, "VALIDATOR_VERDICTS_FILE", verdicts)

    admitted = cg.process_word({"word": "Blut", "word_type": "Noun", "audio": "Blut.mp3"})
    rejected = cg.process_word({"word": "Blut", "word_type": "Noun", "audio": "Blut.mp3"})

    assert admitted.cards[0]["audio"] == "Blut.mp3"
    assert {card["extra"] for card in admitted.cards} == {"die Blute"}
    assert rejected.cards == []
    assert rejected.quarantined is True
    assert parked == [("Blut", "Noun", "russian: неточно")]
    assert '"extra"' not in prompts[0]
    assert "russian, german, example_de, example_ru, notes, general." in prompts[0]
    records = [json.loads(line) for line in verdicts.read_text(encoding="utf-8").splitlines()]
    assert [(record["attempt"], record["valid"], record["issues"]) for record in records] == [
        (1, True, []),
        (1, False, [{"field": "russian", "problem": "неточно"}]),
        (2, False, [{"field": "russian", "problem": "неточно"}]),
    ]


def test_wiktionary_alternative_selected_by_the_model_is_authoritative(monkeypatch):
    cards = _noun_cards("Luft")
    cards[0]["german"] = "die Luft"
    cards[1]["german"] = "{{c1::die}} Luft"
    cards[0]["extra"] = cards[1]["extra"] = "die Lüften"
    monkeypatch.setattr(
        cg,
        "lookup_noun_inflection",
        lambda _word: [cg.NounInflectionEntry("f", ("Lüfte", "Lüften"))],
    )

    result = cg.check_generated_cards({"word": "Luft", "word_type": "Noun"}, cards)

    assert result == []
    assert result.wiktionary_extra_authoritative is True


def test_noun_without_a_wiktionary_table_keeps_extra_visible(monkeypatch):
    cards = _noun_cards("Blut")
    monkeypatch.setattr(cg, "lookup_noun_inflection", lambda _word: None)

    result = cg.check_generated_cards({"word": "Blut", "word_type": "Noun"}, cards)

    assert result.wiktionary_extra_authoritative is False


def test_retry_feedback_names_each_validator_issue_field(monkeypatch, tmp_path):
    feedback: list[str | None] = []
    monkeypatch.setattr(
        cg,
        "generate_card_data",
        lambda _info, retry_feedback=None: feedback.append(retry_feedback) or [_card()],
    )
    monkeypatch.setattr(
        cg,
        "_ask_validators",
        lambda _prompt: (
            "Codex",
            (
                False,
                [
                    {"field": "german", "problem": "wrong article"},
                    {"field": "example_ru", "problem": "inaccurate"},
                ],
            ),
            [],
        ),
    )
    monkeypatch.setattr(cg, "quarantine_word", lambda *_args: True)
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed_words.txt")
    monkeypatch.setattr(cg, "VALIDATOR_VERDICTS_FILE", tmp_path / "validator_verdicts.jsonl")

    cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})

    assert feedback == [None, "german: wrong article\nexample_ru: inaccurate"]


def test_every_validator_verdict_is_recorded_with_its_attempt(monkeypatch, tmp_path):
    replies = iter(
        [
            (False, [{"field": "russian", "problem": "translation is too broad"}]),
            (False, [{"field": "example_de", "problem": "sentence is unnatural"}]),
        ]
    )
    verdicts = tmp_path / "validator_verdicts.jsonl"
    monkeypatch.setattr(cg, "generate_card_data", lambda *_args, **_kwargs: [_card()])
    monkeypatch.setattr(cg, "_ask_validators", lambda _prompt: ("Codex", next(replies), []))
    monkeypatch.setattr(cg, "quarantine_word", lambda *_args: True)
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed_words.txt")
    monkeypatch.setattr(cg, "VALIDATOR_VERDICTS_FILE", verdicts)

    cg.process_word({"word": "gehen", "word_type": "Verb", "audio": "Gehen.mp3"})

    records = [json.loads(line) for line in verdicts.read_text(encoding="utf-8").splitlines()]
    assert [(record["attempt"], record["issues"][0]["field"]) for record in records] == [
        (1, "russian"),
        (2, "example_de"),
    ]


def test_existing_deck_has_no_g1e_violations():
    deck = (PROJECT_ROOT / "flashcards/german_vocabulary_b1.md").read_text(encoding="utf-8")
    rows = [line.split("|")[1:-1] for line in deck.splitlines() if line.startswith("| ")]
    rows = [row for row in rows if len(row) == 10 and row[0].strip() != "ID"]
    violations = []
    for row in rows:
        russian = row[3].strip()
        german = row[4].strip()
        example_de, example_ru, notes = (cell.strip() for cell in row[6:9])
        if not cg.re.search(r"[\u0400-\u052f]", russian) or cg._contains_latin(russian):
            violations.append(row[0])
        if cg._has_latin_run(example_ru):
            violations.append(row[0])
        if cg.re.search(r"[\u0400-\u052f]", german + example_de):
            violations.append(row[0])
        if not cg.re.search(r"[\u0400-\u052f]", notes):
            violations.append(row[0])
    assert violations == []


def test_insert_refuses_table_breaking_card():
    insert = importlib.import_module("flashcards.scripts.insert_cards")
    valid, message = insert.validate_json_structure({"cards": [{**_card(), "audio": "x|y.mp3"}]})
    assert valid is False
    assert "table-breaking" in message


def test_parked_word_is_drawn_once_after_cooldown_and_records_second_park(monkeypatch, tmp_path):
    import paths

    parked_on = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    tracking = tmp_path / "word_tracking.md"
    tracking.write_text(
        "| Word | Status | Audio | IPA | Word Type | Date Added | Notes |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| Spiel | error | ✅ Spiel.mp3 | — | Noun | — | {parked_on} validation failed: old |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "WORD_TRACKING_FILE", tracking, raising=False)
    pending = cg.get_pending_words()
    assert pending == [
        {
            "word": "Spiel",
            "status": "error",
            "audio": "Spiel.mp3",
            "word_type": "Noun",
            "parked_retry": True,
        }
    ]
    assert cg.quarantine_word("Spiel", "Noun", "still wrong") is True
    assert "validation failed (2): still wrong" in tracking.read_text(encoding="utf-8")
    assert cg.get_pending_words() == []


def test_metadata_counts_distinct_last_token_headwords(monkeypatch, tmp_path):
    import paths

    deck = tmp_path / "deck.md"
    deck.write_text(
        "- Total cards: 0\n- Words: 0\n- Generated: 2000-01-01\n\n"
        "| ID | Card Type | Word Type | Russian | German | Extra | Example_DE | "
        "Example_RU | Notes | Audio |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        "| 11111111 | Reverse RU→DE | Noun | стол | der Tisch | die Tische | — | — | — | — |\n"
        "| 22222222 | Cloze | Noun | стол | {{c1::der}} Tisch | die Tische | — | — | — | — |\n"
        "| 33333333 | Reverse RU→DE | Verb | идти | gehen | ist gegangen | — | — | — | — |\n"
        "| 44444444 | Reverse RU→DE | Noun | улица | die Straße | die Straßen | — | — | — | — |\n"
        "| 55555555 | Reverse RU→DE | Noun | улица | die STRASSE | die Straßen | — | — | — | — |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "DECK_FILE", deck, raising=False)
    insert = importlib.import_module("flashcards.scripts.insert_cards")
    insert.update_deck_metadata(0)
    assert "- Words: 4" in deck.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "row",
    [
        "| abcdef12 | Reverse RU→DE | Verb | идти | gehen | ist gegangen | "
        "Ich gehe. | Я иду. | Неправильный глагол. | missing.mp3 |",
        "| abcdef12 | Reverse RU→DE | Verb | идти | gehen | ist gegangen | "
        "Ich gehe.\n| Я иду. | Неправильный глагол. | — |",
        "| abcdef12 | Unknown | Verb | идти | gehen | — | "
        "Ich gehe. | Я иду. | Неправильный глагол. | — |",
        "| ABCDEF12 | Reverse RU→DE | Verb | идти | gehen | ist gegangen | "
        "Ich gehe. | Я иду. | Неправильный глагол. | — |",
    ],
    ids=["missing-audio", "newline-broken-row", "skipped-note", "uncounted-row"],
)
def test_build_refuses_bad_input_without_replacing_existing_package(
    monkeypatch, tmp_path, row, capsys
):
    import paths

    flashcards_dir = tmp_path / "flashcards"
    scripts_dir = flashcards_dir / "scripts"
    audio_dir = tmp_path / "audio"
    scripts_dir.mkdir(parents=True)
    audio_dir.mkdir()
    deck = flashcards_dir / "german_vocabulary_b1.md"
    deck.write_text(
        "| ID | Card Type | Word Type | Russian | German | Extra | Example_DE | "
        "Example_RU | Notes | Audio |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n" + row + "\n",
        encoding="utf-8",
    )
    package = flashcards_dir / "german_vocabulary_b1.apkg"
    package.write_bytes(b"previous package")
    monkeypatch.setattr(paths, "FLASHCARDS_DIR", flashcards_dir, raising=False)
    monkeypatch.setattr(paths, "FLASHCARDS_SCRIPTS", scripts_dir, raising=False)
    monkeypatch.setattr(paths, "DECK_FILE", deck, raising=False)
    monkeypatch.setattr(paths, "AUDIO_DUOLINGO", audio_dir, raising=False)
    monkeypatch.setattr(paths, "AUDIO_GENERATED", audio_dir, raising=False)
    generator = importlib.reload(
        importlib.import_module("flashcards.scripts.generate_deck_from_md")
    )
    generator.logger.log_file = scripts_dir / "generation.log"
    with pytest.raises(SystemExit):
        generator.main()
    assert package.read_bytes() == b"previous package"
    if "Ich gehe.\n" in row:
        assert "first unparsed row abcdef12 at line 3" in capsys.readouterr().out
    if row.startswith("| ABCDEF12"):
        assert "first parsed-but-uncounted row ABCDEF12 at line 3" in capsys.readouterr().out
