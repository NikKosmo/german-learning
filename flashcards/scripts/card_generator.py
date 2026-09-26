#!/usr/bin/env python3
"""
Automated Flashcard Generation for German Vocabulary
- Selects pending words from word_tracking.md
- Generates card data using Claude CLI
- Validates data using Gemini CLI
- Runs the insertion and deck generation pipeline
"""

import argparse
import contextlib
import json
import os
import random
import re
import reprlib
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

import jsonschema


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON to `path` via temp file + rename. Crash-safe."""
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        tmp_path = Path(tmp.name)
        try:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        except Exception:
            with contextlib.suppress(OSError):
                tmp_path.unlink()
            raise
    os.replace(tmp_path, path)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text to `path` via temp file + rename. Crash-safe."""
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        tmp_path = Path(tmp.name)
        try:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        except Exception:
            with contextlib.suppress(OSError):
                tmp_path.unlink()
            raise
    os.replace(tmp_path, path)


_NOHOOKS_DIR = Path.home() / ".config" / "nohooks"

try:
    import anthropic

    HAS_SDK = True
except ImportError:
    HAS_SDK = False

try:
    from claude_runner import run_claude

    HAS_RUNNER = True
except ImportError:
    HAS_RUNNER = False

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths
from flashcards.scripts import add_words
from flashcards.scripts.word_types import WordType

# Constants
PENDING_CARDS_JSON = paths.FLASHCARDS_SCRIPTS / "pending_cards.json"
PENDING_CARDS_SCHEMA = paths.FLASHCARDS_SCRIPTS / "pending_cards_schema.json"
FAILED_WORDS_FILE = paths.FLASHCARDS_SCRIPTS / "failed_words.txt"
VALIDATOR_VERDICTS_FILE = paths.FLASHCARDS_SCRIPTS / "validator_verdicts.jsonl"
GENERATION_MODEL = "claude-sonnet-5"
CODEX_PATH = "/usr/local/bin/codex"

# No Codex model id is pinned here, deliberately. Pinning one has now killed this
# validator twice: gpt-5.2 was rejected outright in 2026, and gpt-5.4 returned
# HTTP 400 every morning from 2026-09-04 to 09-19 — fifteen runs, no cards, and a
# morning message that blamed the vocabulary. `codex exec` with no `-m` resolves
# its own model: from ~/.codex/config.toml when that file sets one, otherwise from
# the CLI's built-in default.
#
# That is not self-healing and must not be sold as such: ~/.codex/config.toml can
# itself hold a retired id (it did, for the whole outage). What makes the next
# lineup move survivable is not a cleverer id, it is that check_prerequisites()
# refuses to start and says exactly what to do — see VALIDATOR_REMEDY.

# Measured healthy latency is 4.0s (probe, 2026-09-20). loom caps this whole script
# at 300s (`card_generator_timeout_seconds`), and a run can process several words,
# each of which may call a validator twice. At 180s a single hung call ate the entire
# script budget, so the outer timeout fired first and the non-conclusive path below —
# the one that keeps a word out of quarantine — never executed. 60s is ~15x healthy
# latency and leaves the fallback backend and the rest of the run reachable.
VALIDATOR_TIMEOUT_SECONDS = 60
GENERATION_TIMEOUT_SECONDS = 120
WIKTIONARY_TIMEOUT_SECONDS = 10

# What one word can cost when everything degrades: two generations (the retry) and two
# validations. loom caps this whole script, and the arithmetic never fitted — a single
# degraded word needs 420s against a 300s cap, so the outer timeout fired, SIGKILLed the
# process, and took the summary line with it. That is the worst possible failure: the
# words that HAD succeeded were thrown away too, because loom learns per-word outcomes
# only from a summary that never got printed.
WORST_CASE_WORD_SECONDS = (
    2 * GENERATION_TIMEOUT_SECONDS + 2 * VALIDATOR_TIMEOUT_SECONDS + 2 * WIKTIONARY_TIMEOUT_SECONDS
)

VALIDATOR_REMEDY = (
    "If the failure above mentions a model that is 'not supported', then "
    "~/.codex/config.toml pins a retired model id. Either run `codex` once "
    "interactively to accept the migration prompt, or delete its `model = ...` "
    "line so codex resolves its own current default."
)


# --- Why a run produced nothing, as structured data rather than log prose ----------
#
# loom used to answer that question by grepping this script's whole stdout, which
# cannot distinguish "the primary backend timed out and the fallback then judged the
# word" from "nobody answered", and read a CLAUDE GENERATION timeout as a validator
# timeout. The script knows the answer exactly; it should say so once, in a field.
FAILURE_NONE = "none"
FAILURE_NO_VALIDATOR = "no_validator"  # preflight: nothing could answer at all
FAILURE_VALIDATOR_UNREACHABLE = "validator_unreachable"  # a word got no verdict
FAILURE_GENERATION_ERROR = "generation_error"  # an exception while generating
FAILURE_REJECTED = "rejected"  # a validator genuinely judged the word
FAILURE_PIPELINE_ERROR = "pipeline_error"  # insert/apkg/tracking step failed

# Most actionable first: infrastructure outranks a content verdict, because a verdict
# reached while the machine was healthy is information and a verdict attributed to a
# dead machine is a lie about Nik's vocabulary.
FAILURE_PRECEDENCE = (
    FAILURE_NO_VALIDATOR,
    FAILURE_VALIDATOR_UNREACHABLE,
    FAILURE_PIPELINE_ERROR,
    FAILURE_GENERATION_ERROR,
    FAILURE_REJECTED,
)


def print_summary(
    *,
    status: str,
    failure_kind: str,
    words_requested: int,
    generated=(),
    failed=(),
    quarantined=(),
    retried_parked=(),
    deferred=(),
    cards_inserted: int = 0,
) -> None:
    """The one line loom parses. Printed on EVERY exit path, without exception.

    Three exits used to print nothing: the pending_cards write failure, the
    insert/apkg pipeline failure, and (until this session) the preflight abort. With
    no summary line loom has no structured answer and falls back to reading the
    transcript, which is how a dead Anki got reported as a validator problem. A
    script that exits silently forces the reader to guess, and the guess is what this
    whole subsystem keeps getting wrong.
    """
    print(
        json.dumps(
            {
                "status": status,
                "failure_kind": failure_kind,
                "words_requested": words_requested,
                "words_generated": len(generated),
                "cards_inserted": cards_inserted,
                "generated": list(generated),
                "failed": list(failed),
                "quarantined": list(quarantined),
                "retried_parked": list(retried_parked),
                "deferred": list(deferred),
            },
            ensure_ascii=False,
        )
    )


def worst_failure_kind(kinds) -> str:
    """The most actionable failure kind present, or FAILURE_NONE."""
    present = {k for k in kinds if k}
    for kind in FAILURE_PRECEDENCE:
        if kind in present:
            return kind
    return FAILURE_NONE


def log(message: str) -> None:
    """Print message to stdout"""
    print(message)


