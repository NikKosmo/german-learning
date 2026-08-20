"""A failed word costs its own slot, not the whole batch.

The all-or-nothing contract this replaces discarded every card in a run as soon as one word
failed validation. In August that zeroed ten of eleven drip runs: on 2026-08-20 four words
passed and `einige` did not, and all four were thrown away. These tests hold the new contract —
partial insertion, with the per-word outcome carried in the summary loom reads.
"""

import importlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

cg = importlib.import_module("flashcards.scripts.card_generator")

if TYPE_CHECKING:
    # `cg` is a module object at runtime, so `cg.WordOutcome` is a variable and cannot
    # appear in a type expression. The static import gives the annotation a real type
    # without changing how the module is loaded.
    from flashcards.scripts.card_generator import WordOutcome


def _card(word: str) -> dict[str, str]:
    return {"card_type": "recognition", "german": word}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Run main() with every side effect stubbed except the pending-cards write."""
    pending = tmp_path / "pending_cards.json"
    commands: list[str] = []

    monkeypatch.setattr(cg, "PENDING_CARDS_JSON", pending)
    monkeypatch.setattr(cg, "check_prerequisites", lambda: None)
    monkeypatch.setattr(cg, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cg, "run_command", lambda command, **kwargs: commands.append(Path(command[-1]).name)
    )
    monkeypatch.setattr(sys, "argv", ["card_generator.py", "--count", "5"])
    return {"pending": pending, "commands": commands}


def _plan(monkeypatch, outcomes: "dict[str, WordOutcome]"):
    """Give main() a fixed word list and a fixed outcome per word."""
    monkeypatch.setattr(
        cg,
        "select_words",
        lambda requested, count: [{"word": word, "word_type": "Noun"} for word in outcomes],
    )
    monkeypatch.setattr(cg, "process_word", lambda info: outcomes[info["word"]])


def _summary(capsys) -> dict:
    for line in reversed(capsys.readouterr().out.splitlines()):
        if line.strip().startswith("{"):
            return json.loads(line)
    raise AssertionError("no JSON summary was printed")


def test_a_partial_batch_inserts_the_passing_words(harness, monkeypatch, capsys):
    _plan(
        monkeypatch,
        {
            "lang": cg.WordOutcome([_card("lang")]),
            "einige": cg.WordOutcome([], quarantined=True),
            "Mensch": cg.WordOutcome([_card("Mensch")]),
        },
    )

    cg.main()

    summary = _summary(capsys)
    assert summary["status"] == "partial"
    assert summary["words_generated"] == 2
    assert summary["generated"] == ["lang", "Mensch"]
    assert summary["failed"] == ["einige"]
    assert summary["quarantined"] == ["einige"]
    written = json.loads(harness["pending"].read_text(encoding="utf-8"))
    assert [card["german"] for card in written["cards"]] == ["lang", "Mensch"]
    assert "insert_cards.py" in harness["commands"]


def test_a_clean_batch_still_reports_success(harness, monkeypatch, capsys):
    _plan(monkeypatch, {"lang": cg.WordOutcome([_card("lang")])})

    cg.main()

    summary = _summary(capsys)
    assert summary["status"] == "success"
    assert summary["failed"] == []
    assert summary["quarantined"] == []


def test_a_word_that_failed_without_a_verdict_is_not_reported_as_parked(
    harness, monkeypatch, capsys
):
    """Only a judged rejection parks a word; an unreachable validator must leave it retryable."""
    _plan(
        monkeypatch,
        {"lang": cg.WordOutcome([_card("lang")]), "einige": cg.WordOutcome([])},
    )

    cg.main()

    summary = _summary(capsys)
    assert summary["failed"] == ["einige"]
    assert summary["quarantined"] == []


def test_a_batch_where_everything_failed_inserts_nothing_and_exits_1(harness, monkeypatch, capsys):
    _plan(
        monkeypatch,
        {"lang": cg.WordOutcome([]), "einige": cg.WordOutcome([], quarantined=True)},
    )

    with pytest.raises(SystemExit) as exit_info:
        cg.main()

    assert exit_info.value.code == 1
    assert not harness["pending"].exists()
    assert harness["commands"] == ["update_word_tracking.py"]
    summary = _summary(capsys)
    assert summary["status"] == "failed"
    assert summary["words_generated"] == 0
    assert summary["quarantined"] == ["einige"]
