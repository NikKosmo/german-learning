"""An outage and a verdict must never share a representation.

The 2026-09 outage had two halves. The loud half was a retired Codex model id, which
made every call return HTTP 400 and the deck go fifteen mornings without a card. The
quiet half was worse and had been there far longer: `is_valid = val_data.get("valid",
False)` tested by truthiness, so `{"valid": "false"}` ADMITTED a card, while any
parseable dict — including a provider's rate-limit envelope — counted as a real
verdict and could permanently quarantine a perfectly good word.

These tests hold the line that replaced it: `parse_verdict` is the single gate, it
accepts only an object whose `valid` is exactly `True` or `False`, and preflight and
per-word validation both go through it so the probe can never be green while
production fails on the same payload.
"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

cg = importlib.import_module("flashcards.scripts.card_generator")


# --- parse_verdict: what counts as an answer -------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"valid": true, "issues": []}', (True, [])),
        ('{"valid": false, "issues": ["wrong case"]}', (False, ["wrong case"])),
        ('```json\n{"valid": true, "issues": []}\n```', (True, [])),
        ('  {"valid": false, "issues": []}  ', (False, [])),
    ],
)
def test_a_real_verdict_parses(raw, expected):
    assert cg.parse_verdict(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param('{"valid": "false"}', id="string-false-would-have-admitted"),
        pytest.param('{"valid": "no"}', id="string-no-would-have-admitted"),
        pytest.param('{"valid": 1}', id="int-one-would-have-admitted"),
        pytest.param('{"valid": "0"}', id="string-zero-would-have-admitted"),
        pytest.param('{"valid": NaN}', id="nan-would-have-admitted"),
        pytest.param("{}", id="empty-object"),
        pytest.param('{"issues": []}', id="no-valid-key"),
        pytest.param('{"valid": null}', id="null-verdict"),
        pytest.param('{"error": "rate limited"}', id="provider-error-envelope"),
        pytest.param('"invalid"', id="bare-string-substring-trap"),
        pytest.param("5", id="bare-number"),
        pytest.param("null", id="bare-null"),
        pytest.param("[]", id="bare-list"),
        pytest.param("I could not validate this card.", id="prose"),
        pytest.param("", id="empty"),
    ],
)
def test_anything_that_is_not_a_boolean_verdict_is_an_outage(raw):
    """Every one of these used to be treated as a verdict, and four admitted a card."""
    with pytest.raises(cg.VerdictError):
        cg.parse_verdict(raw)


@pytest.mark.parametrize(
    ("raw", "expected_issues"),
    [
        ('{"valid": false, "issues": "one string"}', ["one string"]),
        ('{"valid": false, "issues": [1, 2]}', ["1", "2"]),
        ('{"valid": true, "issues": null}', []),
        ('{"valid": true}', []),
    ],
)
def test_issues_is_normalised_before_anyone_joins_it(raw, expected_issues):
    """`"\\n".join` over a bare string char-splits it into garbage feedback, and a
    non-string member raises out of a function whose caller only caught JSONDecodeError.
    That garbage then gets written into word_tracking.md as a quarantine note."""
    assert cg.parse_verdict(raw)[1] == expected_issues


# --- the argv: no model id, ever --------------------------------------------------


def test_the_validator_command_pins_no_model_id():
    """A pinned id here has killed this validator twice (gpt-5.2, then gpt-5.4)."""
    for _name, cmd, _env in cg._validator_commands("prompt"):
        assert "-m" not in cmd
        assert "--model" not in cmd
        assert not any("gpt-" in arg for arg in cmd)


def test_probe_and_production_share_one_argv_builder():
    probe_codex = cg._validator_commands(cg.PROBE_PROMPT)[0][1]
    real_codex = cg._validator_commands("a real validation prompt")[0][1]
    assert probe_codex[:-1] == real_codex[:-1]


# --- _ask_validators: exit 0 is not an answer -------------------------------------


def _stub_backends(monkeypatch, replies):
    """Replace the backend list with named stubs, each returning a canned stdout.

    `replies` maps backend name -> stdout string, or to an Exception to raise.
    """
    names = list(replies)
    monkeypatch.setattr(
        cg,
        "_validator_commands",
        lambda prompt: [(n, ["/usr/bin/true", prompt], None) for n in names],
    )
    monkeypatch.setattr(cg.shutil, "which", lambda _binary: "/usr/bin/true")

    calls = []

    def fake_run_command(cmd, cwd=None, extra_env=None, timeout=None, **_kw):
        name = names[len(calls)]
        calls.append({"name": name, "timeout": timeout})
        reply = replies[name]
        if isinstance(reply, Exception):
            raise reply
        return subprocess.CompletedProcess(cmd, 0, stdout=reply, stderr="")

    monkeypatch.setattr(cg, "run_command", fake_run_command)
    return calls


def test_a_backend_that_exits_clean_with_garbage_does_not_end_the_search(monkeypatch):
    """Falling back only on a non-zero exit means "backends in priority order" really
    means "in order of who crashes first". A backend that answers prose has not
    answered, and the next one must still be asked."""
    calls = _stub_backends(
        monkeypatch,
        {"Codex": "I'm sorry, I can't help with that.", "Gemini": '{"valid": true, "issues": []}'},
    )
    name, verdict, failures = cg._ask_validators("prompt")
    assert name == "Gemini"
    assert verdict == (True, [])
    assert [c["name"] for c in calls] == ["Codex", "Gemini"]
    assert any("Codex" in f for f in failures)


def test_a_crashing_backend_falls_through_too(monkeypatch):
    _stub_backends(
        monkeypatch,
        {"Codex": RuntimeError("400 not supported"), "Gemini": '{"valid": false, "issues": []}'},
    )
    name, verdict, _failures = cg._ask_validators("prompt")
    assert name == "Gemini"
    assert verdict == (False, [])


def test_no_backend_answering_is_reported_as_no_verdict_with_every_reason(monkeypatch):
    _stub_backends(monkeypatch, {"Codex": "nonsense", "Gemini": RuntimeError("no auth")})
    name, verdict, failures = cg._ask_validators("prompt")
    assert name is None
    assert verdict is None
    assert len(failures) == 2


def test_every_validator_call_is_bounded(monkeypatch):
    """A hung codex used to block the whole morning job forever: the generation leg
    was bounded and the validation leg was not."""
    calls = _stub_backends(monkeypatch, {"Codex": '{"valid": true, "issues": []}'})
    cg._ask_validators("prompt")
    assert calls[0]["timeout"] == cg.VALIDATOR_TIMEOUT_SECONDS
    assert cg.VALIDATOR_TIMEOUT_SECONDS > 0


# --- the seam between preflight and production ------------------------------------


def test_the_probe_cannot_pass_on_a_payload_production_would_reject(monkeypatch):
    """The false-green that matters: a probe parsing more leniently than production
    reports all-clear over the exact failure it exists to catch."""
    for payload in ['{"valid": "false"}', '"invalid"', "{}", '{"valid": 1}']:
        _stub_backends(monkeypatch, {"Codex": payload, "Gemini": payload})
        backend, _failures = cg.probe_validator()
        assert backend is None, f"probe accepted {payload!r} that production rejects"


def test_the_probe_accepts_fenced_json_only_because_production_does(monkeypatch):
    fenced = '```json\n{"valid": true, "issues": []}\n```'
    _stub_backends(monkeypatch, {"Codex": fenced})
    assert cg.probe_validator()[0] == "Codex"
    assert cg.parse_verdict(fenced) == (True, [])


# --- check_prerequisites: the FAILING direction -----------------------------------


def test_preflight_exits_and_names_the_backend_and_the_remedy(monkeypatch, capsys):
    """The claim is about the unhappy path, so the test has to be too. Checking that
    the codex binary is on PATH was never this check: through the whole outage the
    binary was present and every call 400'd."""
    monkeypatch.setattr(cg, "HAS_RUNNER", True, raising=False)
    monkeypatch.setattr(
        cg, "probe_validator", lambda: (None, ["Codex: 400 not supported", "Gemini: not installed"])
    )
    with pytest.raises(SystemExit) as exit_info:
        cg.check_prerequisites()
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "no validator could answer" in out
    assert "Codex: 400 not supported" in out
    assert "config.toml" in out, "the message must say what to actually do about it"