def check_prerequisites() -> None:
    """Verify required CLI tools are available before starting"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    # Only two generation paths are implemented: the anthropic SDK (needs both a
    # key AND the package) and run_claude from claude-runner. A bare `claude` on
    # PATH is not one of them, so accepting it here let a broken claude_runner
    # import pass preflight and resurface 200 lines later as
    # `NameError: name 'run_claude' is not defined`, once per word, with the real
    # cause nowhere in the output. Fail here instead, naming what is missing.
    if not (api_key and HAS_SDK) and not HAS_RUNNER:
        log(
            "ERROR: no usable generation path. "
            f"anthropic SDK installed: {HAS_SDK}, ANTHROPIC_API_KEY set: {bool(api_key)}, "
            f"claude_runner importable: {HAS_RUNNER}. "
            "If claude_runner is False, the venv most likely holds the unrelated PyPI "
            "'claude-runner' package — reinstall from "
            "git+https://github.com/NikKosmo/claude-runner.git@main"
        )
        sys.exit(1)
    # Validation needs at least one validator that can actually ANSWER. Checking
    # that a binary is on PATH is not that check: through the whole 2026-09 outage
    # the codex binary was present and every call 400'd. So ask it one real
    # question, through the same argv builder and the same parser production uses,
    # and require a real verdict back.
    backend, failures = probe_validator()
    if backend is None:
        log("ERROR: no validator could answer, so no card could be checked.")
        for failure in failures:
            log(f"  - {failure}")
        log(VALIDATOR_REMEDY)
        # The summary line is part of the contract with loom, so it is printed on THIS
        # exit path too. Without it a preflight abort was the one failure loom could
        # only diagnose by reading prose.
        print_summary(status="failed", failure_kind=FAILURE_NO_VALIDATOR, words_requested=0)
        sys.exit(1)
    log(f"Validator preflight OK ({backend}).")


def run_command(
    cmd: list[str],
    cwd: Path | str | None = None,
    unset_claudecode: bool = False,
    extra_env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result.

    ``timeout`` is not optional in spirit: a validator call with no bound can hang
    the whole morning job behind an expired login or a stalled network, and the
    generation leg has always been bounded while the validation leg was not.
    """
    env: dict[str, str] | None = None
    if unset_claudecode or extra_env:
        env = dict(os.environ)
        if unset_claudecode:
            env.pop("CLAUDECODE", None)
        if extra_env:
            env.update(extra_env)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
            env=env,
            timeout=timeout,
            # `capture_output` redirects stdout and stderr but NOT stdin, so a child
            # inherits ours. `codex exec` reads stdin when it is not a TTY ("Reading
            # additional input from stdin..."), and under the loom service that is a
            # pipe which never reaches EOF — so it blocks until the timeout, on every
            # single word. Caught by the end-to-end run on 2026-09-20: identical calls
            # answered in 4s from a shell and hit the 180s cap under the service.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        # Never echo the command: argv carries the whole validation prompt, and
        # dumping it here is how a one-line failure became an unreadable wall in
        # failed_words.txt and in the morning message.
        log(f"ERROR: {_describe_cmd(cmd)} timed out after {timeout}s")
        raise
    except subprocess.CalledProcessError as e:
        log(f"ERROR: {_describe_cmd(cmd)} failed with exit {e.returncode}")
        log(f"STDOUT: {_tail(e.stdout)}")
        log(f"STDERR: {_tail(e.stderr)}")
        raise


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    return text


CMD_OUTPUT_TAIL = 500


def _describe_cmd(cmd: list[str]) -> str:
    """Name a command without reprinting its arguments.

    The validator's argv contains the entire prompt — schema, card JSON, the lot.
    Logging `' '.join(cmd)` put several kilobytes of prompt into failed_words.txt
    and, through loom, into the morning message.
    """
    return f"{Path(cmd[0]).name} ({len(cmd) - 1} args)"


def _tail(text: str | None) -> str:
    """Last part of a captured stream — where a provider's error actually lands."""
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= CMD_OUTPUT_TAIL else "…" + text[-CMD_OUTPUT_TAIL:]


def _reject_duplicate_keys(pairs):
    """Refuse an object that answers twice.

    `json.loads` is last-wins, so `{"valid": false, "valid": true}` quietly becomes a
    PASS. Two different answers in one payload is not a verdict, whichever one the
    decoder happens to keep.
    """
    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r} in validator reply")
        seen.add(key)
    return dict(pairs)


class VerdictError(Exception):
    """A validator replied, but not with a verdict."""


VERDICT_ERROR_VALUE_REPR_LIMIT = 160
VERDICT_ERROR_MESSAGE_LIMIT = 240
VALIDATOR_ISSUE_PROBLEM_LIMIT = 240
MAX_VALIDATOR_ISSUES = 10


def _short_verdict_repr(value: object) -> str:
    """Represent validator-supplied values without letting them become log payloads."""
    rendered = reprlib.repr(value)
    if len(rendered) <= VERDICT_ERROR_VALUE_REPR_LIMIT:
        return rendered
    return rendered[: VERDICT_ERROR_VALUE_REPR_LIMIT - 1] + "…"


def _verdict_error(message: str) -> VerdictError:
    """Build a log-safe parser error at the only source of validator reply details."""
    if len(message) > VERDICT_ERROR_MESSAGE_LIMIT:
        message = message[: VERDICT_ERROR_MESSAGE_LIMIT - 1] + "…"
    return VerdictError(message)


def _truncate_validator_problem(problem: str) -> str:
    """Keep accepted validator feedback safe for every downstream consumer."""
    problem = problem.strip()
    if len(problem) > VALIDATOR_ISSUE_PROBLEM_LIMIT:
        return problem[: VALIDATOR_ISSUE_PROBLEM_LIMIT - 1] + "…"
    return problem


VALIDATOR_CARD_FIELDS = ("russian", "german", "extra", "example_de", "example_ru", "notes")
VALIDATOR_ISSUE_FIELDS = frozenset((*VALIDATOR_CARD_FIELDS, "general"))


