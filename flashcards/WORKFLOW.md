# Flashcard Generation Workflow

**Purpose:** Complete end-to-end workflow for generating German-Russian flashcards using Claude + Gemini validation

**Version:** 1.2
**Last Updated:** 2025-12-20

---

## Required Files

| File | Purpose |
|------|---------|
| `flashcards/word_tracking.md` | Word status tracking (Steps 1, 7) |
| `flashcards/german_vocabulary_b1.md` | Deck source of truth |
| `flashcards/scripts/pending_cards.json` | Output target (Step 4) |
| `flashcards/scripts/word_types.py` | Word type enum (source of truth) |
| `flashcards/scripts/update_word_tracking.py` | Update tracking script |
| `flashcards/scripts/insert_cards.py` | Card insertion script |
| `flashcards/scripts/generate_deck_from_md.py` | Deck generation script |
| `audio/words_from_duolingo/` | Audio pronunciation files (1,189 MP3s) |
| `audio/generated_audio/` | TTS audio files (457 WAVs) |

⚠️ **STOP** if any required file above is not accessible. Report which file is missing before proceeding.

**Note:** All scripts follow the fail-fast principle - they will exit immediately with clear error messages if critical issues are detected (missing audio, invalid word types, file access errors, etc.).

---

## Input

- **Source:** `flashcards/word_tracking.md`
- **Format:** Markdown table with word status
- **Selection criteria:** Words with status `pending` and audio `✅`
- **Selection method:**
  - Random sampling (e.g., 4 from top, 3 from middle, 3 from bottom)
  - Direct specification by user
- **Typical batch size:** 10 words
- **Example:**
  ```
  | ein | pending | ✅ Ein.mp3 | — | Article | — |
  | eine | pending | ✅ Eine.mp3 | — | Article | — |
  | Mann | pending | ✅ Mann.mp3 | — | Noun | — |
  ```

---

## Output

- **Primary file:** `flashcards/scripts/pending_cards.json`
- **Format:** JSON array of card objects (overwrites existing)
- **Final products:**
  - Updated `german_vocabulary_b1.md` with new card rows
  - Generated `german_vocabulary_b1.apkg` deck file
  - Updated `word_tracking.md` with status `in_deck`

**Card schema:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| card_type | string | yes | "Reverse" or "Cloze" |
| word_type | string | yes | Must match `word_types.py` enum exactly |
| russian | string | yes | Russian translation |
| german | string | yes | German word (with article for nouns) |
| extra | string | yes | Plural/Perfekt/Comparison forms (or "—") |
| example_de | string | yes | German example sentence |
| example_ru | string | yes | Russian translation of example |
| notes | string | yes | Grammatical notes in Russian |
| audio | string | yes | Filename.mp3 or Filename.wav |

**Valid word_type values** (from `flashcards/scripts/word_types.py`):
- Single types: `Noun`, `Verb`, `Adjective`, `Adverb`, `Preposition`, `Conjunction`, `Article`, `Pronoun`, `Particle`, `Possessive`, `Question Word`
- Compound types: `Adjective/Adverb`, `Adverb/Particle`
- **Case-sensitive!** Must match exactly.

---

## Overview

This workflow uses **Claude to generate card data** (translations, examples, notes) and **Gemini to validate** quality. No LLM script needed - Claude works directly with the data files.

### Key Principle
**Claude generates, Gemini validates, scripts automate the insertion.**

---

## Steps

### Step 1: Update Word Tracking

```bash
cd flashcards/scripts
python3 update_word_tracking.py
```

**Purpose:** Refresh `word_tracking.md` with current deck status

**What it does:**
- Checks which words are in `german_vocabulary_b1.md`
- Updates status: `in_deck`, `pending`, `missing_audio`, `error`
- Verifies audio availability (✅ or ❌)
- Generates statistics

---

### Step 2: Claude Reads Pending Words

**File:** `flashcards/word_tracking.md`
**Task:** Identify N words with status `pending` and audio `✅`