def test_preflight_passes_quietly_when_a_backend_answers(monkeypatch, capsys):
    monkeypatch.setattr(cg, "HAS_RUNNER", True, raising=False)
    monkeypatch.setattr(cg, "probe_validator", lambda: ("Codex", []))
    cg.check_prerequisites()
    assert "Validator preflight OK (Codex)" in capsys.readouterr().out


# --- validate_card_data: the contract loom depends on -----------------------------


def test_an_unreachable_validator_is_never_conclusive(monkeypatch):
    """conclusive=False is what keeps a dead vendor from quarantining vocabulary."""
    _stub_backends(monkeypatch, {"Codex": '{"error": "rate limited"}', "Gemini": "nope"})
    is_valid, feedback, conclusive = cg.validate_card_data("Haus", [{"german": "das Haus"}])
    assert is_valid is False
    assert conclusive is False
    assert "No validator could check this card" in feedback


def test_a_real_rejection_is_conclusive(monkeypatch):
    _stub_backends(monkeypatch, {"Codex": '{"valid": false, "issues": ["wrong gender"]}'})
    is_valid, feedback, conclusive = cg.validate_card_data("Haus", [{"german": "die Haus"}])
    assert is_valid is False
    assert conclusive is True
    assert feedback == "wrong gender"


def test_a_pass_is_a_real_boolean_not_a_truthy_value(monkeypatch):
    _stub_backends(monkeypatch, {"Codex": '{"valid": true, "issues": []}'})
    is_valid, _feedback, conclusive = cg.validate_card_data("Haus", [{"german": "das Haus"}])
    assert is_valid is True
    assert conclusive is True