def parse_verdict(raw: str) -> tuple[bool, list[dict[str, str]]]:
    """Turn a validator's raw reply into ``(valid, issues)``.

    Raises :class:`VerdictError` for anything that is not an unambiguous verdict.
    That line is the whole point of this function. An outage and a verdict must
    never share a representation, and "it parsed as JSON" is not the same fact as
    "a model judged this word":

    * ``{"valid": "false"}`` is a string, and truthiness would have ADMITTED the
      card. So would ``{"valid": 1}``, ``{"valid": "no"}`` and ``{"valid": "0"}``.
    * ``{}``, ``{"valid": null}`` and ``{"error": "rate limited"}`` are a provider
      envelope, not a judgement — treating them as one is what can quarantine a
      perfectly good word on the vendor's schedule.
    * ``json.loads('"invalid"')`` is a bare string; a substring test for "valid"
      passes on it while it means the opposite.

    Both the preflight probe and per-word validation go through here, so the probe
    cannot be green while production fails on the same payload.
    """
    try:
        data = json.loads(_strip_fences(raw), object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise _verdict_error(f"reply is not JSON ({_short_verdict_repr(str(exc))})") from exc
    except ValueError as exc:
        # Not redundant with JSONDecodeError: an integer past Python's str->int
        # conversion limit raises a plain ValueError from inside the decoder, which
        # would otherwise escape _ask_validators entirely and skip the fallback.
        raise _verdict_error(
            f"reply could not be decoded ({_short_verdict_repr(str(exc))})"
        ) from exc
    if not isinstance(data, dict):
        raise _verdict_error(f"reply is a JSON {type(data).__name__}, not an object")
    valid = data.get("valid")
    # `is` rather than `==`: in Python `1 == True`, and a validator answering `1`
    # has not answered.
    if valid is not True and valid is not False:
        raise _verdict_error(f"'valid' is {_short_verdict_repr(valid)}, not a boolean")
    raw_issues = data.get("issues")
    # A true verdict is unambiguous even when a backend omits its empty optional
    # list, or serializes it as null. A rejection still has to explain itself.
    if raw_issues is None and valid is True:
        raw_issues = []
    elif "issues" not in data:
        raise _verdict_error("verdict has no 'issues' array")
    if not isinstance(raw_issues, list):
        raise _verdict_error("'issues' is not an array")

    issues: list[dict[str, str]] = []
    for index, issue in enumerate(raw_issues, start=1):
        if not isinstance(issue, dict):
            raise _verdict_error(f"issue {index} is not an object")
        field = issue.get("field")
        if not isinstance(field, str) or field not in VALIDATOR_ISSUE_FIELDS:
            raise _verdict_error(
                f"issue {index} has unknown or missing field {_short_verdict_repr(field)}"
            )
        problem = issue.get("problem")
        if not isinstance(problem, str) or not problem.strip():
            raise _verdict_error(f"issue {index} has an empty or missing problem")
        issues.append({"field": field, "problem": _truncate_validator_problem(problem)})
    if valid is False and not issues:
        raise _verdict_error("an invalid verdict needs at least one issue")
    if len(issues) > MAX_VALIDATOR_ISSUES:
        dropped_count = len(issues) - (MAX_VALIDATOR_ISSUES - 1)
        issues = issues[: MAX_VALIDATOR_ISSUES - 1]
        issues.append(
            {
                "field": "general",
                "problem": f"{dropped_count} additional validator issues were dropped.",
            }
        )
    return valid, issues


def _validator_commands(prompt: str) -> list[tuple[str, list[str], dict[str, str] | None]]:
    """Validator backends in priority order, as (name, argv, extra_env).

    Codex leads. Gemini's free individual tier is decommissioned (IneligibleTierError
    / UNSUPPORTED_CLIENT), so leading with it cost a failed round-trip on every word;
    it stays last so that restoring auth needs no code change.

    One builder, used by both the preflight probe and per-word validation — sharing
    the argv is necessary but not sufficient, which is why they share the parser too.
    """
    return [
        (
            "Codex",
            [CODEX_PATH, "exec", "--skip-git-repo-check", "-s", "read-only", "--", prompt],
            None,
        ),
        ("Gemini", ["gemini", "-p", prompt], {"GEMINI_CLI_TRUST_WORKSPACE": "true"}),
    ]


def _ask_validators(
    prompt: str,
) -> tuple[str | None, tuple[bool, list[dict[str, str]]] | None, list[str]]:
    """Ask each backend in turn and return the first genuine verdict.

    Returns ``(backend_name, (valid, issues), failures)``, or ``(None, None, failures)``
    when nobody answered usably.

    Exit code 0 is not an answer. A backend that exits clean with prose, an error
    envelope or a truncated payload has failed to answer, and the next backend must
    still be tried — otherwise "backends in priority order" only means "in order of
    who crashes first".
    """
    failures: list[str] = []
    for name, cmd, extra_env in _validator_commands(prompt):
        if not shutil.which(cmd[0]) and not Path(cmd[0]).exists():
            failures.append(f"{name}: not installed")
            continue
        log(f"Asking {name} for a verdict...")
        try:
            raw_output = run_command(
                cmd, cwd=_NOHOOKS_DIR, extra_env=extra_env, timeout=VALIDATOR_TIMEOUT_SECONDS
            ).stdout
        except Exception as exc:
            reason = _describe_failure(exc)
            # "Validator backend" is load-bearing: it is how loom's fallback matcher
            # tells this apart from a Claude GENERATION timeout, which also contains
            # the words "timed out after".
            log(f"Validator backend {name} failed: {reason}")
            failures.append(f"{name}: {reason}")
            continue
        try:
            return name, parse_verdict(raw_output), failures
        except VerdictError as exc:
            log(f"Validator backend {name} answered but not with a verdict: {exc}")
            _record_validator_contract_breach(name, raw_output, str(exc))
            failures.append(f"{name}: {exc}")
    return None, None, failures


def _describe_failure(exc: Exception) -> str:
    """A backend failure in one readable clause.

    `str(TimeoutExpired)` and `str(CalledProcessError)` both embed the full argv, and
    argv carries the entire validation prompt. Left raw, these strings land in
    failed_words.txt, in a quarantine note, and in the morning message.
    """
    if isinstance(exc, subprocess.TimeoutExpired):
        return f"timed out after {exc.timeout}s"
    if isinstance(exc, subprocess.CalledProcessError):
        detail = _tail(exc.stderr) or _tail(exc.stdout)
        return f"exit {exc.returncode}{f' — {detail}' if detail else ''}"
    return f"{type(exc).__name__}: {exc}"


PROBE_PROMPT = """You are validating German vocabulary card data.

Word: Haus
Generated data:
{"cards": [{"german": "das Haus", "russian": "дом"}]}

Respond with ONLY valid JSON, no other text, in exactly this shape:
{"valid": true, "issues": [], "suggestions": []}

For an invalid result, use:
{"valid": false, "issues": [{"field": "german", "problem": "..."}], "suggestions": []}

Every issue must be an object with field and problem. For this data, field must be
russian or german; use general only when no one field is responsible."""


def probe_validator() -> tuple[str | None, list[str]]:
    """Preflight: which backend can answer right now, if any.

    Deliberately routed through :func:`_ask_validators`, so the probe runs the same
    argv and the same acceptance rule as every real validation. A preflight that
    parses more leniently than production is worse than no preflight — it reports
    all-clear over the exact failure it was added to catch.
    """
    name, verdict, failures = _ask_validators(PROBE_PROMPT)
    return (name if verdict is not None else None), failures


def get_pending_words() -> list[dict[str, str]]:
    """Read word_tracking.md and return list of pending words with audio"""
    words = []
    if not paths.WORD_TRACKING_FILE.exists():
        log(f"ERROR: {paths.WORD_TRACKING_FILE} not found")
        sys.exit(1)

    with open(paths.WORD_TRACKING_FILE, encoding="utf-8") as f:
        lines = f.readlines()

    # Find table start
    table_start = -1
    for i, line in enumerate(lines):
        if line.startswith("| Word | Status |"):
            table_start = i
            break

    if table_start == -1:
        log("ERROR: Could not find table in word_tracking.md")
        sys.exit(1)

    for line in lines[table_start + 2 :]:
        line = line.strip()
        if not line.startswith("|"):
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            continue

        word = parts[1]
        status = parts[2]
        audio = parts[3]
        word_type = parts[5]

        retrying_parked = status == QUARANTINE_STATUS and _is_retryable_parked_note(parts[7])
        if (status == "pending" or retrying_parked) and "✅" in audio:
            words.append(
                {
                    "word": word,
                    "status": status,
                    "audio": audio.replace("✅", "").strip(),
                    "word_type": word_type,
                    "parked_retry": retrying_parked,
                }
            )

    return words


def select_words(requested_words: list[str] | None, count: int) -> list[dict[str, str]]:
    """Select words based on requested list and total count"""
    all_pending = get_pending_words()
    selected = []
    unavailable = 0

    # 1. Start with explicitly requested words
    if requested_words:
        for req in requested_words:
            # Case-sensitive match
            match = next((w for w in all_pending if w["word"] == req), None)
            if match:
                selected.append(match)
            else:
                unavailable += 1
                # Check if it exists at all but is not pending
                msg = (
                    f"WARNING: Requested word '{req}' is not available "
                    "(not pending, quarantined, or missing audio)"
                )
                log(msg)

    # 2. Fill remaining slots randomly for the daily drip.
    # A requested word that is unavailable forfeits its slot rather than being swapped for a
    # random substitute: that would attribute the substitute's failure to the word you asked
    # for, which is exactly how a request for 'fief' produced a failed run on 'Salvaging'.
    remaining_count = count - len(selected) - unavailable
    if remaining_count > 0:
        others = [w for w in all_pending if w not in selected]
        if len(others) < remaining_count:
            msg = (
                f"WARNING: Only {len(others)} more pending words available "
                f"(requested {remaining_count})"
            )
            log(msg)
            selected.extend(others)
        else:
            selected.extend(random.sample(others, remaining_count))

    return selected


def generate_card_data(
    word_info: dict[str, str], retry_feedback: str | None = None
) -> list[dict[str, Any]]:
    """Generate card data using Claude CLI"""
    word = word_info["word"]
    word_type = word_info["word_type"]
    with open(PENDING_CARDS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
    language_rule = (
        "5. russian is Cyrillic without Latin; example_ru has no Latin word; "
        "German fields lack Cyrillic; notes have Cyrillic."
    )
    forms_rule = (
        '6. Forms (extra): Noun: "die <Plural>" or "— (kein Plural)". '
        'Verb: "hat [sich] <Partizip II>" or "ist [sich] <Partizip II>", '
        'and two auxiliaries are written "hat geschwommen / ist geschwommen". '
        'Preposition: "+ Akkusativ", "+ Dativ", "+ Genitiv", or a two-case form '
        'such as "+ Akkusativ / + Dativ". All remaining types except Adjective and '
        'Adjective/Adverb: "—".'
    )

    prompt = f"""Generate German flashcard data for the word: "{word}"
Word type: {word_type}

CRITICAL: Output ONLY a single raw JSON object. No preamble, no explanation, no markdown
code fences, no templates, no frameworks, no wrappers. Do not read any files. Do not use
any tools. Your entire response must be parseable by json.loads() with nothing stripped.

Rules for the JSON content:
1. Conform to the schema below exactly.
2. Make exactly one Reverse and one Cloze for a Noun; make exactly one Reverse for every other type.
3. Noun Reverse german is exactly article + "{word}"; Cloze is exactly "{{{{c1::article}}}} {word}".
4. Cloze markup {{{{...}}}} appears only in the german field of the Cloze card.
{language_rule}
{forms_rule}
7. Adjective and Adjective/Adverb extra: "<Komparativ> — am <Superlativ>",
   or "— (keine Steigerung)" if not gradable.
8. No field may contain a pipe character or a newline, and notes are at most 200 characters.
9. The returned word_type must be exactly "{word_type}". Every german value must end
   with the tracking word "{word}". Do not include audio; code supplies it.

JSON Schema:
{schema_str}
"""
    if retry_feedback:
        prompt += (
            "\n\nValidation failed previously with this feedback. Please fix these issues:\n"
            f"{retry_feedback}"
        )

    log(f"Calling Claude for '{word}'...")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key and HAS_SDK:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=GENERATION_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            # The run_claude branch has always passed timeout=120; this one passed
            # nothing, so the SDK path could hang the morning job exactly the way the
            # validator did before it was bounded.
            timeout=GENERATION_TIMEOUT_SECONDS,
        )
        raw_output = message.content[0].text  # type: ignore[union-attr]
    else:
        raw_output = run_claude(prompt, model=GENERATION_MODEL, timeout=GENERATION_TIMEOUT_SECONDS)

    cleaned = _strip_fences(raw_output)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise MalformedModelOutputError(
            f"Claude returned non-JSON output for '{word}':\n{raw_output}"
        ) from err

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as err:
        raise MalformedModelOutputError(
            f"Claude output for '{word}' failed schema validation: {err.message}"
        ) from err

    return data.get("cards", [])


def _record_validator_verdict(
    word: str,
    attempt: int,
    valid: bool,
    issues: list[dict[str, str]],
    dropped_issues: list[dict[str, str]],
) -> None:
    """Append one compact, machine-readable record for a validator judgement."""
    record: dict[str, Any] = {
        "word": word,
        "attempt": attempt,
        "valid": valid,
        "issues": issues,
        "dropped_issues": dropped_issues,
    }
    try:
        with open(VALIDATOR_VERDICTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log(
            f"WARNING: could not record validator verdict for '{word}' "
            f"in {VALIDATOR_VERDICTS_FILE}: {exc}"
        )


def _record_validator_contract_breach(backend: str, raw_reply: str, parse_error: str) -> None:
    """Record an unusable validator reply without turning it into a verdict."""
    record = {
        "not_a_verdict": True,
        "backend": backend,
        "parse_error": _tail(parse_error),
        "raw_reply": _tail(raw_reply),
    }
    try:
        with open(VALIDATOR_VERDICTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log(
            f"WARNING: could not record validator contract breach from {backend} "
            f"in {VALIDATOR_VERDICTS_FILE}: {exc}"
        )


def validate_card_data(
    word: str,
    cards: list[dict[str, Any]],
    wiktionary_extra_authoritative: bool = False,
    attempt: int | None = None,
) -> tuple[bool, str, bool]:
    """Validate card data using Codex (fallback to Gemini).

    Returns (is_valid, feedback, conclusive). ``conclusive`` is True only when a validator
    actually returned a parseable verdict. An unreachable or unparseable validator is an
    infrastructure failure, not a judgement about the word, and must never quarantine it —
    that class of failure is what silently drained the deck for two months.
    """
    hidden_fields = {"extra"} if wiktionary_extra_authoritative else set()
    validator_cards = [
        {
            key: value
            for key, value in card.items()
            if key not in {"word_type", "audio", "card_type", *hidden_fields}
        }
        for card in cards
    ]
    sent_fields = [
        field for field in VALIDATOR_CARD_FIELDS if any(field in card for card in validator_cards)
    ]
    allowed_fields_text = ", ".join([*sent_fields, "general"])
    cards_json = json.dumps({"cards": validator_cards}, ensure_ascii=False, indent=2)
    prompt = f"""You are validating German vocabulary card data
for a Russian native speaker learning German.

Word: {word}
Generated data:
{cards_json}

Validate:
1. Russian translation is accurate
2. Grammatical forms are correct
3. Example sentences are natural German
4. Russian translations of examples are accurate
5. Grammatical notes are helpful and in Russian

IMPORTANT: Respond with ONLY valid JSON, no other text. Every issue must be an object
with a field and problem. field must be one of the fields actually sent above:
{allowed_fields_text}. Use general only for an issue that does not belong to one field.
Format:
{{
  "valid": true,
  "issues": [],
  "suggestions": []
}}

Or if invalid:
{{
  "valid": false,
  "issues": [
    {{"field": "german", "problem": "issue 1"}},
    {{"field": "general", "problem": "issue 2"}}
  ],
  "suggestions": ["suggestion 1"]
}}"""

    log(f"Validating '{word}'...")
    _, verdict, failures = _ask_validators(prompt)

    if verdict is None:
        return False, f"No validator could check this card — {'; '.join(failures)}", False

    is_valid, issues = verdict
    dropped_issues: list[dict[str, str]] = []
    if "extra" in hidden_fields:
        for issue in issues:
            if issue["field"] == "extra":
                reason = "extra was omitted because Wiktionary supplied or confirmed it"
                dropped_issues.append({**issue, "reason": reason})
                log(f"Validator contract breach for '{word}': {reason}; dropping issue.")
        issues = [issue for issue in issues if issue["field"] != "extra"]

    # An invalid reply whose only objections are about a field it was not sent is a pass.
    if not is_valid and not issues:
        is_valid = True
    if attempt is not None:
        _record_validator_verdict(word, attempt, is_valid, issues, dropped_issues)
    feedback = "\n".join(f"{issue['field']}: {issue['problem']}" for issue in issues)
    return is_valid, feedback, True


class NounLookupError(Exception):
    """Wiktionary could not be reached while checking a noun."""


class MalformedModelOutputError(ValueError):
    """The model reply was not JSON or did not satisfy the card schema.

    This is the only generation failure that is safe to retry with feedback.
    Other ValueErrors can originate in provider or local configuration code and
    must be reported after a single generation attempt.
    """


def _template_parts(template) -> dict[str, list[str]]:
    """Return named values from a Wiktionary template in its parsetree XML."""
    result: dict[str, list[str]] = {}
    for part in template.findall("part"):
        name = part.findtext("name")
        value = part.findtext("value")
        if name is None or value is None:
            continue
        result.setdefault(name.strip(), []).append(value.strip())
    return result


class NounInflectionEntry(NamedTuple):
    """One German Wiktionary noun entry, retaining its gender/plural pairing."""

    gender: str
    plurals: tuple[str, ...]


def _german_section_children(root):
    """Yield only direct parsetree children in the Deutsch language section."""
    children = list(root)
    start: int | None = None
    for index, child in enumerate(children):
        if (
            child.tag == "h"
            and child.get("level") == "2"
            and add_words._h_contains_sprache(child, add_words.GERMAN_LANGUAGE_NAME)
        ):
            start = index
            break
    if start is None:
        return []
    end = len(children)
    for index in range(start + 1, len(children)):
        child = children[index]
        if child.tag == "h" and child.get("level") == "2":
            end = index
            break
    return children[start + 1 : end]


def lookup_noun_inflection(word: str) -> list[NounInflectionEntry] | None:
    """Read paired plural alternatives and gender from German noun overviews.

    A missing page or overview is deliberately not a failure: Wiktionary is useful
    corroboration, not a reason to discard a card for a word it does not cover.
    Transport failures are different, because silently accepting data after a
    failed lookup would claim the lookup had checked it.
    """
    try:
        payload = add_words.fetch_parse_payload(word, WIKTIONARY_TIMEOUT_SECONDS)
        parse_block = add_words._validate_parse_payload(payload)
        xml = add_words._extract_parsetree_xml(parse_block)
        root = add_words.ET.fromstring(xml)
    except add_words.LookupErrorResult as exc:
        if exc.message.startswith("Wiktionary unreachable"):
            raise NounLookupError(exc.message) from exc
        return None
    except add_words.ET.ParseError:
        return None

    entries: list[NounInflectionEntry] = []
    for child in _german_section_children(root):
        if child.tag != "template":
            continue
        template = child
        title = add_words._template_title(template)
        if title != "Deutsch Substantiv Übersicht":
            continue
        parts = _template_parts(template)
        for name, values in parts.items():
            match = re.fullmatch(r"Genus(?: (\d+))?", name)
            if match is None:
                continue
            suffix = f" {match.group(1)}" if match.group(1) else ""
            plural_name = f"Nominativ Plural{suffix}"
            plural_values = parts.get(plural_name)
            if plural_values is None:
                plural_values = parts.get("Nominativ Plural")
            if plural_values is None:
                plural_values = [
                    value
                    for plural_key, values_for_key in parts.items()
                    if re.fullmatch(r"Nominativ Plural \d+", plural_key)
                    for value in values_for_key
                ]
            plurals = tuple(value for value in plural_values if value)
            for value in values:
                for gender in value.split(","):
                    gender = gender.strip()
                    if gender:
                        entries.append(NounInflectionEntry(gender, plurals))
    return entries or None


def _noun_article(german: str) -> str | None:
    match = re.fullmatch(r"(der|die|das) .+", german)
    return match.group(1) if match else None


def _noun_gender(article: str) -> str:
    return {"der": "m", "die": "f", "das": "n"}[article]


def _allowed_noun_genders(entries: list[NounInflectionEntry]) -> str:
    labels = {"m": "der (m)", "f": "die (f)", "n": "das (n)", "0": "die (plural-only)"}
    return " or ".join(
        labels[gender]
        for gender in ("f", "m", "n", "0")
        if any(entry.gender == gender for entry in entries)
    )


def _noun_extra(plural: str) -> str:
    return "— (kein Plural)" if plural == "—" else f"die {plural}"


class GenerationCheckResult(list[str]):
    """Deterministic complaints plus whether Wiktionary owns the noun plural."""

    def __init__(self, complaints: list[str], wiktionary_extra_authoritative: bool):
        super().__init__(complaints)
        self.wiktionary_extra_authoritative = wiktionary_extra_authoritative


def _noun_allowed_extras(
    noun_lookup: list[NounInflectionEntry], cards: list[dict[str, Any]]
) -> set[str]:
    articles = {
        article
        for card in cards
        if (article := _noun_article(str(card.get("german", "")))) is not None
    }
    matching_entries = [
        entry
        for entry in noun_lookup
        if any(
            entry.gender == _noun_gender(article) or (entry.gender == "0" and article == "die")
            for article in articles
        )
    ]
    return {_noun_extra(plural) for entry in matching_entries for plural in entry.plurals}


def _wiktionary_extra_is_authoritative(
    noun_lookup: list[NounInflectionEntry] | None, cards: list[dict[str, Any]]
) -> bool:
    """Whether the current noun extra was written or confirmed from Wiktionary."""
    if noun_lookup is None or not cards:
        return False
    allowed = _noun_allowed_extras(noun_lookup, cards)
    return bool(allowed) and (
        len(allowed) == 1 or all(str(card.get("extra")) in allowed for card in cards)
    )


def _expected_forms_format(word_type: object) -> str:
    if not isinstance(word_type, str):
        return "`—`"
    formats = {
        WordType.NOUN.value: "`die <Plural>` or `— (kein Plural)`",
        WordType.VERB.value: (
            "`hat [sich] <Partizip II>` or `ist [sich] <Partizip II>`; two forms use ` / `"
        ),
        WordType.PREPOSITION.value: (
            "`+ Akkusativ`, `+ Dativ`, `+ Genitiv`, or `+ Akkusativ / + Dativ`"
        ),
        WordType.ADJECTIVE.value: ("`<Komparativ> — am <Superlativ>` or `— (keine Steigerung)`"),
        WordType.ADJECTIVE_ADVERB.value: (
            "`<Komparativ> — am <Superlativ>` or `— (keine Steigerung)`"
        ),
    }
    return formats.get(word_type, "`—`")


def _forms_are_valid(card: dict[str, Any]) -> bool:
    word_type = card.get("word_type")
    extra = card.get("extra")
    if not isinstance(extra, str):
        return False
    if word_type == WordType.NOUN.value:
        return extra == "— (kein Plural)" or bool(re.fullmatch(r"die [^\s—][^—]*", extra))
    if word_type in {WordType.ADJECTIVE.value, WordType.ADJECTIVE_ADVERB.value}:
        match = re.fullmatch(r"(.+) — am (.+)", extra)
        return extra == "— (keine Steigerung)" or bool(
            match and "—" not in match.group(1) and "—" not in match.group(2)
        )
    if word_type == WordType.VERB.value:
        forms = extra.split(" / ")
        form = r"(?:hat|ist) (?:sich )?[^\s—][^—]*"
        return len(forms) in {1, 2} and all(re.fullmatch(form, value) for value in forms)
    if word_type == WordType.PREPOSITION.value:
        case = r"\+ (?:Akkusativ|Dativ|Genitiv)"
        return bool(re.fullmatch(case + r"(?: / " + case + r")?", extra))
    return extra == "—"


REQUIRED_CARD_FIELDS = {
    "card_type",
    "word_type",
    "russian",
    "german",
    "extra",
    "example_de",
    "example_ru",
    "notes",
}


def _is_latin_letter(char: str) -> bool:
    """Whether ``char`` is a Unicode letter from the Latin script."""
    return unicodedata.category(char).startswith("L") and "LATIN" in unicodedata.name(char, "")


def _contains_latin(text: str) -> bool:
    return any(_is_latin_letter(char) for char in text)


def _has_latin_run(text: str) -> bool:
    run_length = 0
    for char in text:
        run_length = run_length + 1 if _is_latin_letter(char) else 0
        if run_length >= 2:
            return True
    return False


def check_generated_cards(
    word_info: dict[str, str], cards: list[dict[str, Any]]
) -> GenerationCheckResult:
    """Return every deterministic generation complaint without repairing a card."""
    word = word_info["word"]
    expected_type = word_info["word_type"]
    complaints: list[str] = []
    if expected_type == WordType.NOUN.value:
        reverse = [card for card in cards if card.get("card_type") == "Reverse"]
        cloze = [card for card in cards if card.get("card_type") == "Cloze"]
        if len(cards) != 2 or len(reverse) != 1 or len(cloze) != 1:
            complaints.append("a noun needs exactly one Reverse and one Cloze card")
        elif reverse[0].get("german") not in {f"der {word}", f"die {word}", f"das {word}"}:
            complaints.append("noun Reverse german must be article plus the tracking word")
        elif cloze[0].get("german") != "{{c1::" + reverse[0]["german"].split()[0] + "}} " + word:
            complaints.append(
                "noun Cloze german must hide the Reverse article and use the tracking word"
            )
    elif len(cards) != 1 or cards[0].get("card_type") != "Reverse":
        complaints.append("a non-noun needs exactly one Reverse card")

    noun_lookup: list[NounInflectionEntry] | None = None
    if expected_type == WordType.NOUN.value:
        noun_lookup = lookup_noun_inflection(word)

    # A single Wiktionary-supported plural is authoritative and must be repaired
    # before the general Forms check evaluates it.
    if noun_lookup is not None and cards:
        allowed = _noun_allowed_extras(noun_lookup, cards)
        if len(allowed) == 1:
            extra = next(iter(allowed))
            for card in cards:
                card["extra"] = extra

    for index, card in enumerate(cards, start=1):
        missing = REQUIRED_CARD_FIELDS - card.keys()
        if missing:
            complaints.append(
                f"card {index} is missing required fields: {', '.join(sorted(missing))}"
            )
        if card.get("word_type") != expected_type:
            complaints.append(
                f"card {index} has word_type {card.get('word_type')!r}; expected {expected_type!r}"
            )
        for field, value in card.items():
            if not isinstance(value, str):
                complaints.append(f"card {index} field {field} is not text")
                continue
            if "|" in value or "\n" in value or "\r" in value:
                complaints.append(f"card {index} field {field} contains a table-breaking character")
            if (field != "german" or card.get("card_type") != "Cloze") and (
                "{{" in value or "}}" in value
            ):
                complaints.append(f"card {index} has cloze markup outside Cloze german")
        russian = str(card.get("russian", ""))
        example_ru = str(card.get("example_ru", ""))
        german = str(card.get("german", ""))
        example_de = str(card.get("example_de", ""))
        notes = str(card.get("notes", ""))
        if not re.search(r"[\u0400-\u052f]", russian) or _contains_latin(russian):
            complaints.append(f"card {index} russian must be Cyrillic without Latin")
        if _has_latin_run(example_ru):
            complaints.append(f"card {index} example_ru has a Latin word")
        if re.search(r"[\u0400-\u052f]", german + example_de):
            complaints.append(f"card {index} German fields contain Cyrillic")
        if not re.search(r"[\u0400-\u052f]", notes):
            complaints.append(f"card {index} notes need Cyrillic")
        if len(notes) > 200:
            complaints.append(f"card {index} notes exceed 200 characters")
        if not _forms_are_valid(card):
            complaints.append(
                f"card {index} extra has the wrong format for {card.get('word_type')}; "
                f"expected {_expected_forms_format(card.get('word_type'))}"
            )
        if expected_type != WordType.NOUN.value and (
            not german.split() or german.split()[-1].lower() != word.lower()
        ):
            complaints.append(f"card {index} german does not end with the tracking word")

    if noun_lookup is not None and cards:
        articles = {
            article
            for card in cards
            if (article := _noun_article(str(card.get("german", "")))) is not None
        }
        matching_entries = [
            entry
            for entry in noun_lookup
            if any(
                entry.gender == _noun_gender(article) or (entry.gender == "0" and article == "die")
                for article in articles
            )
        ]
        if articles and not matching_entries:
            complaints.append(
                "noun article disagrees with Wiktionary Genus; "
                f"Wiktionary gives {word} as {_allowed_noun_genders(noun_lookup)}"
            )
        elif matching_entries:
            allowed = {
                _noun_extra(plural) for entry in matching_entries for plural in entry.plurals
            }
            if len(allowed) == 1:
                extra = next(iter(allowed))
                for card in cards:
                    card["extra"] = extra
            elif len(allowed) > 1 and any(str(card.get("extra")) not in allowed for card in cards):
                complaints.append(
                    "noun plural is not one of Wiktionary's alternatives; "
                    f"expected one of {', '.join(sorted(allowed))}"
                )
    return GenerationCheckResult(complaints, _wiktionary_extra_is_authoritative(noun_lookup, cards))


def _attach_audio(cards: list[dict[str, Any]], audio: str) -> list[dict[str, Any]]:
    for card in cards:
        card["audio"] = audio
    return cards


QUARANTINE_STATUS = "error"
QUARANTINE_NOTE_LIMIT = 120
QUARANTINE_MARKER = "QUARANTINED:"


def _park_count(note: str) -> int:
    match = re.search(r"validation failed \((\d+)\):", note)
    return int(match.group(1)) if match else 1


def _is_retryable_parked_note(note: str) -> bool:
    match = re.match(r"(\d{4}-\d{2}-\d{2}) validation failed", note)
    if match is None or _park_count(note) >= 2:
        return False
    try:
        parked_on = datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return False
    return (datetime.now().date() - parked_on).days >= 30


def _quarantine_note(reason: str, today: str, count: int) -> str:
    """A one-line note that cannot break the markdown table it lives in."""
    flattened = " ".join(reason.split())
    flattened = flattened.replace("|", "/")
    if len(flattened) > QUARANTINE_NOTE_LIMIT:
        flattened = flattened[: QUARANTINE_NOTE_LIMIT - 1].rstrip() + "…"
    prefix = f"{today} validation failed ({count}):"
    return f"{prefix} {flattened}" if flattened else prefix


def quarantine_word(word: str, word_type: str, reason: str) -> bool:
    """Mark a word `error` in word_tracking.md so it stops being drawn.

    `error` is an existing documented status that update_word_tracking.py already preserves
    across its recompute, so nothing else has to change. Returns True when a row was updated.
    """
    tracking_path = paths.WORD_TRACKING_FILE
    try:
        content = tracking_path.read_text(encoding="utf-8")
    except OSError as exc:
        log(f"WARNING: could not read {tracking_path} to quarantine '{word}': {exc}")
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    lines = content.splitlines()
    updated = False

    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        if len(parts) < 9:
            continue
        cells = [part.strip() for part in parts]
        if cells[1] != word:
            continue
        # Match the type too, so a homonym pair is not quarantined wholesale.
        if word_type not in ("—", "", None) and cells[5] not in (word_type, "—", ""):
            continue
        if cells[2] == QUARANTINE_STATUS and not _is_retryable_parked_note(cells[7]):
            return True
        count = _park_count(cells[7]) + 1 if cells[2] == QUARANTINE_STATUS else 1
        cells[2] = QUARANTINE_STATUS
        cells[7] = _quarantine_note(reason, today, count)
        lines[index] = "| " + " | ".join(cells[1:8]) + " |"
        updated = True
        break

    if not updated:
        log(f"WARNING: '{word}' not found in {tracking_path}; nothing quarantined")
        return False

    try:
        _atomic_write_text(tracking_path, "\n".join(lines) + "\n")
    except OSError as exc:
        log(f"WARNING: could not write {tracking_path} to quarantine '{word}': {exc}")
        return False

    # Machine-readable for loom: the capture bullet should be parked, not retried tomorrow.
    log(f"{QUARANTINE_MARKER} {word}")
    log(f"🚫 Quarantined '{word}' (status → {QUARANTINE_STATUS}); it will not be drawn again.")
    return True


class WordOutcome(NamedTuple):
    """What one word produced: its cards, and whether it was parked on the way out.

    `quarantined` is what tells the caller a failure is permanent. A word that merely failed
    stays pending and is worth another run tomorrow; a parked one never will be, so its capture
    bullet should go rather than sit there being retried forever.
    """

    cards: list[dict[str, Any]]
    quarantined: bool = False
    # Why this word produced nothing, when it produced nothing. Carried as data so the
    # run summary can state the reason instead of loom grepping for it.
    failure_kind: str | None = None


def process_word(word_info: dict[str, str]) -> WordOutcome:
    """Generate and validate cards for a single word, with one retry"""
    word = word_info["word"]
    feedback = ""
    had_deterministic_failure = False
    for attempt in range(2):
        complaints = ["no cards generated"]
        wiktionary_extra_authoritative = False
        try:
            cards = generate_card_data(word_info, retry_feedback=feedback or None)
        except MalformedModelOutputError as exc:
            cards = []
            complaints = [f"generation output is invalid: {exc}"]
        except Exception as exc:
            reason = f"generation failed: {_describe_failure(exc)}"
            log(f"Generation failed for '{word}': {reason}")
            _record_failed_word(word, reason)
            return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)

        if cards:
            try:
                check_result = check_generated_cards(word_info, cards)
                complaints = check_result
                wiktionary_extra_authoritative = getattr(
                    check_result, "wiktionary_extra_authoritative", False
                )
            except NounLookupError as exc:
                reason = f"generation check could not complete: {exc}"
                log(f"Generation check failed for '{word}': {reason}")
                _record_failed_word(word, reason)
                return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)
            except Exception as exc:
                reason = f"generation check could not complete: {_describe_failure(exc)}"
                log(f"Generation check failed for '{word}': {reason}")
                _record_failed_word(word, reason)
                return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)
        if complaints:
            feedback = "\n".join(complaints)
            had_deterministic_failure = True
            if attempt == 0:
                log(f"Generation check failed for '{word}'. Retrying once... Feedback: {feedback}")
                continue
            log(f"Generation check failed for '{word}' on retry: {feedback}")
            _record_failed_word(word, feedback)
            return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)
        try:
            is_valid, feedback, conclusive = validate_card_data(
                word, cards, wiktionary_extra_authoritative, attempt + 1
            )
        except Exception as exc:
            reason = f"validation could not complete: {_describe_failure(exc)}"
            log(f"Validation failed for '{word}': {reason}")
            _record_failed_word(word, reason)
            return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)
        if is_valid:
            try:
                return WordOutcome(_attach_audio(cards, word_info.get("audio", "—")))
            except Exception as exc:
                reason = f"could not finish generated cards: {_describe_failure(exc)}"
                log(f"Generation failed for '{word}': {reason}")
                _record_failed_word(word, reason)
                return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)
        if not conclusive:
            _record_failed_word(word, feedback)
            return WordOutcome([], failure_kind=FAILURE_VALIDATOR_UNREACHABLE)
        if attempt == 0:
            continue
        if had_deterministic_failure:
            log(
                f"Validator rejected '{word}' after a generation check failure; leaving it pending."
            )
            _record_failed_word(word, feedback)
            return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)
        _record_failed_word(word, feedback)
        try:
            parked = quarantine_word(word, word_info.get("word_type", "—"), feedback)
        except Exception as exc:
            reason = f"could not quarantine rejected word: {_describe_failure(exc)}"
            log(f"Validation failed for '{word}': {reason}")
            _record_failed_word(word, reason)
            return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)
        return WordOutcome([], quarantined=parked, failure_kind=FAILURE_REJECTED)
    raise AssertionError("unreachable")


