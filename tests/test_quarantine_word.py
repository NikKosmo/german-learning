"""Quarantine: a word the validator has judged wrong stops being drawn.

One unwinnable word used to zero an entire run — the all-or-nothing contract skips insertion
for the whole batch — and it stayed in the pool, so the same run could fail again tomorrow.
"""

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Imported as a package path rather than a bare module so the type checker can resolve it.
cg = importlib.import_module("flashcards.scripts.card_generator")

TABLE = """# Word Tracking

**Status values:**
- `in_deck` - Already added to german_vocabulary_b1.md
- `pending` - Not processed yet, has audio
- `missing_audio` - No audio file found
- `error` - Generation/validation failed

| Word | Status | Audio | IPA | Word Type | Date Added | Notes |
|------|--------|-------|-----|-----------|------------|-------|
| Spiel | pending | ✅ Spiel.mp3 | — | Noun | — | — |
| spielen | pending | ✅ Spielen.mp3 | — | Verb | — | — |
| Fenster | pending | ✅ Fenster.mp3 | — | Noun | — | — |
| der | in_deck | ✅ Der.mp3 | — | Article | 2025-11-13 | — |
"""


@pytest.fixture
def tracking(tmp_path, monkeypatch):
    import paths

    path = tmp_path / "word_tracking.md"
    path.write_text(TABLE, encoding="utf-8")
    monkeypatch.setattr(paths, "WORD_TRACKING_FILE", path, raising=False)
    return path


def _row(content: str, word: str) -> list[str]:
    for line in content.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 9 and parts[1] == word:
            return parts
    raise AssertionError(f"row for {word} not found")


def test_quarantine_sets_error_status(tracking):
    assert cg.quarantine_word("Spiel", "Noun", 'Перевод "спектакль" неточен') is True
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "error"


def test_quarantine_records_a_dated_reason(tracking):
    cg.quarantine_word("Spiel", "Noun", "translation is wrong")
    note = _row(tracking.read_text(encoding="utf-8"), "Spiel")[7]
    assert "validation failed" in note
    assert "translation is wrong" in note
    assert note[:2] == "20"


def test_quarantined_word_is_no_longer_drawn(tracking, monkeypatch):
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    before = {word["word"] for word in cg.get_pending_words()}
    assert "Spiel" in before

    cg.quarantine_word("Spiel", "Noun", "translation is wrong")

    after = {word["word"] for word in cg.get_pending_words()}
    assert "Spiel" not in after
    assert {"spielen", "Fenster"} <= after


def test_other_rows_are_untouched(tracking):
    original = tracking.read_text(encoding="utf-8")
    cg.quarantine_word("Spiel", "Noun", "translation is wrong")
    updated = tracking.read_text(encoding="utf-8")
    for word in ("spielen", "Fenster", "der"):
        assert _row(original, word) == _row(updated, word)


def test_pipes_and_newlines_cannot_break_the_table(tracking):
    reason = "first issue | second issue\nthird issue"
    cg.quarantine_word("Spiel", "Noun", reason)
    content = tracking.read_text(encoding="utf-8")
    note = _row(content, "Spiel")[7]
    assert "|" not in note
    assert "\n" not in note
    # The table still parses: every row keeps its seven columns.
    for line in content.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            assert len(line.split("|")) == 9


def test_long_feedback_is_truncated(tracking):
    cg.quarantine_word("Spiel", "Noun", "x" * 500)
    note = _row(tracking.read_text(encoding="utf-8"), "Spiel")[7]
    assert len(note) < 200
    assert note.endswith("…")


def test_homonym_of_another_type_is_not_quarantined(tracking):
    cg.quarantine_word("Spiel", "Verb", "wrong type")
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "pending"


def test_unknown_word_is_a_no_op(tracking, monkeypatch):
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    before = tracking.read_text(encoding="utf-8")
    assert cg.quarantine_word("Unbekannt", "Noun", "nope") is False
    assert tracking.read_text(encoding="utf-8") == before


def test_quarantining_twice_is_idempotent(tracking):
    cg.quarantine_word("Spiel", "Noun", "first reason")
    first = tracking.read_text(encoding="utf-8")
    assert cg.quarantine_word("Spiel", "Noun", "second reason") is True
    assert tracking.read_text(encoding="utf-8") == first


def test_quarantining_emits_the_machine_readable_marker(tracking, monkeypatch):
    """loom parks the capture bullet off this line; prose alone would leave it retried forever."""
    lines: list[str] = []
    monkeypatch.setattr(cg, "log", lambda message: lines.append(message))

    cg.quarantine_word("Spiel", "Noun", "translation is wrong")

    assert f"{cg.QUARANTINE_MARKER} Spiel" in lines


def test_unreadable_tracking_file_does_not_raise(tmp_path, monkeypatch):
    import paths

    monkeypatch.setattr(paths, "WORD_TRACKING_FILE", tmp_path / "missing.md", raising=False)
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    assert cg.quarantine_word("Spiel", "Noun", "reason") is False


# --- which failures quarantine ------------------------------------------------------------


