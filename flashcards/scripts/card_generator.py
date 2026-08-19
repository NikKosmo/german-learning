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
from datetime import datetime
from pathlib import Path
from typing import Any

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
GENERATION_MODEL = "claude-sonnet-4-6"
CODEX_PATH = "/usr/local/bin/codex"
# Codex rejects retired model ids with a 400 that the fallback only surfaces as
# "Both Gemini and Codex failed to validate". Bump this when the account's Codex
# lineup moves; gpt-5.2 was rejected outright from 2026.
CODEX_MODEL = "gpt-5.4"


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
    # Validation needs at least one validator, not specifically Gemini — its free
    # individual tier is decommissioned, so hard-requiring it here would block
    # every run on a tool that can no longer answer.
    if not Path(CODEX_PATH).exists() and not shutil.which("codex") and not shutil.which("gemini"):
        log("ERROR: no validation backend available — need codex or gemini on PATH.")
        sys.exit(1)


def run_command(
    cmd: list[str],
    cwd: Path | str | None = None,
    unset_claudecode: bool = False,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result"""
    env: dict[str, str] | None = None
    if unset_claudecode or extra_env:
        env = dict(os.environ)
        if unset_claudecode:
            env.pop("CLAUDECODE", None)
        if extra_env:
            env.update(extra_env)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=cwd, env=env)
    except subprocess.CalledProcessError as e:
        log(f"ERROR: Command failed: {' '.join(cmd)}")
        log(f"STDOUT: {e.stdout}")
        log(f"STDERR: {e.stderr}")
        raise


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    return text


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
        )
        raw_output = message.content[0].text  # type: ignore[union-attr]
    else:
        raw_output = run_claude(prompt, model=GENERATION_MODEL, timeout=120)

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

    # Codex leads. Gemini's free individual tier was decommissioned (it now fails
    # with IneligibleTierError / UNSUPPORTED_CLIENT), so leaving it first cost a
    # full failed prompt round-trip on every single word before Codex picked up.
    # It stays as a fallback so that restoring Gemini auth needs no code change.
    validators: list[tuple[str, list[str], dict[str, str] | None]] = [
        (
            "Codex",
            [
                CODEX_PATH,
                "exec",
                "--skip-git-repo-check",
                "-m",
                CODEX_MODEL,
                "-s",
                "read-only",
                "--",
                prompt,
            ],
            None,
        ),
        ("Gemini", ["gemini", "-p", prompt], {"GEMINI_CLI_TRUST_WORKSPACE": "true"}),
    ]

    raw_output = None
    failures: list[str] = []
    for name, cmd, extra_env in validators:
        if not shutil.which(cmd[0]) and not Path(cmd[0]).exists():
            failures.append(f"{name}: not installed")
            continue
        log(f"Calling {name} to validate '{word}'...")
        try:
            raw_output = run_command(cmd, cwd=_NOHOOKS_DIR, extra_env=extra_env).stdout
            break
        except Exception as exc:
            log(f"{name} failed: {exc}")
            failures.append(f"{name}: {exc}")

    if raw_output is None:
        return False, f"No validator could check this card — {'; '.join(failures)}", False

    try:
        val_data = json.loads(raw_output.strip())
        is_valid = val_data.get("valid", False)
        issues = val_data.get("issues", [])
        feedback = "\n".join(issues)
        return is_valid, feedback, True
    except json.JSONDecodeError as e:
        log(f"Failed to parse validation response: {e}\nRaw output: {raw_output}")
        return False, f"Validation returned invalid JSON: {raw_output[:100]}...", False


QUARANTINE_STATUS = "error"
QUARANTINE_NOTE_LIMIT = 120


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

    log(f"🚫 Quarantined '{word}' (status → {QUARANTINE_STATUS}); it will not be drawn again.")
    return True


def process_word(word_info: dict[str, str]) -> list[dict[str, Any]]:
    """Generate and validate cards for a single word, with one retry"""
    word = word_info["word"]
    try:
        cards = generate_card_data(word_info)
        is_valid, feedback, conclusive = validate_card_data(word, cards)

        if not is_valid:
            log(f"Validation failed for '{word}'. Retrying once... Feedback: {feedback}")
            cards = generate_card_data(word_info, retry_feedback=feedback)
            is_valid, feedback, conclusive = validate_card_data(word, cards)

        if is_valid:
            log(f"✅ Successfully generated and validated cards for '{word}'")
            return cards
        else:
            log(f"❌ Failed to validate cards for '{word}' after retry. Feedback: {feedback}")
            with open(FAILED_WORDS_FILE, "a", encoding="utf-8") as f:
                f.write(f"{word}: {feedback}\n")
            if conclusive:
                # The validator judged the word itself, twice. Take it out of the draw so one
                # unwinnable word cannot keep zeroing whole runs.
                quarantine_word(word, word_info.get("word_type", "—"), feedback)
            else:
                log(f"'{word}' stays pending: no validator verdict, so this is not its fault.")
            return []

    except Exception as e:
        msg = f"exception during processing: {e}"
        log(f"ERROR processing '{word}': {msg}")
        with open(FAILED_WORDS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{word}: {msg}\n")
        return []


def main():
    parser = argparse.ArgumentParser(description="Automated Flashcard Generator")
    parser.add_argument("--words", type=str, help="Comma-separated list of words")
    parser.add_argument("--count", type=int, default=10, help="Total number of words to process")
    args = parser.parse_args()

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
    processed_count = 0
    failed_words: list[str] = []
    for word_info in selected_words:
        cards = process_word(word_info)
        if cards:
            all_cards.extend(cards)
            processed_count += 1
        else:
            failed_words.append(word_info["word"])

    # All-or-nothing contract: if any per-word failure, do not insert anything
    # and exit non-zero so loom keeps the bullets in the capture file for retry.
    if failed_words:
        log(
            f"❌ {len(failed_words)} of {len(selected_words)} words failed: "
            f"{', '.join(failed_words)}. Skipping insertion; see failed_words.txt for details."
        )
        sys.exit(1)

    if not all_cards:
        log("No cards were successfully generated. Exiting.")
        sys.exit(1)

    # Write pending_cards.json atomically (temp file + rename) so a crash
    # mid-write cannot leave a truncated file that a later run would consume.
    log(f"Writing {len(all_cards)} cards to {PENDING_CARDS_JSON}...")
    _atomic_write_json(PENDING_CARDS_JSON, {"cards": all_cards})

    # Verification of written file
    if not PENDING_CARDS_JSON.exists():
        log(f"ERROR: Failed to write {PENDING_CARDS_JSON}")
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
        sys.exit(1)

    try:
        log("Step 3: Updating word tracking...")
        run_command([sys.executable, "update_word_tracking.py"], cwd=paths.FLASHCARDS_SCRIPTS)
    except Exception as e:
        log(f"WARNING: update_word_tracking.py failed (cards already inserted): {e}")

    log("✅ Pipeline completed successfully!")

    # Final output
    output = {
        "status": "success",
        "words_requested": len(selected_words),
        "words_generated": processed_count,
        "cards_inserted": len(all_cards),
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