**Recommended batch size:** 5-10 words for testing, 20-50 for production

---

### Step 3: Claude Generates & Validates Card Data (Per-Word)

**IMPORTANT: Gemini validation is REQUIRED for every word. Do not skip this step.**

For each word:

#### 3.1 Identify Word Type

**Supported types** (from `word_types.py` enum):
- **Noun** - has gender (der/die/das), plural form
- **Verb** - has infinitive, Perfekt form
- **Adjective** - has comparative/superlative
- **Adverb** - time/manner/place modifiers
- **Preposition** - has case governance (+ Dativ, etc.)
- **Article** - der, die, das, ein, eine, etc.
- **Conjunction** - und, aber, oder, weil, etc.
- **Particle** - ja, nein, doch, etc.
- **Pronoun** - ich, du, er, sie, es, etc.
- **Possessive** - mein, dein, sein, etc.
- **Question Word** - wer, was, wo, wann, etc.
- **Adjective/Adverb** - words functioning as both (compound type)
- **Adverb/Particle** - words functioning as both (compound type)

**Decision guide:**
- Starts with capital → likely noun
- Ends in -en → likely verb infinitive
- Ends in -ung, -heit, -keit → feminine noun
- Short function words → article/particle/conjunction

#### 3.2 Generate Card Data

