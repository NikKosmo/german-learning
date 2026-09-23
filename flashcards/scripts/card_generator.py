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
import shutil
import subprocess
import sys
import tempfile
import time
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

# Constants
PENDING_CARDS_JSON = paths.FLASHCARDS_SCRIPTS / "pending_cards.json"
PENDING_CARDS_SCHEMA = paths.FLASHCARDS_SCRIPTS / "pending_cards_schema.json"
FAILED_WORDS_FILE = paths.FLASHCARDS_SCRIPTS / "failed_words.txt"
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

# What one word can cost when everything degrades: two generations (the retry) and two
# validations. loom caps this whole script, and the arithmetic never fitted — a single
# degraded word needs 420s against a 300s cap, so the outer timeout fired, SIGKILLed the
# process, and took the summary line with it. That is the worst possible failure: the
# words that HAD succeeded were thrown away too, because loom learns per-word outcomes
# only from a summary that never got printed.
WORST_CASE_WORD_SECONDS = 2 * GENERATION_TIMEOUT_SECONDS + 2 * VALIDATOR_TIMEOUT_SECONDS

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


def clear_gatekeeper_quarantine(binary: str = CODEX_PATH) -> None:
    """Strip com.apple.quarantine from the codex binary if macOS put it back.

    codex is a Homebrew *cask*, so every `brew upgrade` writes a fresh copy carrying
    a fresh quarantine stamp. The first run after an upgrade then waits on a
    Gatekeeper dialog. Interactively you click through it once; under the loom
    service nobody does, and the validator call simply burns its timeout
    (2026-09-23: "Validator backend Codex failed: timed out after 60s", every word,
    the morning after a brew upgrade).

    Stripping the attribute needs no privileges and touches only this one binary,
    so the fix stays here instead of turning Gatekeeper off machine-wide with
    HOMEBREW_CASK_OPTS=--no-quarantine. Best-effort by design: if it cannot be
    removed, say so and carry on — probe_validator() below is what actually decides
    whether the validator can answer.
    """
    if sys.platform != "darwin":
        return
    real = os.path.realpath(binary)
    try:
        listed = subprocess.run(["xattr", real], capture_output=True, text=True, timeout=5)
        if "com.apple.quarantine" not in listed.stdout:
            return
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", real],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        log(f"Cleared com.apple.quarantine from {real} (Homebrew Cask sets it on every install).")
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"WARNING: could not clear com.apple.quarantine from {real}: {exc}")


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
    # A quarantined binary answers nothing; clear it before asking it a question.
    clear_gatekeeper_quarantine()
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


def parse_verdict(raw: str) -> tuple[bool, list[str]]:
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
        raise VerdictError(f"reply is not JSON ({exc})") from exc
    except ValueError as exc:
        # Not redundant with JSONDecodeError: an integer past Python's str->int
        # conversion limit raises a plain ValueError from inside the decoder, which
        # would otherwise escape _ask_validators entirely and skip the fallback.
        raise VerdictError(f"reply could not be decoded ({exc})") from exc
    if not isinstance(data, dict):
        raise VerdictError(f"reply is a JSON {type(data).__name__}, not an object")
    valid = data.get("valid")
    # `is` rather than `==`: in Python `1 == True`, and a validator answering `1`
    # has not answered.
    if valid is not True and valid is not False:
        raise VerdictError(f"'valid' is {valid!r}, not a boolean")
    raw_issues = data.get("issues", [])
    if isinstance(raw_issues, str):
        issues = [raw_issues]
    elif isinstance(raw_issues, list):
        # str() each one: "\n".join over a bare string char-splits it, and a
        # non-string member raises out of a function whose caller only catches
        # JSONDecodeError.
        issues = [str(issue) for issue in raw_issues]
    elif raw_issues is None:
        # `null` genuinely means "no issues" and must not become the string "None".
        issues = []
    else:
        # A dict- or scalar-shaped `issues` used to be discarded silently: the verdict
        # survived and the REASON did not, so the retry got no feedback and the
        # quarantine note degraded to a bare date. Keep whatever was sent.
        issues = [str(raw_issues)]
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


def _ask_validators(prompt: str) -> tuple[str | None, tuple[bool, list[str]] | None, list[str]]:
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
{"valid": true, "issues": [], "suggestions": []}"""


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

        if status == "pending" and "✅" in audio:
            words.append(
                {
                    "word": word,
                    "status": status,
                    "audio": audio.replace("✅", "").strip(),
                    "word_type": word_type,
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
    audio = word_info["audio"]

    with open(PENDING_CARDS_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)

    prompt = f"""Generate German flashcard data for the word: "{word}"
Word type: {word_type}
Audio file: {audio}

CRITICAL: Output ONLY a single raw JSON object. No preamble, no explanation, no markdown
code fences, no templates, no frameworks, no wrappers. Do not read any files. Do not use
any tools. Your entire response must be parseable by json.loads() with nothing stripped.

Rules for the JSON content:
1. Conform to the schema below exactly.
2. For Nouns: Create 2 entries (one "Reverse" and one "Cloze").
3. For others: Create 1 entry with "Reverse".
4. Use Russian for translations and notes.
5. For Nouns: "german" must include article (e.g. "der Tisch"), "extra" is plural.
   "Cloze" must use {{{{c1::article}}}} (e.g. "{{{{c1::der}}}} Tisch").
