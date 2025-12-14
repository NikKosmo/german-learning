"""
Static analysis tests to ensure no script hardcodes word type strings.

Per requirements, WordType enum is the single source of truth. We scan
flashcards/scripts (excluding the enum module itself) for literals like
"Noun", "Verb", etc. Comparisons should use the enum, not strings.
"""

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "flashcards" / "scripts"


WORD_TYPE_LITERALS = {
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
    "Adjective/Adverb",
    "Adverb/Particle",
}


def file_should_be_scanned(path: Path) -> bool:
    # Only Python files under flashcards/scripts, excluding the enum itself
    if path.suffix != ".py":
        return False
    # Exclude the enum module where literals are defined by design
    if path.name == "word_types.py":
        return False
    return True


def strip_allowed_contexts(text: str) -> str:
    """
    Remove/neutralize occurrences of literals that appear in allowed contexts so
    the static scan only flags business-logic misuse. Allowed contexts include:
    - genanki Model field definitions (fields=[ {... 'name': 'Noun'} ... ])
    - Dict entries like {'name': 'Noun'} used for UI/field naming
    """
    # Remove entire fields=[ ... ] blocks (non-greedy, dot matches newlines)
    text = re.sub(r"fields\s*=\s*\[(?:.|\n)*?\]", "", text, flags=re.IGNORECASE)
    # Neutralize simple dict name entries
    text = re.sub(r"\{\s*(['\"])name\1\s*:\s*(['\"]).*?\2\s*\}", "{}", text)
    return text


def test_no_hardcoded_word_type_literals_in_scripts():
    offenders = []
    for py in SCRIPTS_DIR.glob("*.py"):
        if not file_should_be_scanned(py):
            continue
        raw = py.read_text(encoding="utf-8")
        text = strip_allowed_contexts(raw)
        for literal in WORD_TYPE_LITERALS:
            if f'"{literal}"' in text or f"'{literal}'" in text:
                offenders.append((py, literal))

    assert not offenders, (
        "Found hardcoded word type string literals in scripts (must use WordType enum):\n"
        + "\n".join(f"- {p.name}: {lit}" for p, lit in offenders)
    )
