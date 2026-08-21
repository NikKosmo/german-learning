#!/usr/bin/env python3
"""
Add new words to the German vocabulary pipeline.

This version classifies each input word via de.wiktionary.org, resolves lemmas,
generates audio for the resolved lemma, then writes rows to word_tracking.md in
one atomic batch.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "audio" / "generated_audio" / "scripts"))

import paths
from flashcards.scripts.word_types import WordType

WORD_TRACKING_FILE = Path(os.environ.get("ADD_WORDS_TRACKING_FILE", str(paths.WORD_TRACKING_FILE)))
AUDIO_SCRIPTS_DIR = Path(
    os.environ.get(
        "ADD_WORDS_AUDIO_SCRIPTS_DIR",
        str(PROJECT_ROOT / "audio" / "generated_audio" / "scripts"),
    )
)
AUDIO_OUTPUT_DIR = Path(os.environ.get("ADD_WORDS_AUDIO_OUTPUT_DIR", str(paths.AUDIO_GENERATED)))
DEFAULT_TIMEOUT_SECONDS = 10.0
WIKTIONARY_BASE_URL = os.environ.get(
    "ADD_WORDS_WIKTIONARY_BASE_URL",
    "https://de.wiktionary.org/w/api.php",
)
WIKTIONARY_USER_AGENT = os.environ.get(
    "ADD_WORDS_USER_AGENT",
    "german-flashcards/1.0 (https://github.com/NikKosmo/german-learning)",
)

LOGGER = logging.getLogger(__name__)

POS_TEMPLATE_MAP = {
    "substantiv": WordType.NOUN.value,
    "noun": WordType.NOUN.value,
    "verb": WordType.VERB.value,
    "hilfsverb": WordType.VERB.value,
    "modalverb": WordType.VERB.value,
    "adjektiv": WordType.ADJECTIVE.value,
    "adverb": WordType.ADVERB.value,
    "lokaladverb": WordType.ADVERB.value,
    "temporaladverb": WordType.ADVERB.value,
    "modaladverb": WordType.ADVERB.value,
    "konjunktionaladverb": WordType.ADVERB.value,
    "pronominaladverb": WordType.ADVERB.value,
    "präposition": WordType.PREPOSITION.value,
    "praeposition": WordType.PREPOSITION.value,
    "konjunktion": WordType.CONJUNCTION.value,
    "artikel": WordType.ARTICLE.value,
    "partikel": WordType.PARTICLE.value,
    "pronomen": WordType.PRONOUN.value,
    "personalpronomen": WordType.PRONOUN.value,
    "indefinitpronomen": WordType.PRONOUN.value,
    "demonstrativpronomen": WordType.PRONOUN.value,
    "reflexivpronomen": WordType.PRONOUN.value,
    "relativpronomen": WordType.PRONOUN.value,
    "possessivpronomen": WordType.POSSESSIVE.value,
    "fragepronomen": WordType.QUESTION_WORD.value,
    "interrogativpronomen": WordType.QUESTION_WORD.value,
    "frageadverb": WordType.QUESTION_WORD.value,
    "interrogativadverb": WordType.QUESTION_WORD.value,
}

WORDTYPE_ORDER = [word_type.value for word_type in WordType]
COMPOUND_TYPE_MAP = {
    frozenset(compound.value.split("/")): compound.value
    for compound in WordType
    if "/" in compound.value
}

FAILURE_PRIORITY = {
    "no Wiktionary entry": 1,
    "no German section": 2,
    "no supported part of speech": 3,
}

# When multiple inflected sections each carry a Grundformverweis, lower index wins.
INFLECTED_GRUNDFORM_PRIORITY = [
    "deklinierte form",
    "konjugierte form",
    "partizip ii",
    "partizip i",
    "komparativ",
    "superlativ",
]

# A "strong" inflected Wortart always wins, even alongside a lemma-style POS.
STRONG_INFLECTED_WORTARTEN_CASEFOLD = frozenset({"komparativ", "superlativ"})

# A "weak" inflected Wortart only wins when no lemma-style POS coexists on the
# same page. Real Wiktionary pages combining Adjektiv + Partizip II are
# ambiguous — verb participles (gemacht -> machen) and true derived adjectives
# (betrunken, bekannt) share this shape and no Wortart-level signal distinguishes
# them. Keeping the adjective is the chosen tradeoff; misclassifications are
# corrected manually in word_tracking.md.
WEAK_INFLECTED_WORTARTEN_CASEFOLD = frozenset(
    {"konjugierte form", "deklinierte form", "partizip i", "partizip ii"}
)

SPRACHE_TEMPLATE_TITLE = "Sprache"
WORTART_TEMPLATE_TITLE = "Wortart"
GRUNDFORMVERWEIS_PREFIX = "Grundformverweis"
GERMAN_LANGUAGE_NAME = "Deutsch"


class LookupErrorResult(Exception):
    """Internal exception for lookup failures."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CLIError(Exception):
    """Fatal CLI or initialization error."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class PosSection:
    """One Wortart subsection within the Deutsch language section of a Wiktionary page.

    Wortart is the raw POS string from {{Wortart|X|Deutsch}}. Grundformverweis,
    if present, is the canonical lemma target from a sibling
    {{Grundformverweis ...|X}} template scoped to THIS subsection only.
    """

    wortart: str
    grundformverweis: str | None

    @property
    def wortart_cf(self) -> str:
        return self.wortart.casefold()

    @property
    def is_strong_inflected(self) -> bool:
        return self.wortart_cf in STRONG_INFLECTED_WORTARTEN_CASEFOLD

    @property
    def is_weak_inflected(self) -> bool:
        return self.wortart_cf in WEAK_INFLECTED_WORTARTEN_CASEFOLD

    @property
    def mapped_type(self) -> str | None:
        return POS_TEMPLATE_MAP.get(self.wortart_cf)


@dataclass(frozen=True)
class LookupCandidate:
    variant: str
    lemma: str
    supported_types: tuple[str, ...]
    is_inflected: bool = False


@dataclass(frozen=True)
class BatchRecord:
    input_word: str
    lemma: str
    word_type: str | None
    status: str
    audio: str | None
    error: str | None
    tracking_status: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "input": self.input_word,
                "lemma": self.lemma,
                "type": self.word_type,
                "status": self.status,
                "audio": self.audio,
                "error": self.error,
                "tracking_status": self.tracking_status,
            },
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class StagedRow:
    word: str
    status: str
    audio_filename: str
    word_type: str

    def to_markdown_row(self) -> str:
        return (
            f"| {self.word} | {self.status} | ✅ {self.audio_filename} | — | "
            f"{self.word_type} | — | — |"
        )


def normalize_lemma(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def toggle_first_char_case(value: str) -> str:
    if not value:
        return value
    first = value[0]
    toggled = first.lower() if first.isupper() else first.upper()
    return toggled + value[1:]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add words to German vocabulary tracking with Wiktionary classification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --words "Lieb Hinausgegangen bearbeiten"
  %(prog)s --file words.txt

Output: NDJSON records on stdout (one per resolved (input, POS) pair),
human-readable progress on stderr.
        """,
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--words", help="Space-separated words to add")
    input_group.add_argument("--file", type=Path, help="File with one word per line")
    parser.add_argument(
        "--wiktionary-timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-request timeout in seconds for Wiktionary lookups (default: 10)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to stderr",
    )
    return parser.parse_args(argv)