Generate complete data based on word type. See [Card Data Standards](#card-data-standards) section below.

#### 3.3 Validate with Gemini (REQUIRED)

**This step is MANDATORY for all words. Always validate with Gemini before accepting card data.**

**Command format:**
```bash
gemini -p 'You are validating German vocabulary card data for a Russian native speaker learning German.

Word: [WORD]
Type: [TYPE]
Generated data:
{
  "russian": "...",
  "german": "...",
  "example_de": "...",
  "example_ru": "...",
  "notes": "...",
  "audio": "..."
}

Validate:
1. Russian translation is accurate
2. Grammatical forms are correct
3. Example sentences are natural German
4. Russian translations of examples are accurate
5. Grammatical notes are helpful and in Russian

IMPORTANT: Respond with ONLY valid JSON, no other text. Format:
{
  "valid": true,
  "issues": [],
  "suggestions": []
}

Or if invalid:
{
  "valid": false,
  "issues": ["issue 1", "issue 2"],
  "suggestions": ["suggestion 1"]
}'
```

#### 3.4 Handle Validation Feedback

**If valid (✅):**
- Add to pending cards collection
- Continue to next word

**If invalid (❌):**
- Read issues from Gemini
- Regenerate card data incorporating feedback
- Validate again (ONE retry only)
- If still invalid → Skip word, log to `failed_words.txt`

---

### Step 4: Claude Writes `pending_cards.json`

**File:** `flashcards/scripts/pending_cards.json`
**Format:**
```json
{
  "cards": [
    {
      "card_type": "Reverse",
      "word_type": "Noun",
      "russian": "стол",
      "german": "der Tisch",
      "extra": "die Tische",
      "example_de": "Der Tisch ist aus Holz.",
      "example_ru": "Стол сделан из дерева.",
      "notes": "Мужской род • Множественное число с -e окончанием",
      "audio": "Tisch.mp3"
    },
    {
      "card_type": "Cloze",
      "word_type": "Noun",
      "russian": "стол",
      "german": "{{c1::der}} Tisch",
      "extra": "die Tische",
      "example_de": "Der Tisch ist aus Holz.",
      "example_ru": "Стол сделан из дерева.",
      "notes": "Мужской род • тест на артикль",
      "audio": "Tisch.mp3"
    }
  ]
}
```

**IMPORTANT - Auto-expansion behavior:**
- `card_type: "Reverse"` → `insert_cards.py` automatically creates **2 cards**: "Reverse RU→DE" and "Reverse DE→RU"
- `card_type: "Cloze"` → stays as 1 card
- **For verbs/prepositions/adjectives:** Create 1 entry with `card_type: "Reverse"` (expands to 2 cards)
- **For nouns:** Create 2 entries: one "Reverse" (expands to 2 cards) + one "Cloze" (stays 1 card) = 3 total cards

**File is overwritten each time (not appended)**

**VERIFICATION (REQUIRED):** After writing, verify the file was updated correctly:

```bash
cd flashcards/scripts
head -20 pending_cards.json
```

**Check that:**
- File contains YOUR cards (not old content from previous session)
- Word names match what you just generated
- Audio filenames are correct
- All required fields are present

**Why this matters:**
- iCloud paths may have sync delays
- Write operations can silently fail
- Prevents inserting wrong/duplicate cards into deck

**If content is wrong:** Re-write the JSON file and verify again before proceeding to Step 5.

---

### Step 5: Insert Cards into Deck

```bash
cd flashcards/scripts
python3 insert_cards.py
```

**What it does:**
- Validates JSON structure
- Generates unique SHA-256 hash IDs (8 chars)
- Appends card rows to `german_vocabulary_b1.md`
- Updates deck metadata (card count, generation date)

**Output:** Cards added to MD file, ready for deck generation

---

### Step 6: Generate Anki .apkg File

```bash
cd flashcards/scripts
python3 generate_deck_from_md.py
```

**What it does:**
- Reads `german_vocabulary_b1.md`
- Creates Anki note models for each card type
- Generates `german_vocabulary_b1.apkg`
- Creates timestamped log file

**Output:** Ready to import into Anki Desktop or AnkiMobile

---

### Step 7: Update Word Tracking Status

```bash
cd flashcards/scripts
python3 update_word_tracking.py
```

**Purpose:** Mark newly added words as `in_deck`

**What it does:**
- Automatically detects words now in `german_vocabulary_b1.md`
- Updates their status from `pending` → `in_deck`
- Sets "Date Added" timestamp
- Updates statistics

---

## Validation

After completing the workflow, verify:

### File Verification
- [ ] `pending_cards.json` exists and contains YOUR cards (not old content)
- [ ] `german_vocabulary_b1.md` updated with new card rows
- [ ] `german_vocabulary_b1.apkg` generated successfully
- [ ] `word_tracking.md` shows processed words as `in_deck`

### Data Quality
- [ ] Card count matches expected: (nouns × 3) + (other words × 2)
- [ ] All required fields present in JSON (9 fields per card)
- [ ] Audio filenames match available files (check capitalization)
- [ ] No English text in cards (only German and Russian)
- [ ] All nouns include articles (der/die/das)
- [ ] Russian translations are in Cyrillic
- [ ] Example sentences are natural German (A2-B1 level)

### Gemini Validation (Mandatory)
- [ ] ALL words validated by Gemini before insertion
- [ ] No validation failures ignored
- [ ] All issues from Gemini addressed

**If validation fails:**
1. Report which check failed
2. Review the specific error in `pending_cards.json`
3. Fix data in `pending_cards.json` ONLY (do not modify other files - they are managed by scripts)
4. Re-validate before proceeding to Step 5

---

## Error Handling

| Error | Action |
|-------|--------|
| Required file not accessible | **STOP** - Report missing file, do not proceed |
| No pending words with audio | **STOP** - Add words to tracking or generate audio first |
| Gemini validation fails | Regenerate card data with fixes, retry ONCE, skip word if still fails |
| Gemini validation times out | Reduce batch size, retry session |
| `pending_cards.json` write fails | Verify iCloud sync status, retry write, verify with `head -20` |
| `pending_cards.json` has old content | Re-write file, verify again before Step 5 |
| Audio filename mismatch | **Verify** you copied filename exactly from `word_tracking.md` Audio column |
| `insert_cards.py` fails | Check JSON structure, verify all 9 required fields present |
| `generate_deck_from_md.py` fails | Script will report specific error (missing audio, invalid word_type, etc.) |
| Duplicate cards in deck | Word already `in_deck` - check tracking status before generating |

**General principle:** Fail fast and report clearly. Do not silently continue with defaults or assumptions.

---

## Card Data Standards

### General Rules (All Word Types)

1. **Russian translations must be accurate and natural**
   - Use Cyrillic script
   - Provide context in parentheses when needed
   - Example: "один (артикль/числительное)" for "ein"

2. **Example sentences must be:**
   - Natural, realistic German
   - A2-B1 level complexity (not too simple, not too complex)
   - Show the word in realistic context
   - Include Russian translation in parentheses

3. **Grammatical notes must be:**
   - Written in Russian (target learner is Russian native speaker)
   - Concise but informative
   - Highlight key grammar points
   - Use bullet points (•) for multiple points

4. **Audio files:**
   - `audio_checker.py` automatically finds available audio (MP3 or WAV)
   - Checks `generated_audio/` first (WAV), falls back to `words_from_duolingo/` (MP3)
   - Format: Capitalized word with umlauts (e.g., "Tisch.mp3", "Wissen.wav")
   - For compound words, use base word audio

---

### Noun Cards (3 cards per word)

**Data to generate:**
- `russian` - Russian translation
- `german` - Article + noun (e.g., "der Tisch")
- `extra` - Plural form (e.g., "die Tische")
- `example_de` - German sentence using the noun
- `example_ru` - Russian translation of example
- `notes` - Gender explanation, plural pattern in Russian
- `audio` - Filename.mp3

**Card types created:**
1. `card_type: "Reverse RU→DE"` (Russian → German)
2. `card_type: "Reverse DE→RU"` (German → Russian)
3. `card_type: "Cloze"` ({{c1::der/die/das}} Noun) - tests article/gender

**IMPORTANT:** Use `"Cloze"` exactly, NOT `"Cloze (Gender)"` or other variations

**Example:**
```json
{
  "card_type": "Reverse",
  "word_type": "Noun",
  "russian": "стол",
  "german": "der Tisch",
  "extra": "die Tische",
  "example_de": "Der Tisch ist aus Holz.",
  "example_ru": "Стол сделан из дерева.",
  "notes": "Мужской род • Множественное число с -e окончанием",
  "audio": "Tisch.mp3"
}
```

---

### Verb Cards (2 cards per word)

**Data to generate:**
- `russian` - Russian translation (infinitive)
- `german` - German infinitive
- `extra` - Perfekt form (hat/ist + Partizip II)
- `example_de` - German sentence with conjugated verb
- `example_ru` - Russian translation
- `notes` - Verb type (regular/irregular), Perfekt auxiliary in Russian
- `audio` - Filename.mp3

**Card types created:**
1. Reverse RU→DE
2. Reverse DE→RU

**Example:**
```json
{
  "card_type": "Reverse",
  "word_type": "Verb",
  "russian": "работать",
  "german": "arbeiten",
  "extra": "hat gearbeitet",
  "example_de": "Ich arbeite jeden Tag.",
  "example_ru": "Я работаю каждый день.",
  "notes": "Регулярный глагол • haben + Partizip II",
  "audio": "Arbeiten.mp3"
}
```

---

### Adjective Cards (2 cards per word)

**Data to generate:**
- `russian` - Russian translation
- `german` - Base form
- `extra` - Comparative – Superlative (e.g., "groß – größer – am größten")
- `example_de` - Show both predicative AND attributive use
- `example_ru` - Russian translation
- `notes` - Note umlaut changes, irregularities in Russian
- `audio` - Filename.mp3

**Card types created:**
1. Reverse RU→DE
2. Reverse DE→RU

**Example:**
```json
{
  "card_type": "Reverse",
  "word_type": "Adjective",
  "russian": "большой",
  "german": "groß",
  "extra": "groß – größer – am größten",
  "example_de": "Das Haus ist groß. Ein großes Haus.",
  "example_ru": "Дом большой. Большой дом.",
  "notes": "С умлаутом в сравнительной и превосходной степени",
  "audio": "Groß.mp3"
}
```

---

### Preposition Cards (2 cards per word)

**Data to generate:**
- `russian` - Russian translation
- `german` - German preposition
- `extra` - Case governance (e.g., "+ Dativ", "+ Akkusativ", "Wechselpräposition")
- `example_de` - Show preposition with correct case
- `example_ru` - Russian translation
- `notes` - Case requirements, special uses in Russian
- `audio` - Filename.mp3

**Card types created:**
1. Reverse RU→DE
2. Reverse DE→RU

**Example:**
```json
{
  "card_type": "Reverse",
  "word_type": "Preposition",
  "russian": "с, вместе с",
  "german": "mit",
  "extra": "+ Dativ",
  "example_de": "Ich gehe mit dem Kind. Mit dir.",
  "example_ru": "Я иду с ребёнком. С тобой.",
  "notes": "Всегда требует Dativ",
  "audio": "Mit.mp3"
}
```

---

### Article/Conjunction/Particle/Pronoun/Possessive/Question Word Cards (2 cards per word)

**Data to generate:**
- `russian` - Russian translation
- `german` - German word
- `extra` - "—" (not applicable)
- `example_de` - Show word in natural context
- `example_ru` - Russian translation
- `notes` - Function/usage explanation in Russian
- `audio` - Filename.mp3

**Card types created:**
1. Reverse RU→DE
2. Reverse DE→RU

**Example (Conjunction):**
```json
{
  "card_type": "Reverse",
  "word_type": "Conjunction",
  "russian": "и",
  "german": "und",
  "extra": "—",
  "example_de": "Brot und Butter.",
  "example_ru": "Хлеб и масло.",
  "notes": "Сочинительный союз для соединения однородных членов",
  "audio": "Und.mp3"
}
```

---

## Card Type Mapping

| Word Type | JSON Entries | Final Cards | Card Types Created |
|-----------|--------------|-------------|-------------------|
| Noun | 2 (1 Reverse + 1 Cloze) | 3 | RU→DE, DE→RU, Cloze |
| Verb | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Adjective | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Preposition | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Adverb | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Article | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Conjunction | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Particle | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Pronoun | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Possessive | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Question Word | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Adjective/Adverb | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Adverb/Particle | 1 (Reverse) | 2 | RU→DE, DE→RU |

**Note:** `insert_cards.py` automatically expands each "Reverse" entry into 2 cards (RU→DE and DE→RU)

---

## Edge Cases

### Compound Words
- Audio filename is specified in `word_tracking.md` Audio column
- Use the exact filename from tracking - do not make assumptions or search for alternatives
- Example: If tracking shows "Tisch.mp3" for "Bürotisch", use "Tisch.mp3"

### Separable Verbs
- List infinitive with prefix: "ankommen"
- Perfekt: "ist angekommen"
- Example should show separation: "Ich komme morgen an."
- Notes should mention separability in Russian

### Wechselpräpositionen (Two-Way Prepositions)
- Case: "Wechselpräposition (+ Dativ/Akkusativ)"
- Example should show BOTH cases:
  - "Ich bin in der Stadt. (Dativ - где?)"
  - "Ich gehe in die Stadt. (Akkusativ - куда?)"

### Modal Verbs
- High priority (see `CLAUDE.md` grammar priorities)
- Notes should explain meaning distinctions in Russian
- Example: "müssen vs sollen", "nicht dürfen vs nicht müssen"

### Konjunktiv II Forms
- Highest priority (30% - see `CLAUDE.md`)
- Notes should explain würde-form construction
- Example should show polite request or conditional

### Polysemous Words (Multiple Meanings, Same Word Class)

**Definition:** Words with multiple distinct meanings within the same word class.

**Examples:**
- `lassen` (to leave / to let/allow)
- `geben` (to give / there is - es gibt)
- `stellen` (to place / to ask - eine Frage stellen)

**Rules:**
1. **Include all major meanings in Russian translation**
   - Format: "значение1, значение2"
   - Example: `"russian": "оставлять, позволять"`

2. **Provide multiple examples covering different meanings**
   - Use 2-3 sentences if meanings are very distinct
   - Example: `"example_de": "Ich lasse mein Auto zu Hause. Lass mich das machen!"`

3. **Clarify meanings in notes**
   - Explicitly list numbered meanings in Russian
   - Example: `"notes": "Два значения: (1) оставлять что-то (2) позволять, разрешать"`

4. **Generate one card set** (not separate cards for each meaning)

**✅ Good Example:**
```json
{
  "card_type": "Reverse",
  "word_type": "Verb",
  "russian": "оставлять, позволять",
  "german": "lassen",
  "extra": "hat gelassen",
  "example_de": "Ich lasse mein Auto zu Hause. Lass mich das machen!",
  "example_ru": "Я оставляю машину дома. Позволь мне это сделать!",
  "notes": "Неправильный глагол • haben + Partizip II • Два значения: (1) оставлять (2) позволять, разрешать",
  "audio": "Lassen.mp3"
}
```

### Homonyms (Different Word Classes, Same Spelling)

**Definition:** Words spelled identically but with completely different meanings and word classes.

**Examples:**
- `der Morgen` (morning - noun m) vs `morgen` (tomorrow - adverb)
- `der Arm` (arm - noun m) vs `arm` (poor - adjective)

**Rules:**
1. **Track separately in word_tracking.md**
   - Create separate entries with word type specification
   - Same audio file for all entries

   **IMPORTANT:** Only generate cards for homonyms explicitly listed in `word_tracking.md`. Do not automatically add other homonym forms during card generation. Process each entry independently.

2. **Generate separate card sets for each homonym**
   - Treat as completely independent words
   - Noun gets 3 cards (2 Reverse + 1 Cloze)
   - Adverb/Adjective gets 2 cards (2 Reverse)

3. **Add cross-reference note to each card**
   - Mention the homonym exists
   - Example for noun: `"notes": "Мужской род • Не путать с наречием 'morgen' (завтра)"`

4. **Share audio file across all homonyms**
   - All entries reference same audio file (e.g., `Morgen.mp3`)

**✅ Good Example (Homonym - Noun):**
```json
{
  "card_type": "Reverse",
  "word_type": "Noun",
  "russian": "утро",
  "german": "der Morgen",
  "extra": "die Morgen",
  "example_de": "Guten Morgen! Der Morgen ist schön.",
  "example_ru": "Доброе утро! Утро прекрасное.",
  "notes": "Мужской род • Не путать с наречием 'morgen' (завтра)",
  "audio": "Morgen.mp3"
}
```

---

## Common Mistakes to Avoid

### ❌ Bad Example (Noun):
```json
{
  "russian": "стол",
  "german": "Tisch",  // ❌ Missing article!
  "extra": "Tische",  // ❌ Missing article in plural!
  "example_de": "Tisch ist groß.",  // ❌ Unnatural German
  "example_ru": "(table is big)",  // ❌ English, not Russian!
  "notes": "masculine noun"  // ❌ English, not Russian!
}
```

### ✅ Good Example (Noun):
```json
{
  "russian": "стол",
  "german": "der Tisch",  // ✅ Article included
  "extra": "die Tische",  // ✅ Article in plural
  "example_de": "Der Tisch ist aus Holz.",  // ✅ Natural sentence
  "example_ru": "Стол сделан из дерева.",  // ✅ Russian translation
  "notes": "Мужской род • Множественное число с -e окончанием"  // ✅ Russian
}
```

---

## Quality Checklist

Before writing to `pending_cards.json`, verify:

### For All Cards:
- [ ] Russian translation is accurate and natural
- [ ] Example sentences are realistic German (A2-B1 level)
- [ ] Russian example translations are accurate
- [ ] Grammatical notes are in Russian and helpful
- [ ] Audio filename matches available file (check capitalization)
- [ ] No English text anywhere (only German and Russian)
- [ ] Example sentences show natural usage, not isolated words
- [ ] `word_type` matches `word_types.py` enum exactly (case-sensitive)

### For Nouns Specifically:
- [ ] Article is always included (never just "Mann", always "der Mann")
- [ ] Gender is correct (m/f/n)
- [ ] Plural form is accurate
- [ ] 2 JSON entries created: 1 Reverse + 1 Cloze (expands to 3 cards)

### For Verbs Specifically:
- [ ] Infinitive form is correct
- [ ] Perfekt shows correct auxiliary (haben vs ist)
- [ ] Partizip II is correct
- [ ] Example shows conjugated form in context

### For Adjectives Specifically:
- [ ] Comparative/superlative forms are correct
- [ ] Umlaut changes noted if applicable
- [ ] Both predicative and attributive examples shown

### For Prepositions Specifically:
- [ ] Case governance is explicitly stated
- [ ] Example clearly demonstrates the required case

---

## Validation Best Practices

### What Gemini Validates Well:
✅ Grammatical accuracy (gender, plural, Perfekt forms)
✅ Russian translation accuracy
✅ Example sentence naturalness
✅ Completeness of data

### What to Double-Check Yourself:
⚠️ Audio filename capitalization
⚠️ Priority topics (Konjunktiv II, prepositions, modal verbs)
⚠️ Russian note quality (Gemini might not catch awkward phrasing)

### If Validation Fails:
1. **Read the issues carefully** - Gemini is usually right
2. **Regenerate with fixes** - Don't ignore the feedback
3. **Re-validate** - One retry only
4. **If still fails** - Skip word, add to `failed_words.txt` for manual review

---

## File Locations Reference

```
german/flashcards/
├── word_tracking.md                 # Status tracking (Step 1, Step 7)
├── german_vocabulary_b1.md          # Deck source of truth
├── german_vocabulary_b1.apkg        # Final Anki deck
├── WORKFLOW.md                      # This file
└── scripts/
    ├── pending_cards.json           # Claude writes here (Step 4)
    ├── update_word_tracking.py      # Update tracking (Step 1, Step 7)
    ├── insert_cards.py              # Insert cards into MD (Step 5)
    ├── generate_deck_from_md.py     # Generate .apkg (Step 6)
    └── audio_checker.py             # Check audio availability

german/audio/
├── words_from_duolingo/             # 1,189 MP3 pronunciation files
│   └── [Word].mp3                   # Capitalized with umlauts
└── generated_audio/                 # 457 WAV pronunciation files (Piper TTS)
    ├── [Word].wav                   # High-quality German TTS
    └── scripts/                     # Audio generation tools
```

---

## Session Logging

After completing a batch, update `SESSION_LOG.md`:

```markdown
- **YYYY-MM-DD HH:MM** | `completed` | Generated N cards for M words ([word1, word2, ...]) - [brief summary of any issues/fixes]
```

Use `date '+%Y-%m-%d %H:%M'` for timestamp.

---

**Version:** 1.2
**Last Updated:** 2025-12-20

**Changes from 1.1:**
- Updated Input section to reflect actual usage (10-word batches, random/direct selection)
- Fixed all word_type values to match `word_types.py` enum exactly (no parenthetical details)
- Added complete list of valid word_type values with case-sensitivity warning
- Expanded word type list to include Pronoun, Possessive, Question Word (previously missing)
- Updated Card Type Mapping table with all 13 word types
- Added word_types.py to Required Files section
- Added word_type compliance to Quality Checklist
- Removed reference to deleted `vocabulary/cleaned_german_words.md`
- Fixed Cloze example - cloze syntax only in `german` field, not in `example_de`
- Added note about fail-fast principle in scripts
- Clarified model can only modify `pending_cards.json`, not other files
- Fixed audio filename guidance - use exact value from `word_tracking.md`, no searching
- Removed Import Verification (not a model task)

**Changes from 1.0 (v1.1):**
- Added Required Files section with fail-fast instruction
- Added Input and Output sections
- Added consolidated Validation section
- Added structured Error Handling section
- Reorganized to comply with `common_rules/document_structure.md`
