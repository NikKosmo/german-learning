# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

**Multi-project workspace:** This project is part of a larger workspace. If `../AGENTS.md` exists, **you MUST read it before proceeding** — it contains cross-project standards and shared rules (`common_rules/`).

## Repository Context

German language learning materials for a **Russian native speaker** targeting B2 certification, currently preparing for telc B1 exam (Feb-Mar 2026).

**Key context for AI assistance:**
- **Native language:** Russian - all translations and explanations should reference Russian when helpful
- **Current level:** A2 → B1 transition
- **Focus:** telc exam format (emails 80-100 words, specific grammar patterns)
- **Critical B1 gaps:** Konjunktiv II (30%), Prepositional pronouns (25%), Perfekt word order (20%), Modal verbs (15%)

**Test performance:**
- A1: 87% (strong foundation)
- A2: 68% (ready for B1)
- B1: 43% (specific gaps identified, not general weakness)

## Commands

### Flashcard Generation Workflow

See `flashcards/WORKFLOW.md` for the complete 7-step card generation process.

**Quick reference:**
```bash
# Add words via automatic Wiktionary classification + lemmatization
# (NDJSON records on stdout, human-readable progress on stderr)
python3 flashcards/scripts/add_words.py --words "Lieb Hinausgegangen bearbeiten"

# Update word tracking status
python3 flashcards/scripts/update_word_tracking.py

# Insert new cards into source markdown
python3 flashcards/scripts/insert_cards.py

# Generate .apkg deck from markdown
python3 flashcards/scripts/generate_deck_from_md.py
```

**Dependencies:**
```bash
# Always install into the project venv — never globally
source .venv/bin/activate
pip install -r requirements.txt
```

### Deck Validation and Analysis

```bash
# Unpack .apkg for analysis
python3 flashcards/scripts/unpack_deck.py flashcards/german_vocabulary_b1.apkg

# Validate deck against source markdown
python3 flashcards/scripts/validate_deck.py flashcards/german_vocabulary_b1.apkg flashcards/german_vocabulary_b1.md
```

## Grammar Priority System

Based on B1 test performance gaps. When generating materials or explanations, prioritize in this order:

1. **Konjunktiv II (30% priority)** - All würde-form questions failed in B1 test
   - Conditional sentences, polite requests
   - würde + infinitive constructions

2. **Prepositions (25% priority)** - Prepositional pronoun confusion
   - damit, darauf, wofür, daran, worauf
   - Distinction between da-/wo-compounds

3. **Perfekt (20% priority)** - Word order in complex sentences
   - Partizip II placement
   - Sentences with modal verbs + Perfekt

4. **Modal verbs (15% priority)** - Meaning distinctions
   - nicht dürfen vs nicht müssen
   - müssen vs sollen

5. **Adjective declension (10% priority)** - Endings by case/gender

## File Organization

**Key workflow files:**
- `flashcards/WORKFLOW.md` - Complete card generation process (7 steps)
- `flashcards/CARD_CREATION_RULES.md` - Card formatting standards
- `flashcards/word_tracking.md` - Word status tracking

**Study resources:**
- `resources/voice_language_practice_guide.md` - AI voice conversation setup (EN)
- `resources/voice_language_practice_guide_ru.md` - AI voice conversation setup (RU)
- `resources/das_leben_book_analysis.md` - Textbook chapter-by-chapter analysis mapped to exam gaps
- `study_plan/` - Personal study plans (gitignored)

**Project tracking:**
- `TODO.md` - Current tasks and priorities
- `SESSION_LOG.md` - Development history
- `README.md` - Public repository overview

**Vocabulary:**
- `vocabulary/cleaned_german_words.md` - Master list (800+ words)
- `vocabulary/by_level/` - A1, A2, B1 organized
- `vocabulary/by_topic/` - Thematic groups
- `vocabulary/problem_words.md` - Frequently forgotten

**Grammar directories:**
- `grammar/konjunktiv_ii/` - TOP PRIORITY
- `grammar/prepositions/`
- `grammar/perfekt/`
- `grammar/modal_verbs/`
- `grammar/adjective_declension/`

**Audio resources:**
- `audio/words_from_duolingo/` - 1,189 pronunciation files (gitignored)
- `audio/words_from_duolingo/learned_lexemes.csv` - Tracking data

**Practice materials:**
- `writing/exercises/` - telc format practice (80-100 word emails)
- `writing/corrections/` - Corrected with learning notes
- `tests/practice_exams/` - Full telc B1 format tests

## Flashcard Best Practices

When creating new cards or generating flashcard data:

1. **Always include articles** - "der Mann" not "Mann"
2. **Color-code by gender** - Use `.gender-m/f/n` CSS classes
3. **Provide context** - Example sentences, not isolated words
4. **Russian translations** - Use Cyrillic, include in parentheses after German
5. **Grammatical notes** - Explain case, gender, usage in Russian
6. **Mix card types** - Combine reverse and cloze for better retention
7. **Include plurals** - Essential for German nouns

## Current Test Performance Context

When suggesting study materials or exercises:

**Critical B1 failures (from practice test):**
- Konjunktiv II: 0% (all questions wrong)
- Prepositional pronouns: damit/daran/darauf/wofür confusion
- Perfekt word order: Partizip II placement in complex sentences
- Modal verbs: nicht dürfen vs nicht müssen distinction

**Target:** 75%+ on practice tests by December 2025.

**Study plan reference:** See `study_plan/das_leben_study_plan.md` for detailed 4-week plan and `resources/das_leben_book_analysis.md` for complete chapter analysis.

## Gotchas

*(Ported 2026-08-09 from the assistant's rule corpus during the LifeOS migration.)*

- **Cloze cards on closed-class forms need a hint or they are unanswerable.** For pronouns,
  articles and declension endings, a bare `{{c1::x}}` hides an answer that many candidates fit
  — `Das ist ___ Vater.` accepts all seven possessives — so the learner "fails" a card for
  giving a different perfectly-correct form. The German Pronouns deck shipped 181 cards this
  way and the first test session exposed it. Use `{{c1::answer::hint}}`, which renders the
  hint inside the blank: put the Russian lemma or owner there (`{{c1::mein::мой}}`,
  `{{c1::dich::тебя}}`) and let the sentence frame supply case and gender so the ending still
  has to be derived.

- **AnkiConnect `setSpecificValueOfCard` silently ignores string values on numeric fields.**
  `due`, `queue`, `type`, `ivl`, `factor` must be passed as `int`. A `str` returns
  `{'result': [True], 'error': None}` and changes nothing. Cost a wrong report on the
  irregular-verbs deck: 123 cards "reordered" to 1..123 while the real due values stayed
  random. Always verify with `cardsInfo` afterwards — this API actively lies.

- **Numerals are intentionally out of scope.** Do not add `Numerale`/`Numeral` to
  `POS_TEMPLATE_MAP` and do not write tests for `eins`, `zwei`, `erste` and friends, even when
  their Wiktionary pages have technically-recoverable redirect behaviour. Surface a numeral
  edge case for awareness; don't auto-fix it.

- **Never purge-and-replace a deck under study.** Update only the notes that change, in place,
  via `updateNoteFields` on specific note IDs — `deleteNotes` + `addNotes` destroys
  spaced-repetition scheduling and review history for every card, including the ones you
  weren't touching.

---

**Last Updated:** 2026-08-09
**Note:** Follow `common_rules/naming_conventions.md` for file/directory naming (snake_case standard).