6. For Verbs: "extra" is Perfekt (e.g. "hat gearbeitet").
7. For Adjectives: "extra" is Comparative - Superlative.
8. For Prepositions: "extra" is Case (e.g. "+ Dativ").

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
        raise ValueError(f"Claude returned non-JSON output for '{word}':\n{raw_output}") from err

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as err:
        raise ValueError(
            f"Claude output for '{word}' failed schema validation: {err.message}"
        ) from err

    return data.get("cards", [])


def validate_card_data(word: str, cards: list[dict[str, Any]]) -> tuple[bool, str, bool]:
    """Validate card data using Codex (fallback to Gemini).

    Returns (is_valid, feedback, conclusive). ``conclusive`` is True only when a validator
    actually returned a parseable verdict. An unreachable or unparseable validator is an
    infrastructure failure, not a judgement about the word, and must never quarantine it —
    that class of failure is what silently drained the deck for two months.
    """
    cards_json = json.dumps({"cards": cards}, ensure_ascii=False, indent=2)
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

IMPORTANT: Respond with ONLY valid JSON, no other text. Format:
{{
  "valid": true,
  "issues": [],
  "suggestions": []
}}

Or if invalid:
{{
  "valid": false,
  "issues": ["issue 1", "issue 2"],
  "suggestions": ["suggestion 1"]
}}"""

    log(f"Validating '{word}'...")
    _, verdict, failures = _ask_validators(prompt)

    if verdict is None:
        return False, f"No validator could check this card — {'; '.join(failures)}", False

    is_valid, issues = verdict
    return is_valid, "\n".join(issues), True


QUARANTINE_STATUS = "error"
QUARANTINE_NOTE_LIMIT = 120
QUARANTINE_MARKER = "QUARANTINED:"


def _quarantine_note(reason: str, today: str) -> str:
    """A one-line note that cannot break the markdown table it lives in."""
    flattened = " ".join(reason.split())
    flattened = flattened.replace("|", "/")
    if len(flattened) > QUARANTINE_NOTE_LIMIT:
        flattened = flattened[: QUARANTINE_NOTE_LIMIT - 1].rstrip() + "…"
    return f"{today} validation failed: {flattened}" if flattened else f"{today} validation failed"


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
        if cells[2] == QUARANTINE_STATUS:
            return True
        cells[2] = QUARANTINE_STATUS
        cells[7] = _quarantine_note(reason, today)
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
    try:
        cards = generate_card_data(word_info)
        is_valid, feedback, first_conclusive = validate_card_data(word, cards)
        conclusive = first_conclusive

        # A retry is a second full Claude generation. It is worth spending only when the
        # first attempt produced a real verdict to act on: regenerating a card because
        # the validator was unreachable asks a question nobody is there to answer, and
        # on a five-word run it doubles generation cost inside loom's 300s cap for
        # nothing. An unreachable validator now costs one generation, not two.
        if not is_valid and first_conclusive:
            log(f"Validation failed for '{word}'. Retrying once... Feedback: {feedback}")
            cards = generate_card_data(word_info, retry_feedback=feedback)
            is_valid, feedback, retry_conclusive = validate_card_data(word, cards)
            # Both attempts must have produced a real verdict. Reading `conclusive` off the
            # retry alone let one judged rejection park a word whose first attempt had merely
            # failed to reach the validator, which is the infrastructure failure that must
            # never quarantine.
            conclusive = first_conclusive and retry_conclusive

        if is_valid:
            log(f"✅ Successfully generated and validated cards for '{word}'")
            return WordOutcome(cards)
        else:
            log(f"❌ Failed to validate cards for '{word}'. Feedback: {feedback}")
            with open(FAILED_WORDS_FILE, "a", encoding="utf-8") as f:
                f.write(f"{word}: {feedback}\n")
            if conclusive:
                # The validator judged the word itself. Take it out of the draw so one
                # unwinnable word cannot keep zeroing whole runs.
                parked = quarantine_word(word, word_info.get("word_type", "—"), feedback)
                return WordOutcome([], quarantined=parked, failure_kind=FAILURE_REJECTED)
            log(f"'{word}' stays pending: no validator verdict, so this is not its fault.")
            return WordOutcome([], failure_kind=FAILURE_VALIDATOR_UNREACHABLE)

    except Exception as e:
        msg = f"exception during processing: {e}"
        log(f"ERROR processing '{word}': {msg}")
        # Guarded: if the original exception WAS this append failing (disk full,
        # permissions), retrying it unguarded raises out of process_word and kills
        # the whole run instead of costing one word.
        try:
            with open(FAILED_WORDS_FILE, "a", encoding="utf-8") as f:
                f.write(f"{word}: {msg}\n")
        except OSError as log_exc:
            log(f"WARNING: could not record '{word}' in {FAILED_WORDS_FILE}: {log_exc}")
        return WordOutcome([], failure_kind=FAILURE_GENERATION_ERROR)


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
        deferred=deferred_words,
        cards_inserted=len(all_cards),
    )


if __name__ == "__main__":
    main()