def configure_logging(debug_enabled: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug_enabled else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )


def collect_words(args: argparse.Namespace) -> list[str]:
    if args.words:
        words = [word.strip() for word in args.words.split() if word.strip()]
    else:
        lines = args.file.read_text(encoding="utf-8").splitlines()
        words = [line.strip() for line in lines if line.strip()]

    if not words:
        raise CLIError("No words to process.")
    return words


def fetch_parse_payload(word: str, timeout: float) -> dict[str, Any]:
    """Fetch a MediaWiki action=parse response with prop=parsetree (structured XML)."""
    params = urlencode(
        {
            "action": "parse",
            "page": word,
            "prop": "parsetree",
            "format": "json",
            "formatversion": 2,
        }
    )
    request = Request(
        f"{WIKTIONARY_BASE_URL}?{params}",
        headers={"User-Agent": WIKTIONARY_USER_AGENT},
    )

    LOGGER.debug("Wiktionary lookup word=%s variant=%s", word, word)
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8")
        LOGGER.debug("Wiktionary response word=%s status=%s", word, status)
        return json.loads(body)
    except HTTPError as exc:
        LOGGER.debug("Wiktionary HTTP error word=%s status=%s", word, exc.code)
        if exc.code == 404:
            raise LookupErrorResult("no Wiktionary entry") from exc
        raise LookupErrorResult(f"Wiktionary unreachable: HTTP {exc.code}") from exc
    except URLError as exc:
        raise LookupErrorResult(f"Wiktionary unreachable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LookupErrorResult("Wiktionary unreachable: timeout") from exc


def _validate_parse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "error" in payload:
        if payload["error"].get("code") == "missingtitle":
            raise LookupErrorResult("no Wiktionary entry")
        raise LookupErrorResult(payload["error"].get("info", "Wiktionary parse error"))

    parse = payload.get("parse")
    if not isinstance(parse, dict):
        raise LookupErrorResult("Wiktionary parse error")
    return parse


def _extract_page_title(parse_block: dict[str, Any]) -> str:
    title = parse_block.get("title")
    if not isinstance(title, str) or not title:
        raise LookupErrorResult("Wiktionary parse error")
    return title


def _extract_parsetree_xml(parse_block: dict[str, Any]) -> str:
    parsetree = parse_block.get("parsetree")
    if isinstance(parsetree, dict):
        parsetree = parsetree.get("*")  # legacy formatversion=1 shape
    if not isinstance(parsetree, str) or not parsetree:
        raise LookupErrorResult("Wiktionary parse error")
    return parsetree


def _template_title(elem: ET.Element) -> str | None:
    title = elem.find("title")
    if title is None or title.text is None:
        return None
    return title.text.strip()


def _first_part_value(elem: ET.Element) -> str | None:
    parts = elem.findall("part")
    if not parts:
        return None
    value = parts[0].find("value")
    if value is None or value.text is None:
        return None
    return value.text.strip()


def _h_contains_sprache(h_elem: ET.Element, language: str) -> bool:
    """True iff the h element contains {{Sprache|<language>}}."""
    for tmpl in h_elem.iter("template"):
        if _template_title(tmpl) != SPRACHE_TEMPLATE_TITLE:
            continue
        if _first_part_value(tmpl) == language:
            return True
    return False


def _h_extract_wortarten(h_elem: ET.Element) -> list[str]:
    """Return every {{Wortart|X|Deutsch}}'s X from the h element, in document order.

    Real de.wiktionary German headings often pack multiple POS into a single
    h3 (`### Adjektiv, Adverb` on `schal`, `tageweise`, `fraglos`); each gets
    its own {{Wortart}} template in the parsetree.
    """
    wortarten: list[str] = []
    for tmpl in h_elem.iter("template"):
        if _template_title(tmpl) != WORTART_TEMPLATE_TITLE:
            continue
        value = _first_part_value(tmpl)
        if value:
            wortarten.append(value)
    return wortarten


def _find_grundformverweis(elem: ET.Element) -> str | None:
    """Return the lemma target from the first {{Grundformverweis ...|X}} in elem (or its descendants)."""
    for tmpl in elem.iter("template"):
        title = _template_title(tmpl)
        if title is None or not title.startswith(GRUNDFORMVERWEIS_PREFIX):
            continue
        value = _first_part_value(tmpl)
        if value:
            # Grundformverweis values can be `lemma#Section|displayed`; keep only the lemma title.
            value = value.split("#", 1)[0].split("|", 1)[0].strip()
            if value:
                return unicodedata.normalize("NFC", value)
    return None


def extract_pos_sections(parsetree_xml: str) -> list[PosSection]:
    """Walk the parsetree XML; return one PosSection per Wortart h3 inside the Deutsch section."""
    try:
        root = ET.fromstring(parsetree_xml)
    except ET.ParseError as exc:
        raise LookupErrorResult(f"Wiktionary parse error: {exc}") from exc

    children = list(root)

    # Find the Deutsch language h2.
    deutsch_start: int | None = None
    for index, child in enumerate(children):
        if (
            child.tag == "h"
            and child.get("level") == "2"
            and _h_contains_sprache(child, GERMAN_LANGUAGE_NAME)
        ):
            deutsch_start = index
            break
    if deutsch_start is None:
        raise LookupErrorResult("no German section")

    # Bound the section at the next h2 (or end of page).
    deutsch_end = len(children)
    for index in range(deutsch_start + 1, len(children)):
        child = children[index]
        if child.tag == "h" and child.get("level") == "2":
            deutsch_end = index
            break

    sections: list[PosSection] = []
    current_wortarten: list[str] = []
    current_grundform: str | None = None

    def flush() -> None:
        nonlocal current_wortarten, current_grundform
        # An h3 with multiple {{Wortart}} templates (e.g. `### Adjektiv, Adverb`
        # on `schal`, `tageweise`, `fraglos`) becomes one PosSection per POS,
        # each sharing the same scoped Grundformverweis.
        for wortart in current_wortarten:
            sections.append(PosSection(wortart=wortart, grundformverweis=current_grundform))
        current_wortarten = []
        current_grundform = None

    for child in children[deutsch_start + 1 : deutsch_end]:
        if child.tag == "h" and child.get("level") == "3":
            flush()
            current_wortarten = _h_extract_wortarten(child)
        elif current_wortarten and current_grundform is None:
            gf = _find_grundformverweis(child)
            if gf:
                current_grundform = gf
    flush()

    return sections


def choose_more_specific_failure(current: str, candidate: str) -> str:
    current_priority = FAILURE_PRIORITY.get(current, 0)
    candidate_priority = FAILURE_PRIORITY.get(candidate, 0)
    if candidate_priority >= current_priority:
        return candidate
    return current


def _grundformverweis_priority(wortart_cf: str) -> int:
    try:
        return INFLECTED_GRUNDFORM_PRIORITY.index(wortart_cf)
    except ValueError:
        return len(INFLECTED_GRUNDFORM_PRIORITY)


def parse_lookup_candidate(variant: str, payload: dict[str, Any]) -> LookupCandidate:
    parse_block = _validate_parse_payload(payload)
    page_title = _extract_page_title(parse_block)
    parsetree_xml = _extract_parsetree_xml(parse_block)
    sections = extract_pos_sections(parsetree_xml)

    lemma_sections = [s for s in sections if s.mapped_type is not None]
    has_strong = any(s.is_strong_inflected for s in sections)
    has_weak = any(s.is_weak_inflected for s in sections)
    # Strong markers always trigger inflected handling. Weak markers do so only
    # when no lemma-style POS section coexists on the page (homonym pages like
    # `lieb` keep their lemma POS).
    is_inflected = has_strong or (has_weak and not lemma_sections)

    if is_inflected:
        # Per-section Grundformverweis is authoritative. When multiple inflected
        # sections each carry a redirect (e.g. `bessere`: Konj->bessern AND
        # Dekl->gut), pick by INFLECTED_GRUNDFORM_PRIORITY.
        inflected_with_redirect = [
            s
            for s in sections
            if (s.is_strong_inflected or s.is_weak_inflected) and s.grundformverweis
        ]
        if inflected_with_redirect:
            inflected_with_redirect.sort(key=lambda s: _grundformverweis_priority(s.wortart_cf))
            lemma = inflected_with_redirect[0].grundformverweis or ""
        else:
            lemma = unicodedata.normalize("NFC", page_title.strip())
        supported_types: tuple[str, ...] = ()
    else:
        types: list[str] = []
        for section in lemma_sections:
            mapped = section.mapped_type
            if mapped and mapped not in types:
                types.append(mapped)
        supported_types = tuple(sorted(types, key=WORDTYPE_ORDER.index))
        lemma = unicodedata.normalize("NFC", page_title.strip())

    LOGGER.debug(
        "Resolved variant=%s lemma=%s supported_types=%s is_inflected=%s sections=%s",
        variant,
        lemma,
        list(supported_types),
        is_inflected,
        [(s.wortart, s.grundformverweis) for s in sections],
    )
    return LookupCandidate(
        variant=variant,
        lemma=lemma,
        supported_types=supported_types,
        is_inflected=is_inflected,
    )


def resolve_lookup_candidate(word: str, timeout: float) -> LookupCandidate:
    variants = [word]
    toggled = toggle_first_char_case(word)
    if toggled != word:
        variants.append(toggled)

    fallback_failure = "no Wiktionary entry"
    for variant in variants:
        try:
            payload = fetch_parse_payload(variant, timeout)
            candidate = parse_lookup_candidate(variant, payload)
        except LookupErrorResult as exc:
            LOGGER.debug("Lookup failed variant=%s reason=%s", variant, exc.message)
            if exc.message.startswith("Wiktionary unreachable"):
                raise
            fallback_failure = choose_more_specific_failure(fallback_failure, exc.message)
            continue

        # Once a variant resolves, do NOT fall through to the case-toggled variant
        # (would pick a different lexical item).
        resolved = _resolve_from_candidate(candidate, variant, timeout)
        if resolved is not None:
            return resolved

        fallback_failure = choose_more_specific_failure(
            fallback_failure, "no supported part of speech"
        )
        break

    raise LookupErrorResult(fallback_failure)


def _resolve_from_candidate(
    candidate: LookupCandidate, variant: str, timeout: float
) -> LookupCandidate | None:
    """Return a fully resolved LookupCandidate, or None if no usable lemma+POS."""
    if candidate.is_inflected and candidate.lemma and candidate.lemma != variant:
        try:
            lemma_payload = fetch_parse_payload(candidate.lemma, timeout)
            lemma_candidate = parse_lookup_candidate(candidate.lemma, lemma_payload)
        except LookupErrorResult as exc:
            LOGGER.debug(
                "Lemma re-lookup failed variant=%s lemma=%s reason=%s",
                variant,
                candidate.lemma,
                exc.message,
            )
            if exc.message.startswith("Wiktionary unreachable"):
                raise
            return None
        # Guard against multi-hop chains: a lemma page should not itself be inflected.
        if lemma_candidate.supported_types and not lemma_candidate.is_inflected:
            return lemma_candidate
        return None
    if candidate.supported_types:
        return candidate
    return None


def reduce_word_types(supported_types: tuple[str, ...]) -> list[str]:
    compound = COMPOUND_TYPE_MAP.get(frozenset(supported_types))
    if compound:
        return [compound]
    return list(sorted(supported_types, key=WORDTYPE_ORDER.index))


def generate_audio(lemma: str) -> tuple[bool, str | None, str]:
    from generate_audio import AudioGenerator

    try:
        generator = AudioGenerator(
            model_dir=AUDIO_SCRIPTS_DIR,
            output_dir=AUDIO_OUTPUT_DIR,
        )
    except FileNotFoundError as exc:
        return False, None, f"Generator init failed: {exc}"

    success, message = generator.process_word(lemma)
    if not success:
        return False, None, message

    filename = f"{generator.capitalize_word(lemma).replace(' ', '_')}.wav"
    return True, filename, message


def find_tracking_table_bounds(lines: list[str]) -> tuple[int, int]:
    header_index = -1
    divider_index = -1
    for index, line in enumerate(lines):
        if line.startswith("| Word | Status |"):
            header_index = index
            divider_index = index + 1
            break
    if header_index == -1 or divider_index >= len(lines):
        raise CLIError(f"Could not find word table in {WORD_TRACKING_FILE}")

    body_end = divider_index + 1
    while body_end < len(lines) and lines[body_end].startswith("|"):
        body_end += 1
    return divider_index + 1, body_end


def read_existing_tracking_keys(content: str) -> dict[tuple[str, str], str]:
    """Existing tracking rows, (normalized lemma, type) -> status.

    The status matters to the caller of this script: `skipped_dup` says a row exists, which is
    not the same as a card existing. A row still `pending` means the word was captured and never
    carded, so its capture bullet has not done its job yet.
    """
    lines = content.splitlines()
    body_start, body_end = find_tracking_table_bounds(lines)
    keys: dict[tuple[str, str], str] = {}
    for line in lines[body_start:body_end]:
        if not line.startswith("|") or line.startswith("|---") or "| Word | Status |" in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 6:
            continue
        lemma = parts[1]
        word_type = parts[5]
        if lemma and word_type in WordType.all_values():
            keys[(normalize_lemma(lemma), word_type)] = parts[2]
    return keys


def apply_staged_rows(content: str, rows: list[StagedRow]) -> str:
    if not rows:
        return content

    lines = content.splitlines()
    _, body_end = find_tracking_table_bounds(lines)
    row_lines = [row.to_markdown_row() for row in rows]
    new_lines = lines[:body_end] + row_lines + lines[body_end:]
    return "\n".join(new_lines) + "\n"


def atomic_write_text(path: Path, content: str) -> None:
    temp_path: Path | None = None
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    try:
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def plan_batch(
    words: list[str],
    timeout: float,
    tracking_content: str,
    console,
) -> tuple[list[StagedRow], list[BatchRecord]]:
    seen_keys = read_existing_tracking_keys(tracking_content)
    staged_rows: list[StagedRow] = []
    records: list[BatchRecord] = []

    def emit_per_type(
        word: str,
        lemma: str,
        types: list[str],
        status: str,
        audio: str | None,
        error: str | None,
        lemma_key: str | None = None,
    ) -> None:
        for word_type in types:
            records.append(
                BatchRecord(
                    input_word=word,
                    lemma=lemma,
                    word_type=word_type,
                    status=status,
                    audio=audio,
                    error=error,
                    tracking_status=(
                        seen_keys.get((lemma_key, word_type)) if lemma_key is not None else None
                    ),
                )
            )

    for word in words:
        console(f"Resolving {word}")
        nfc_word = unicodedata.normalize("NFC", word)
        try:
            candidate = resolve_lookup_candidate(word, timeout)
        except LookupErrorResult as exc:
            records.append(BatchRecord(word, nfc_word, None, "failed", None, exc.message))
            continue
        except Exception as exc:
            LOGGER.exception("Unexpected error while resolving %s", word)
            records.append(
                BatchRecord(word, nfc_word, None, "failed", None, f"unexpected error: {exc}")
            )
            continue

        resolved_types = reduce_word_types(candidate.supported_types)
        lemma_key = normalize_lemma(candidate.lemma)
        new_types = [t for t in resolved_types if (lemma_key, t) not in seen_keys]

        if not new_types:
            emit_per_type(
                word,
                candidate.lemma,
                resolved_types,
                "skipped_dup",
                None,
                None,
                lemma_key=lemma_key,
            )
            continue

        success, audio_filename, audio_message = generate_audio(candidate.lemma)
        if not success or not audio_filename:
            emit_per_type(word, candidate.lemma, resolved_types, "failed", None, audio_message)
            continue

        console(f"Audio ready for {candidate.lemma}: {audio_message}")
        for word_type in resolved_types:
            key = (lemma_key, word_type)
            if key in seen_keys:
                records.append(
                    BatchRecord(
                        word,
                        candidate.lemma,
                        word_type,
                        "skipped_dup",
                        None,
                        None,
                        tracking_status=seen_keys.get(key),
                    )
                )
                continue
            staged_rows.append(
                StagedRow(
                    word=candidate.lemma,
                    status="pending",
                    audio_filename=audio_filename,
                    word_type=word_type,
                )
            )
            seen_keys[key] = "pending"
            records.append(
                BatchRecord(word, candidate.lemma, word_type, "added", audio_filename, None)
            )

    return staged_rows, records


def emit_json_records(records: list[BatchRecord]) -> None:
    for record in records:
        print(record.to_json())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.debug)

    try:
        words = collect_words(args)
        tracking_content = WORD_TRACKING_FILE.read_text(encoding="utf-8")
    except CLIError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Failed to read tracking file: {exc}", file=sys.stderr)
        return 1
    except LookupErrorResult as exc:
        print(exc.message, file=sys.stderr)
        return 1

    def console(message: str) -> None:
        print(message, file=sys.stderr)

    staged_rows, records = plan_batch(words, args.wiktionary_timeout, tracking_content, console)
    new_content = apply_staged_rows(tracking_content, staged_rows)
    atomic_write_text(WORD_TRACKING_FILE, new_content)

    emit_json_records(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
