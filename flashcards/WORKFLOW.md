# Flashcard Generation Workflow

**Version:** 1.1
**Date:** 2025-12-01
**Purpose:** Complete end-to-end workflow for generating German-Russian flashcards using Claude + Gemini validation

---

## Overview

This workflow uses **Claude to generate card data** (translations, examples, notes) and **Gemini to validate** quality. No LLM script needed - Claude works directly with the data files.

### Key Principle
**Claude generates, Gemini validates, scripts automate the insertion.**

---

## Complete Workflow (7 Steps)

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

**Example:**
```
| ein | pending | ✅ Ein.mp3 | — | — | — |
| eine | pending | ✅ Eine.mp3 | — | — | — |
```

**Recommended batch size:** 5-10 words for testing, 20-50 for production

---

### Step 3: Claude Generates & Validates Card Data (Per-Word)

**IMPORTANT: Gemini validation is REQUIRED for every word. Do not skip this step.**

For each word:

#### 2.1 Identify Word Type

**Supported types:**
- **Noun** - has gender (der/die/das), plural form
- **Verb** - has infinitive, Perfekt form
- **Adjective** - has comparative/superlative
- **Preposition** - has case governance (+ Dativ, etc.)
- **Adverb** - time/manner/place modifiers
- **Article/Numeral** - ein, eine, der, die, etc.
- **Conjunction** - und, aber, oder, weil, etc.
- **Particle** - ja, nein, doch, etc.

**Decision guide:**
- Starts with capital → likely noun
- Ends in -en → likely verb infinitive
- Ends in -ung, -heit, -keit → feminine noun
- Short function words → article/particle/conjunction
- **When unsure:** Check context in `vocabulary/cleaned_german_words.md` or use German knowledge

#### 2.2 Generate Card Data

