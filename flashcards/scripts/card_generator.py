#!/usr/bin/env python3
"""
Automated Flashcard Generation for German Vocabulary
- Selects pending words from word_tracking.md
- Generates card data using Claude CLI
- Validates data using Gemini CLI
- Runs the insertion and deck generation pipeline
"""

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import anthropic

    HAS_SDK = True
except ImportError:
    HAS_SDK = False

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paths
from flashcards.scripts.word_types import WordType

# Constants
PENDING_CARDS_JSON = paths.FLASHCARDS_SCRIPTS / "pending_cards.json"
FAILED_WORDS_FILE = paths.FLASHCARDS_SCRIPTS / "failed_words.txt"
GENERATION_MODEL = "claude-opus-4-6"


def log(message: str) -> None:
    """Print message to stdout"""
    print(message)


def check_prerequisites() -> None:
    """Verify required CLI tools are available before starting"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not shutil.which("claude"):
        log(
            "ERROR: Neither ANTHROPIC_API_KEY is set nor 'claude' CLI is available. "
            "At least one generation method is required."
        )
        sys.exit(1)
    if not shutil.which("gemini"):
        log("ERROR: 'gemini' CLI is not available in PATH.")
        sys.exit(1)


def run_command(
    cmd: list[str], cwd: Path | str | None = None, unset_claudecode: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result"""
    env = None
    if unset_claudecode:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=cwd, env=env)
    except subprocess.CalledProcessError as e:
        log(f"ERROR: Command failed: {' '.join(cmd)}")
        log(f"STDOUT: {e.stdout}")
        log(f"STDERR: {e.stderr}")
        raise


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

    prompt = f"""Generate German flashcard data for the word: "{word}"
Word type: {word_type}
Audio file: {audio}

Follow these rules:
1. Output ONLY a JSON object with a "cards" array.
2. For Nouns: Create 2 entries (one "Reverse" and one "Cloze").
3. For others: Create 1 entry with "Reverse".
4. "Reverse" expands to RU->DE and DE->RU.
5. Fields required: card_type, word_type, russian, german, extra, example_de, example_ru,
   notes, audio.
6. Use Russian for translations and notes.
7. For Nouns: "german" must include article (e.g. "der Tisch"), "extra" is plural.
   "Cloze" must use {{{{c1::article}}}} (e.g. "{{{{c1::der}}}} Tisch").
8. For Verbs: "extra" is Perfekt (e.g. "hat gearbeitet").
9. For Adjectives: "extra" is Comparative - Superlative.
10. For Prepositions: "extra" is Case (e.g. "+ Dativ").

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
        result = run_command(
            ["claude", "-p", prompt, "--model", GENERATION_MODEL], unset_claudecode=True
        )
        raw_output = result.stdout

    # Extract JSON from Claude's response (in case there's extra text)
    json_match = re.search(r"\{.*\}", raw_output, re.DOTALL)
    if not json_match:
        raise ValueError(f"Claude did not return valid JSON for '{word}'")

    data = json.loads(json_match.group(0))
    return data.get("cards", [])


def validate_card_data(word: str, cards: list[dict[str, Any]]) -> tuple[bool, str]:
    """Validate card data using Gemini CLI"""
    cards_json = json.dumps({"cards": cards}, ensure_ascii=False, indent=2)
    prompt = f"""Validate the following German flashcard data for the word "{word}".
Check for:
1. Accuracy of translations (Russian <-> German).
2. Correct word type usage (must be exactly from {list(WordType.all_values())}).
3. Correct plural/perfekt forms.
4. Natural example sentences.
5. All required fields present and non-empty.
6. Formatting (Cloze deletions for nouns, articles included).

Data to validate:
{cards_json}

If valid, respond ONLY with "VALID: YES".
If invalid, respond with "VALID: NO" followed by a list of issues found.
"""
    log(f"Calling Gemini to validate '{word}'...")
    result = run_command(["gemini", prompt])

    is_valid = "VALID: YES" in result.stdout
    feedback = result.stdout.replace("VALID: NO", "").strip() if not is_valid else ""
    return is_valid, feedback


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
        log(f"ERROR processing '{word}': {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Automated Flashcard Generator")
    parser.add_argument("--words", type=str, help="Comma-separated list of words")
    parser.add_argument("--count", type=int, default=10, help="Total number of words to process")
    args = parser.parse_args()

    check_prerequisites()

    requested_words = [w.strip() for w in args.words.split(",")] if args.words else None

    selected_words = select_words(requested_words, args.count)
    if not selected_words:
        log("No words selected. Exiting.")
        return

    log(f"Processing {len(selected_words)} words...")

    all_cards = []
    processed_count = 0
    for word_info in selected_words:
        cards = process_word(word_info)
        if cards:
            all_cards.extend(cards)
            processed_count += 1

    if not all_cards:
        log("No cards were successfully generated. Exiting.")
        return

    # Write pending_cards.json
    log(f"Writing {len(all_cards)} cards to {PENDING_CARDS_JSON}...")
    with open(PENDING_CARDS_JSON, "w", encoding="utf-8") as f:
        json.dump({"cards": all_cards}, f, ensure_ascii=False, indent=2)

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
