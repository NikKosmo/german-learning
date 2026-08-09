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


def log(message: str) -> None:
    """Print message to stdout"""
    print(message)


def check_prerequisites() -> None:
    """Verify required CLI tools are available before starting"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not HAS_RUNNER and not shutil.which("claude"):
        log(
            "ERROR: Neither ANTHROPIC_API_KEY is set, nor 'claude-runner' is installed, "
            "nor 'claude' CLI is available. At least one generation method is required."
        )
        sys.exit(1)
    if not shutil.which("gemini"):
        log("ERROR: 'gemini' CLI is not available in PATH.")
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

    # 1. Start with explicitly requested words
    if requested_words:
        for req in requested_words:
            # Case-sensitive match
            match = next((w for w in all_pending if w["word"] == req), None)
            if match:
                selected.append(match)
            else:
                # Check if it exists at all but is not pending
                msg = (
                    f"WARNING: Requested word '{req}' is not available "
                    "(not pending or missing audio)"
                )
                log(msg)

    # 2. Fill remaining slots randomly
    remaining_count = count - len(selected)
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


def validate_card_data(word: str, cards: list[dict[str, Any]]) -> tuple[bool, str]:
    """Validate card data using Gemini CLI (fallback to Codex)"""
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

    log(f"Calling Gemini to validate '{word}'...")
    try:
        result = run_command(
            ["gemini", "-p", prompt],
            cwd=_NOHOOKS_DIR,
            extra_env={"GEMINI_CLI_TRUST_WORKSPACE": "true"},
        )
        raw_output = result.stdout
    except Exception as e:
        log(f"Gemini failed: {e}. Falling back to Codex...")
        try:
            result = run_command(
                [
                    CODEX_PATH,
                    "exec",
                    "--skip-git-repo-check",
                    "-m",
                    "gpt-5.2",
                    "-s",
                    "read-only",
                    "--",
                    prompt,
                ],
                cwd=_NOHOOKS_DIR,
            )
            raw_output = result.stdout
        except Exception as codex_e:
            log(f"Codex fallback failed: {codex_e}")
            return False, f"Both Gemini and Codex failed to validate: {e}, {codex_e}"

    try:
        val_data = json.loads(raw_output.strip())
        is_valid = val_data.get("valid", False)
        issues = val_data.get("issues", [])
        feedback = "\n".join(issues)
        return is_valid, feedback
    except json.JSONDecodeError as e:
        log(f"Failed to parse validation response: {e}\nRaw output: {raw_output}")
        return False, f"Validation returned invalid JSON: {raw_output[:100]}..."


def process_word(word_info: dict[str, str]) -> list[dict[str, Any]]:
    """Generate and validate cards for a single word, with one retry"""
    word = word_info["word"]
    try:
        cards = generate_card_data(word_info)
        is_valid, feedback = validate_card_data(word, cards)

        if not is_valid:
            log(f"Validation failed for '{word}'. Retrying once... Feedback: {feedback}")
            cards = generate_card_data(word_info, retry_feedback=feedback)
            is_valid, feedback = validate_card_data(word, cards)

        if is_valid:
            log(f"✅ Successfully generated and validated cards for '{word}'")
            return cards
        else:
            log(f"❌ Failed to validate cards for '{word}' after retry. Feedback: {feedback}")
            with open(FAILED_WORDS_FILE, "a", encoding="utf-8") as f:
                f.write(f"{word}: {feedback}\n")
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