def _record_failed_word(word: str, feedback: str) -> None:
    try:
        with open(FAILED_WORDS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{word}: {feedback}\n")
    except OSError as exc:
        log(f"WARNING: could not record '{word}' in {FAILED_WORDS_FILE}: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Automated Flashcard Generator")
    parser.add_argument("--words", type=str, help="Comma-separated list of words")
    parser.add_argument("--count", type=int, default=10, help="Total number of words to process")
    parser.add_argument(
        "--deadline-seconds",
        type=float,
        default=None,
        help="Stop starting new words once one more could overrun this budget, and "
        "report what was finished. Prevents the caller's own timeout from killing the "
        "run before it can say what happened.",
    )
    args = parser.parse_args()
    started_at = time.monotonic()

    check_prerequisites()

    # Step 1 (WORKFLOW.md): refresh word_tracking.md before selecting words
    log("Step 0: Refreshing word tracking status...")
    try:
        run_command([sys.executable, "update_word_tracking.py"], cwd=paths.FLASHCARDS_SCRIPTS)
    except Exception as e:
        log(f"WARNING: update_word_tracking.py failed at start: {e}")

    requested_words = [w.strip() for w in args.words.split(",")] if args.words else None

    selected_words = select_words(requested_words, args.count)
    if not selected_words:
        log("No words selected. Exiting.")
        return

    log(f"Processing {len(selected_words)} words...")

    all_cards = []
    generated_words: list[str] = []
    failed_words: list[str] = []
    quarantined_words: list[str] = []
    retried_parked_words: list[str] = []
    failure_kinds: list[str | None] = []
    deferred_words: list[str] = []
    for index, word_info in enumerate(selected_words):
        # Stop BEFORE starting a word that could overrun, not after being killed during
        # one. Deferred words are untouched: still pending, redrawn tomorrow, and
        # deliberately not counted as failures, because nothing was attempted.
        if args.deadline_seconds is not None and index > 0:
            spent = time.monotonic() - started_at
            if spent + WORST_CASE_WORD_SECONDS > args.deadline_seconds:
                deferred_words = [w["word"] for w in selected_words[index:]]
                log(
                    f"⏳ Stopping after {index} of {len(selected_words)} words: "
                    f"{spent:.0f}s spent of a {args.deadline_seconds:.0f}s budget, and one "
                    f"more word could need {WORST_CASE_WORD_SECONDS}s. "
                    f"Deferred to the next run: {', '.join(deferred_words)}"
                )
                break
        outcome = process_word(word_info)
        if word_info.get("parked_retry"):
            retried_parked_words.append(word_info["word"])
        if outcome.cards:
            all_cards.extend(outcome.cards)
            generated_words.append(word_info["word"])
        else:
            failed_words.append(word_info["word"])
            failure_kinds.append(outcome.failure_kind)
            if outcome.quarantined:
                quarantined_words.append(word_info["word"])
    failure_kind = worst_failure_kind(failure_kinds)

    # A failed word costs its own slot and nothing else. The predecessor of this block discarded
    # the whole batch on any failure, which zeroed ten of eleven drip runs in August; it existed
    # only because the exit code was the sole signal loom had. The summary below carries the
    # per-word outcome instead, so loom can keep the right capture bullets without the script
    # having to throw away good cards to make a point.
    if failed_words:
        log(
            f"⚠️ {len(failed_words)} of {len(selected_words)} words failed: "
            f"{', '.join(failed_words)}. See failed_words.txt for details."
        )

    if not all_cards:
        log("No cards were successfully generated. Exiting.")
        print_summary(
            status="failed",
            failure_kind=failure_kind,
            words_requested=len(selected_words),
            failed=failed_words,
            quarantined=quarantined_words,
            retried_parked=retried_parked_words,
            deferred=deferred_words,
        )
        sys.exit(1)

    # Write pending_cards.json atomically (temp file + rename) so a crash
    # mid-write cannot leave a truncated file that a later run would consume.
    log(f"Writing {len(all_cards)} cards to {PENDING_CARDS_JSON}...")
    _atomic_write_json(PENDING_CARDS_JSON, {"cards": all_cards})

    # Verification of written file
    if not PENDING_CARDS_JSON.exists():
        log(f"ERROR: Failed to write {PENDING_CARDS_JSON}")
        print_summary(
            status="failed",
            failure_kind=FAILURE_PIPELINE_ERROR,
            words_requested=len(selected_words),
            generated=generated_words,
            failed=failed_words,
            quarantined=quarantined_words,
            retried_parked=retried_parked_words,
            deferred=deferred_words,
        )
        sys.exit(1)

    # Run pipeline
    log("Running pipeline scripts...")
    try:
        log("Step 1: Inserting cards...")
        run_command([sys.executable, "insert_cards.py"], cwd=paths.FLASHCARDS_SCRIPTS)

        log("Step 2: Generating .apkg...")
        run_command([sys.executable, "generate_deck_from_md.py"], cwd=paths.FLASHCARDS_SCRIPTS)
    except Exception as e:
        log(f"ERROR: Pipeline failed: {e}")
        # Anki being down lands here. Without this line loom saw no structured
        # answer, fell back to the transcript, and named the validator — a
        # subsystem that had in fact answered every word correctly.
        print_summary(
            status="failed",
            failure_kind=FAILURE_PIPELINE_ERROR,
            words_requested=len(selected_words),
            generated=generated_words,
            failed=failed_words,
            quarantined=quarantined_words,
            retried_parked=retried_parked_words,
            deferred=deferred_words,
            cards_inserted=len(all_cards),
        )
        sys.exit(1)

    try:
        log("Step 3: Updating word tracking...")
        run_command([sys.executable, "update_word_tracking.py"], cwd=paths.FLASHCARDS_SCRIPTS)
    except Exception as e:
        log(f"WARNING: update_word_tracking.py failed (cards already inserted): {e}")

    log("✅ Pipeline completed successfully!")

    # Final output
    print_summary(
        status="partial" if (failed_words or deferred_words) else "success",
        failure_kind=failure_kind,
        words_requested=len(selected_words),
        generated=generated_words,
        failed=failed_words,
        quarantined=quarantined_words,
        retried_parked=retried_parked_words,
        deferred=deferred_words,
        cards_inserted=len(all_cards),
    )


if __name__ == "__main__":
    main()
