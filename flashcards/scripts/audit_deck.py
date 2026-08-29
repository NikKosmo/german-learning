#!/usr/bin/env python3
"""Audit the vocab deck against its markdown source and word_tracking.md.

Written after the 2026-08-29 cleanup, which found 126 Anki notes with no row in
german_vocabulary_b1.md. Cause: a June drip run's markdown rows were committed
only on a branch that was never merged, while Anki -- a live database with no
branches -- kept the cards. Nothing noticed for ten weeks, because nothing
counted. This script counts.

Checks:
  1. every live Anki note has a row in the deck markdown   (no orphan notes)
  2. every markdown row has a live Anki note               (no phantom rows)
  3. the markdown header counts match its own content
  4. every word_tracking row's Status agrees with the markdown

Exits non-zero on any mismatch, so it works as a pre-commit or cron guard.
Requires Anki running with AnkiConnect on :8765; skip the Anki-side checks with
--offline.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MD = REPO / "flashcards" / "german_vocabulary_b1.md"
TRACKING = REPO / "flashcards" / "word_tracking.md"
VOCAB_DECK = "Deutsch B1::German Vocabulary - B1"
ROW = re.compile(r"^\| ([0-9a-f]{8}) \|")


def anki(action, **params):
    r = subprocess.run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            "http://localhost:8765",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"action": action, "version": 6, "params": params}),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not r.stdout:
        sys.exit("AnkiConnect unreachable on :8765 -- is Anki running? (--offline to skip)")
    d = json.loads(r.stdout)
    if d["error"]:
        sys.exit(f"AnkiConnect error on {action}: {d['error']}")
    return d["result"]


def deck_word(line):
    """The vocabulary word a deck row teaches. Matches the normalisation in
    update_word_tracking.read_words_in_deck() so the two agree by construction."""
    g = line.split("|")[5]
    g = g.replace("{{c1::", "").replace("{{c2::", "").replace("}}", "").strip()
    return g.split()[-1].lower() if g else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--offline", action="store_true", help="skip the checks that need a running Anki"
    )
    args = ap.parse_args()

    text = MD.read_text(encoding="utf-8")
    rows = {m.group(1): line for line in text.splitlines() if (m := ROW.match(line))}
    words = {deck_word(line) for line in rows.values()}
    fails = []

    print(f"deck markdown : {len(rows)} rows, {len(words)} unique words")

    # --- 3. header counts ---
    for label, actual in (("Total cards", len(rows)), ("Words", len(words))):
        m = re.search(rf"^- {label}: (\d+)$", text, re.M)
        if not m:
            fails.append(f"header: no '{label}' line")
        elif int(m.group(1)) != actual:
            fails.append(f"header: '{label}: {m.group(1)}' but content has {actual}")

    # --- 1 + 2. markdown vs collection ---
    if not args.offline:
        ids = anki("findNotes", query=f'deck:"{VOCAB_DECK}"')
        notes = []
        for i in range(0, len(ids), 200):
            notes += anki("notesInfo", notes=ids[i : i + 200])
        live = {n["fields"]["ID"]["value"] for n in notes if "ID" in n["fields"]}
        noid = [n["noteId"] for n in notes if "ID" not in n["fields"]]
        print(f"anki deck     : {len(notes)} notes ({len(live)} with an ID field)")
        if noid:
            fails.append(f"{len(noid)} Anki notes have no ID field: {noid[:5]}")
        orphans = live - set(rows)
        phantoms = set(rows) - live
        if orphans:
            fails.append(f"{len(orphans)} Anki notes with no markdown row: {sorted(orphans)[:8]}")
        if phantoms:
            fails.append(f"{len(phantoms)} markdown rows with no Anki note: {sorted(phantoms)[:8]}")

    # --- 4. tracking status vs markdown ---
    # Type-aware on purpose. update_word_tracking.py matches on (word, Word Type)
    # for homonym safety -- `recht` (Adjective/Adverb) is a different word from the
    # deck's `Recht` (Noun) and must stay pending. An audit that compared words
    # alone would report that forever as a defect. So this mirrors the script's
    # exact-string rule, and reports the case the script CANNOT see -- the same
    # word carrying disagreeing labels in the two files -- as its own category.
    types = {}
    for line in rows.values():
        types.setdefault(deck_word(line), set()).add(line.split("|")[3].strip())

    bad, disagree = [], []
    n_track = 0
    for line in TRACKING.read_text(encoding="utf-8").splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) < 8 or not p[1] or p[1] in ("Word", "------"):
            continue
        n_track += 1
        word, status, wtype = p[1].lower(), p[2], p[5]
        if status == "error":
            continue
        deck_types = types.get(word, set())
        exact = wtype in deck_types or (wtype in ("—", "") and word in words)
        if exact:
            if status != "in_deck":
                bad.append(f"{p[1]} ({wtype}): '{status}' but present in deck markdown")
            continue
        if status == "in_deck":
            bad.append(f"{p[1]} ({wtype}): 'in_deck' but absent from deck markdown")
            continue
        # not an exact type match: is it the same part of speech under a different label?
        mine = {x.strip() for x in wtype.split("/") if x.strip()}
        shared = [t for t in deck_types if mine & {x.strip() for x in t.split("/")}]
        if shared:
            disagree.append(f"{p[1]}: tracking '{wtype}' vs deck {sorted(shared)}")
    print(f"word_tracking : {n_track} rows")
    if bad:
        fails.append(f"{len(bad)} tracking status mismatches: {bad[:8]}")
    if disagree:
        fails.append(
            f"{len(disagree)} words whose Word Type disagrees between the two files "
            f"(see TODO.md, 2026-08-29): {disagree[:8]}"
        )

    print()
    if fails:
        for f in fails:
            print(f"FAIL  {f}")
        sys.exit(1)
    print("PASS  markdown, Anki collection and word_tracking agree")


if __name__ == "__main__":
    main()