Generate complete data based on word type. See [Card Data Standards](#card-data-standards) below.

#### 2.3 Validate with Gemini (REQUIRED)

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

#### 2.4 Handle Validation Feedback

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
      "word_type": "Noun (m)",
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
      "word_type": "Noun (m)",
      "russian": "стол",
      "german": "{{c1::der}} Tisch",
      "extra": "die Tische",
      "example_de": "{{c1::Der}} Tisch ist aus Holz.",
      "example_ru": "Стол сделан из дерева.",
      "notes": "Мужской род • тест на артикль",
      "audio": "Tisch.mp3"
    }
  ]
}
```

**Required fields:** `card_type`, `word_type`, `russian`, `german`, `extra`, `example_de`, `example_ru`, `notes`, `audio`

**IMPORTANT - Auto-expansion behavior:**
- `card_type: "Reverse"` → insert_cards.py automatically creates **2 cards**: "Reverse RU→DE" and "Reverse DE→RU"
- `card_type: "Cloze"` → stays as 1 card
- **For verbs/prepositions/adjectives:** Create 1 entry with `card_type: "Reverse"` (expands to 2 cards)
- **For nouns:** Create 2 entries: one "Reverse" (expands to 2 cards) + one "Cloze" (stays 1 card) = 3 total cards

**Important:** File is overwritten each time (not appended)

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
   - Checks `generated_audio/` first (WAV), falls back to `words_from_duolinguo/` (MP3)
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

### Adverb/Particle/Article/Conjunction Cards (2 cards per word)

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
| Particle | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Article/Numeral | 1 (Reverse) | 2 | RU→DE, DE→RU |
| Conjunction | 1 (Reverse) | 2 | RU→DE, DE→RU |

**Note:** `insert_cards.py` automatically expands each "Reverse" entry into 2 cards (RU→DE and DE→RU)

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

### For Nouns Specifically:
- [ ] Article is always included (never just "Mann", always "der Mann")
- [ ] Gender is correct (m/f/n)
- [ ] Plural form is accurate
- [ ] 3 cards created with card_type: "Reverse RU→DE", "Reverse DE→RU", "Cloze"

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

### ❌ Bad Example (Verb):
```json
{
  "infinitive": "arbeiten",
  "perfekt": "gearbeitet",  // ❌ Missing auxiliary!
  "example_de": "arbeiten",  // ❌ Not a sentence!
}
```

### ✅ Good Example (Verb):
```json
{
  "infinitive": "arbeiten",
  "perfekt": "hat gearbeitet",  // ✅ Auxiliary included
  "example_de": "Ich arbeite jeden Tag.",  // ✅ Complete sentence with conjugation
}
```

---

## Edge Cases

### Compound Words
- Use the audio of the complete word if available
- If not available, use the base word audio
- Example: "Bürotisch" → use "Bürotisch.mp3" or fall back to "Tisch.mp3"

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
   - Example: `"example_ru": "Я оставляю машину дома. Позволь мне это сделать!"`

3. **Clarify meanings in notes**
   - Explicitly list numbered meanings in Russian
   - Example: `"notes": "Два значения: (1) оставлять что-то (2) позволять, разрешать"`

4. **Generate one card set** (not separate cards for each meaning)
   - The multiple examples help learners recognize all uses

**✅ Good Example (Polysemous Verb):**
```json
{
  "russian": "оставлять, позволять",
  "german": "lassen",
  "extra": "hat gelassen",
  "example_de": "Ich lasse mein Auto zu Hause. Lass mich das machen!",
  "example_ru": "Я оставляю машину дома. Позволь мне это сделать!",
  "notes": "Неправильный глагол • haben + Partizip II • Два значения: (1) оставлять (2) позволять, разрешать"
}
```

### Homonyms (Different Word Classes, Same Spelling)
**Definition:** Words spelled identically but with completely different meanings and word classes.

**Examples:**
- `der Morgen` (morning - noun m) vs `morgen` (tomorrow - adverb)
- `der Arm` (arm - noun m) vs `arm` (poor - adjective)
- `die Bank` (bench - noun f) vs `die Bank` (bank - noun f) - different genders!

**Rules:**
1. **Track separately in word_tracking.md**
   - Create separate entries with word type specification
   - Same audio file for all entries
   - Add distinguishing note

   Example:
   ```
   | Morgen | pending | ✅ Morgen.mp3 | — | Noun (m) | — | утро (morning) |
   | morgen | pending | ✅ Morgen.mp3 | — | Adverb | — | завтра (tomorrow) |
   ```

   **IMPORTANT:** Only generate cards for homonyms explicitly listed in word_tracking.md. Do not automatically add other homonym forms during card generation. Each homonym must be tracked separately and intentionally added to word_tracking.md by the user.

   - If only "Morgen" (noun) is in word_tracking.md → generate cards only for the noun
   - If later "morgen" (adverb) is added → generate cards for the adverb when processing that entry
   - Process each entry independently

2. **Generate separate card sets for each homonym**
   - Treat as completely independent words
   - Noun gets 3 cards (2 Reverse + 1 Cloze)
   - Adverb/Adjective gets 2 cards (2 Reverse)

3. **Add cross-reference note to each card**
   - Mention the homonym exists
   - Example for noun: `"notes": "Мужской род • Не путать с наречием 'morgen' (завтра)"`
   - Example for adverb: `"notes": "Наречие времени • Не путать с существительным 'der Morgen' (утро)"`

4. **Skip very rare homonyms**
   - Example: `das Morgen` (the future - philosophical/poetic) - too rare for B1
   - Focus on common meanings only

5. **Share audio file across all homonyms**
   - All entries reference same audio file (e.g., `Morgen.mp3`)

**✅ Good Example (Homonym - Noun):**
```json
{
  "russian": "утро",
  "german": "der Morgen",
  "extra": "die Morgen",
  "example_de": "Guten Morgen! Der Morgen ist schön.",
  "example_ru": "Доброе утро! Утро прекрасное.",
  "notes": "Мужской род • Не путать с наречием 'morgen' (завтра)",
  "audio": "Morgen.mp3"
}
```

**✅ Good Example (Homonym - Adverb):**
```json
{
  "russian": "завтра",
  "german": "morgen",
  "extra": "—",
  "example_de": "Ich komme morgen. Bis morgen!",
  "example_ru": "Я приду завтра. До завтра!",
  "notes": "Наречие времени • Не путать с существительным 'der Morgen' (утро)",
  "audio": "Morgen.mp3"
}
```

**Decision Tree:**
```
Is the word spelled the same?
├─ YES → Check word class
│   ├─ SAME word class → POLYSEMOUS (multiple examples, one card set)
│   └─ DIFFERENT word class → HOMONYM (separate entries, separate card sets)
└─ NO → Regular word (single meaning, single card set)
```

---

## Validation Best Practices

### What Gemini Validates Well:
✅ Grammatical accuracy (gender, plural, Perfekt forms)
✅ Russian translation accuracy
✅ Example sentence naturalness
✅ Completeness of data

### What to Double-Check Yourself:
⚠️ Audio filename capitalization
⚠️ Consistency with `CARD_CREATION_RULES.md`
⚠️ Priority topics (Konjunktiv II, prepositions, modal verbs)
⚠️ Russian note quality (Gemini might not catch awkward phrasing)

### If Validation Fails:
1. **Read the issues carefully** - Gemini is usually right
2. **Regenerate with fixes** - Don't ignore the feedback
3. **Re-validate** - One retry only
4. **If still fails** - Skip word, add to `failed_words.txt` for manual review

---

## File Locations Reference

**Everything needed for flashcard generation is in `flashcards/`:**

```
german/flashcards/
├── word_tracking.md                 # Status tracking (Step 1, Step 7)
├── german_vocabulary_b1.md          # Deck source of truth
├── german_vocabulary_b1.apkg        # Final Anki deck
├── CARD_CREATION_RULES.md           # Card structure rules
├── WORKFLOW.md                      # This file
└── scripts/
    ├── pending_cards.json           # Claude writes here (Step 4)
    ├── update_word_tracking.py      # Update tracking (Step 1, Step 7)
    ├── insert_cards.py              # Insert cards into MD (Step 5)
    ├── generate_deck_from_md.py     # Generate .apkg (Step 6)
    └── audio_checker.py             # Check audio availability

german/audio/
├── words_from_duolinguo/            # 1,188 MP3 pronunciation files
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

## Troubleshooting

### Issue: Gemini validation times out
**Solution:** Use smaller batch sizes (5 words instead of 10)

### Issue: Audio file not found
**Solution:** Check `audio/words_from_duolinguo/` for exact filename (capitalization matters)

### Issue: Card skipped during .apkg generation
**Solution:** Check `generate_deck_from_md.py` supports the word_type. Add to `get_model_key()` function if needed.

### Issue: Duplicate cards in deck
**Solution:** Check `word_tracking.md` - word might already be `in_deck`

---

## Version History

- **v1.0** (2025-11-09) - Initial workflow documentation, tested with 5 words (ein, eine, und, ja, nein)