# --- failure logging stays readable ------------------------------------------------


def test_a_failed_command_is_not_echoed_with_its_prompt(capsys):
    """argv carries the entire validation prompt. Echoing it is how a one-line failure
    became kilobytes of prompt in failed_words.txt and in the morning message."""
    long_prompt = "PROMPT-NEEDLE " + ("x" * 5000)
    with pytest.raises(subprocess.CalledProcessError):
        cg.run_command(["/usr/bin/false", long_prompt])
    out = capsys.readouterr().out
    assert "PROMPT-NEEDLE" not in out
    assert "false (1 args)" in out


def test_the_provider_error_survives_truncation(capsys):
    """The 400 text is the one thing worth keeping out of a failed call."""
    tail = cg._tail("noise " * 500 + "400 model is not supported")
    assert "400 model is not supported" in tail
    assert len(tail) <= cg.CMD_OUTPUT_TAIL + 1


# --- round 2: findings from the cross-vendor and fresh-context reviews -------------


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param('{"valid": ' + "9" * 5000 + "}", id="integer-past-the-conversion-limit"),
        pytest.param('{"valid": false, "valid": true}', id="duplicate-key-last-wins"),
        pytest.param('{"valid": true, "valid": false}', id="duplicate-key-either-order"),
    ],
)
def test_hostile_json_is_an_outage_not_a_crash_and_not_a_verdict(raw):
    """Both found by the cross-vendor reviewer. An oversized integer raises a plain
    ValueError from inside the decoder, not JSONDecodeError, so it escaped the handler
    and skipped the fallback backend entirely. And json.loads is last-wins, so an
    object that answers twice quietly became whichever answer came last."""
    with pytest.raises(cg.VerdictError):
        cg.parse_verdict(raw)


@pytest.fixture
def isolated_failed_words(monkeypatch, tmp_path):
    """Keep process_word's failure log out of the real, TRACKED failed_words.txt.

    Without this, calling the real `process_word` appends `Haus: no validator` to a
    file that is committed to the repo — and german-learning is a PUBLIC repo. Six
    such rows reached a commit before both round-2 reviewers caught it independently.
    A unit test must never write into production data, and `FAILED_WORDS_FILE` is
    production data: Nik reads it.
    """
    target = tmp_path / "failed_words.txt"
    monkeypatch.setattr(cg, "FAILED_WORDS_FILE", target)
    return target


