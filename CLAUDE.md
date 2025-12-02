# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Context

German language learning materials for a **Russian native speaker** targeting B2 certification, currently preparing for telc B1 exam (Feb-Mar 2026). Current level: A2 with specific B1 gaps identified.

**Key context for AI assistance:**
- All translations and explanations should reference Russian when helpful
- Focus on telc exam format (emails 80-100 words, specific grammar patterns)
- Current B1 test score: 43% with critical gaps in Konjunktiv II, prepositional pronouns, Perfekt word order, and modal verbs

## Commands

### Flashcard Generation

**Dependencies:**
```bash
pip install genanki
```

**Generate Anki decks:**
```bash
cd flashcards

# Basic vocabulary cards (reverse RU→DE + cloze)
python3 create_basic_cards.py
# Output: german_basic_10_words.apkg

# Noun cards with gender color-coding
python3 create_noun_cards.py
# Output: german_nouns_gender_practice.apkg
```

Generated `.apkg` files can be imported into Anki Desktop or AnkiMobile.

## Code Architecture

### Flashcard Generation System

Built with `genanki` library. Two main card types:

**1. Reverse Cards (Russian → German)**
- Front: Russian word/phrase
- Back: German translation with article, grammatical notes
- Used for: Active recall, production practice

**2. Cloze Deletion Cards**
- Format: `{{c1::word}}` syntax for fill-in-the-blank
- Includes: Context sentence, Russian translation, grammatical notes
- Used for: Context learning, natural usage patterns

### Card Models Structure

**Noun Card Model** (`create_noun_cards.py`):
```python
fields = ['Russian', 'Article', 'Noun', 'Plural', 'Gender', 'Example']
```

**Gender color-coding CSS classes:**
- `.gender-m` - Blue (#2196F3) for masculine (der)
- `.gender-f` - Pink (#E91E63) for feminine (die)
- `.gender-n` - Green (#4CAF50) for neuter (das)

**Essential patterns when creating cards:**
- Always include article with nouns (never just "Mann", always "der Mann")
- Include plural forms for nouns
- Provide example sentences with Russian translations in parentheses
- Add grammatical notes in Russian for cases, declensions

### Example Data Structure

```python
# Noun card
{
    'Russian': 'мужчина',
    'Article': 'der',
    'Noun': 'Mann',
    'Plural': 'die Männer',
    'Gender': 'm',
    'Example': 'Der Mann arbeitet im Büro. (Мужчина работает в офисе.)'
}

# Cloze card
{
    'Text': 'Ich sehe {{c1::den Mann}} im Park.',
    'Translation': 'Я вижу мужчину в парке.',
    'Notes': 'den Mann (masculine, Akkusativ)'
}
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

**Vocabulary:**
- `vocabulary/cleaned_german_words.md` - Master list (800+ words)
- `vocabulary/by-level/` - A1, A2, B1 organized
- `vocabulary/by-topic/` - Thematic groups
- `vocabulary/problem-words.md` - Frequently forgotten

**Grammar directories match priority order:**
- `grammar/konjunktiv-ii/` - TOP PRIORITY
- `grammar/prepositions/`
- `grammar/perfekt/`
- `grammar/modal-verbs/`
- `grammar/adjective-declension/`

**Audio resources:**
- `audio/words_from_duolinguo/` - 1,189 pronunciation files
- `audio/words_from_duolinguo/learned_lexemes.csv` - Tracking data

**Practice materials:**
- `writing/exercises/` - telc format practice (80-100 word emails)
- `writing/corrections/` - Corrected with learning notes
- `listening/deutsche-welle/` - B1 level content
- `tests/practice-exams/` - Full telc B1 format tests

## Flashcard Best Practices

When creating new flashcard generation scripts:

1. **Always include articles** - "der Mann" not "Mann"
2. **Color-code by gender** - Use `.gender-m/f/n` CSS classes
3. **Provide context** - Example sentences, not isolated words
4. **Russian translations** - Use Cyrillic, include in parentheses after German
5. **Grammatical notes** - Explain case, gender, usage in Russian
6. **Mix card types** - Combine reverse and cloze for better retention
7. **Include plurals** - Essential for German nouns

## Current Test Performance Context

When suggesting study materials or exercises:

- **A1 test:** 87% (strong foundation)
- **A2 test:** 68% (ready for B1)
- **B1 test:** 43% (specific gaps, not general weakness)

**Critical B1 failures:**
- Konjunktiv II: 0% (all questions wrong)
- Prepositional pronouns: damit/daran/darauf/wofür confusion
- Perfekt word order: Partizip II placement in complex sentences
- Modal verbs: nicht dürfen vs nicht müssen distinction

Target: 75%+ on practice tests by December 2025.