def _stub_generation(monkeypatch, verdicts):
    """Feed process_word a fixed sequence of (is_valid, feedback, conclusive) verdicts."""
    calls = iter(verdicts)
    monkeypatch.setattr(cg, "generate_card_data", lambda *args, **kwargs: [{"front": "x"}])
    monkeypatch.setattr(cg, "validate_card_data", lambda *args, **kwargs: next(calls))
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)


def test_a_judged_rejection_quarantines(tracking, monkeypatch, tmp_path):
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    _stub_generation(monkeypatch, [(False, "bad translation", True), (False, "still bad", True)])

    assert cg.process_word({"word": "Spiel", "word_type": "Noun"}).cards == []
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "error"


def test_an_unreachable_validator_leaves_the_word_pending(tracking, monkeypatch, tmp_path):
    """The failure class that drained the deck for two months must never quarantine."""
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    _stub_generation(
        monkeypatch,
        [
            (False, "No validator could check this card — Codex: not installed", False),
            (False, "No validator could check this card — Codex: not installed", False),
        ],
    )

    assert cg.process_word({"word": "Spiel", "word_type": "Noun"}).cards == []
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "pending"


def test_unparseable_validator_output_leaves_the_word_pending(tracking, monkeypatch, tmp_path):
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    _stub_generation(
        monkeypatch,
        [
            (False, "Validation returned invalid JSON: <html>...", False),
            (False, "Validation returned invalid JSON: <html>...", False),
        ],
    )

    assert cg.process_word({"word": "Spiel", "word_type": "Noun"}).cards == []
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "pending"


def test_a_word_that_passes_on_retry_is_not_quarantined(tracking, monkeypatch, tmp_path):
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    _stub_generation(monkeypatch, [(False, "first attempt off", True), (True, "", True)])

    assert cg.process_word({"word": "Spiel", "word_type": "Noun"}).cards == [{"front": "x"}]
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "pending"


def test_an_exception_during_processing_leaves_the_word_pending(tracking, monkeypatch, tmp_path):
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)

    def boom(*args, **kwargs):
        raise RuntimeError("anthropic timeout")

    monkeypatch.setattr(cg, "generate_card_data", boom)

    assert cg.process_word({"word": "Spiel", "word_type": "Noun"}).cards == []
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "pending"


# --- no silent substitution ----------------------------------------------------------------


def test_an_unavailable_request_forfeits_its_slot(tracking, monkeypatch):
    """Asking for a word that cannot be drawn must not run a random substitute instead."""
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    assert cg.select_words(["der"], count=1) == []


def test_a_quarantined_request_is_not_substituted(tracking, monkeypatch):
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    cg.quarantine_word("Spiel", "Noun", "reason")
    assert cg.select_words(["Spiel"], count=1) == []


def test_available_requests_still_resolve(tracking, monkeypatch):
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    selected = cg.select_words(["Fenster"], count=1)
    assert [word["word"] for word in selected] == ["Fenster"]


def test_a_mixed_batch_keeps_the_available_words(tracking, monkeypatch):
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    selected = cg.select_words(["Fenster", "der"], count=2)
    assert [word["word"] for word in selected] == ["Fenster"]


def test_the_daily_drip_still_fills_beyond_the_requested_words(tracking, monkeypatch):
    """The drip is deliberate: count above the requested list still pulls random pending words."""
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    selected = cg.select_words(["Fenster"], count=3)
    assert len(selected) == 3
    assert "Fenster" in {word["word"] for word in selected}


def test_the_drip_is_not_widened_by_an_unavailable_request(tracking, monkeypatch):
    """'der' is in_deck, so it forfeits its slot; the drip fills only its own share."""
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    selected = cg.select_words(["Fenster", "der"], count=3)
    assert len(selected) == 2


# --- two verdicts, not one (2026-08-21) ---


def test_an_inconclusive_first_attempt_blocks_quarantine(tracking, monkeypatch, tmp_path):
    """One judged rejection must not park a word whose first attempt never reached a validator.

    `conclusive` used to be read off the retry alone, so an unreachable validator followed by a
    real verdict parked the word on a single sample of a stochastic judge.
    """
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    _stub_generation(
        monkeypatch,
        [
            (False, "No validator could check this card — Codex: not installed", False),
            (False, "translation is wrong", True),
        ],
    )

    outcome = cg.process_word({"word": "Spiel", "word_type": "Noun"})

    assert outcome.cards == []
    assert outcome.quarantined is False
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "pending"


def test_two_judged_rejections_report_the_word_as_parked(tracking, monkeypatch, tmp_path):
    """The field loom keys its bullet decision on has to be asserted where it is produced."""
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    _stub_generation(monkeypatch, [(False, "bad translation", True), (False, "still bad", True)])

    outcome = cg.process_word({"word": "Spiel", "word_type": "Noun"})

    assert outcome.quarantined is True
    assert _row(tracking.read_text(encoding="utf-8"), "Spiel")[2] == "error"


def test_a_word_that_passes_reports_itself_unparked(tracking, monkeypatch, tmp_path):
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", tmp_path / "failed.txt")
    _stub_generation(monkeypatch, [(True, "", True)])

    outcome = cg.process_word({"word": "Spiel", "word_type": "Noun"})

    assert outcome.cards != []
    assert outcome.quarantined is False