def test_an_inconclusive_first_attempt_does_not_buy_a_second_generation(
    monkeypatch, isolated_failed_words
):
    """A retry is a whole second Claude generation. Spending it because the validator
    was unreachable asks a question nobody is there to answer, and on a multi-word run
    it doubles generation cost inside loom's script timeout."""
    generations = []
    monkeypatch.setattr(
        cg, "generate_card_data", lambda info, retry_feedback=None: generations.append(1) or [{}]
    )
    monkeypatch.setattr(cg, "validate_card_data", lambda *_a: (False, "no validator", False))
    outcome = cg.process_word({"word": "Haus", "word_type": "Noun", "audio": "x"})
    assert len(generations) == 1
    assert outcome.quarantined is False
    assert outcome.failure_kind == cg.FAILURE_VALIDATOR_UNREACHABLE


def test_a_conclusive_rejection_still_buys_its_one_retry(monkeypatch, isolated_failed_words):
    generations = []
    monkeypatch.setattr(
        cg, "generate_card_data", lambda info, retry_feedback=None: generations.append(1) or [{}]
    )
    monkeypatch.setattr(cg, "validate_card_data", lambda *_a: (False, "wrong", True))
    monkeypatch.setattr(cg, "quarantine_word", lambda *_a: True)
    outcome = cg.process_word({"word": "Haus", "word_type": "Noun", "audio": "x"})
    assert len(generations) == 2
    assert outcome.failure_kind == cg.FAILURE_REJECTED


def test_the_child_s_stdin_is_closed(monkeypatch):
    """The exact regression. capture_output redirects stdout and stderr but NOT stdin,
    so codex inherited the loom service's never-closing pipe and blocked to the
    timeout on every word. No previous test could tell DEVNULL from inherited."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(cg.subprocess, "run", fake_run)
    cg.run_command(["/usr/bin/true"])
    assert seen.get("stdin") is subprocess.DEVNULL


def test_the_run_summary_names_why_it_failed():
    """loom stops grepping the transcript once this field exists."""
    assert cg.worst_failure_kind([]) == cg.FAILURE_NONE
    assert cg.worst_failure_kind([None, cg.FAILURE_REJECTED]) == cg.FAILURE_REJECTED
    # Infrastructure outranks a content verdict: a verdict reached while the machine
    # was dead is a lie about the vocabulary.
    assert (
        cg.worst_failure_kind([cg.FAILURE_REJECTED, cg.FAILURE_VALIDATOR_UNREACHABLE])
        == cg.FAILURE_VALIDATOR_UNREACHABLE
    )
    assert (
        cg.worst_failure_kind([cg.FAILURE_VALIDATOR_UNREACHABLE, cg.FAILURE_NO_VALIDATOR])
        == cg.FAILURE_NO_VALIDATOR
    )


def test_a_unit_test_never_writes_into_the_tracked_failure_log(monkeypatch, isolated_failed_words):
    """The guard that keeps the guard. german-learning is public."""
    monkeypatch.setattr(cg, "generate_card_data", lambda info, retry_feedback=None: [{}])
    monkeypatch.setattr(cg, "validate_card_data", lambda *_a: (False, "no validator", False))
    cg.process_word({"word": "Haus", "word_type": "Noun", "audio": "x"})
    assert isolated_failed_words.exists(), "the failure was recorded..."
    assert "Haus" in isolated_failed_words.read_text(encoding="utf-8")
    # Untracked since 2026-09-20 and recreated on demand, so a clean checkout may not
    # have it at all — which is itself the strongest form of "the test did not write
    # here". Only assert on the content when the file exists.
    real = Path(__file__).resolve().parents[1] / "flashcards/scripts/failed_words.txt"
    if real.exists():
        assert "Haus: no validator" not in real.read_text(encoding="utf-8"), (
            "...but not into the real failure log"
        )


def test_one_degraded_word_fits_inside_the_configured_budget():
    """The arithmetic that was never done. A degraded word costs two generations and
    two validations; the old 300s cap could not fit even one, so loom's outer timeout
    SIGKILLed the script mid-word and took the summary — and every word that had
    already succeeded — with it."""
    assert cg.WORST_CASE_WORD_SECONDS == 2 * cg.GENERATION_TIMEOUT_SECONDS + 2 * (
        cg.VALIDATOR_TIMEOUT_SECONDS
    )
    loom_cap, pipeline_reserve = 900, 60
    generator_budget = loom_cap - pipeline_reserve
    assert generator_budget > cg.WORST_CASE_WORD_SECONDS
