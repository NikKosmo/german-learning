# Card Creation Rules for German Anki Decks

**Version:** 2.1
**Date:** November 8, 2025
**Purpose:** Standard rules for generating all German flashcards
**Last Updated:** November 8, 2025 - Added bidirectional cards and gender cloze for nouns

---

## 🎯 General Rule (Applies to ALL Words)

Every card must include:

### 1. **Russian Translation**
- Front side (question): Russian word/phrase
- Native language for recall and comprehension

### 2. **German Word/Phrase**
- Back side (answer): German text
- Must be shown in natural form (not isolated)

### 3. **Example Sentence**
- **German sentence** showing the word in context
- **Russian translation** of the sentence (in parentheses)
- Must be natural, realistic German
- Should make the usage clear

### 4. **Audio** (REQUIRED)
- Audio file for German pronunciation is REQUIRED for all cards
- We have 1,189 audio files in `audio/words_from_duolinguo/`
- Format in Anki: `[sound:filename.mp3]`
- Plays on answer (German) side
- **File naming:** Capitalized word with umlauts: `Büro.mp3`, `Straße.mp3`
- **If audio missing:** Add word to `MISSING_AUDIO.md` for later collection
- **Do not create cards** for words without audio until audio is obtained

### 5. **Grammatical Notes**
- Brief explanation in Russian
- Clarifies usage, case, or grammatical function
- Example: "Akkusativ после глагола 'sehen'"

### 6. **One Concept Per Card**
- Each card tests ONE thing only
- Don't mix multiple grammar points
- Clear learning objective

---

## 📝 Card Type Selection

### ⭐ PRIMARY RULE: Vocabulary = Bidirectional Reverse Cards

**All vocabulary learning uses Bidirectional Reverse Cards**
- Every word gets TWO reverse cards: RU→DE AND DE→RU
- Ensures both recognition (DE→RU) and production (RU→DE)
- Nouns, verbs, adjectives, adverbs, conjunctions, etc.

**Additional for Nouns: Gender Cloze Cards**
- Every noun gets a THIRD card: Gender Cloze ({{c1::der/die/das}} Noun)
- Tests article recall - critical for German noun mastery
- Part of vocabulary learning, not grammar practice

### Card breakdown per word type:
- **Nouns:** 3 cards each (RU→DE, DE→RU, Gender Cloze)
- **Verbs, Adjectives, Prepositions, Adverbs:** 2 cards each (RU→DE, DE→RU)

### Use **Reverse Cards** for:
- **ALL vocabulary learning** (nouns, verbs, adjectives, etc.)
- Active vocabulary production (RU→DE)
- Passive vocabulary recognition (DE→RU)
- Testing word recall with full context
- Learning new words with examples

### Use **Cloze Cards** for:
- **Noun gender practice** (vocabulary learning - part of knowing the noun)
- Grammar patterns (endings, declensions)
- Prepositions in context
- Verb conjugations
- Word order rules

**Summary:**
- 📘 Learning a noun? → **3 cards: RU→DE, DE→RU, Gender Cloze**
- 📙 Learning other vocabulary? → **2 cards: RU→DE, DE→RU**
- 📗 Practicing grammar? → **Cloze Card**

### Cloze Card Best Practices:
- **Maximum 2-3 deletions per card** (preferably 1-2)
- Hide specific grammar elements, not random words
- Sentence context must make answer logically derivable
- Each deletion should test the same concept (e.g., all endings, or all articles)

### ❌ Cloze Anti-Patterns (What NOT to Do):

**1. Random Word Hiding**
```
"{{c1::Der}} Mann geht zur Arbeit."
```
- Problem: What am I recalling? The article? The whole phrase?
- No clear learning objective
- Ambiguous what's being tested

**2. Too Much Hidden**
```
"{{c1::Die Männer}} spielen Fußball."
```
- Hides article + noun together
- Unclear if testing vocabulary, grammar, or both
- Too broad to be useful

**3. Over-Deletion**
```
"Ich {{c1::möchte}} einen {{c2::Kaffee}} {{c3::trinken}}."
```
- More than 2-3 deletions becomes overwhelming
- Loses context needed to answer

**4. Vocabulary Testing with Cloze**
```
"Das ist ein {{c1::Tisch}}."
```
- Cloze is wrong tool for vocabulary
- Use Reverse cards instead

---

## 📚 Word-Type Specific Rules

### **NOUNS** - Additional Requirements

In addition to general rules above, noun cards must include:

1. **Article** - Always show der/die/das (NEVER just the noun)
   - Format: "der Mann" not "Mann"

2. **Plural Form** - German plurals are unpredictable
   - Show as: "Plural: die Männer"

3. **Gender Indicator** - For color-coding
   - m/f/n (masculine/feminine/neuter)

4. **Gender Color-Coding** (on answer side):
   - Blue (#2196F3) for masculine (der)
   - Pink (#E91E63) for feminine (die)
   - Green (#4CAF50) for neuter (das)

**Example Noun Card:**
```
Front: мужчина
Back:  der Mann
       Plural: die Männer
       Example: Der Mann arbeitet im Büro. (Мужчина работает в офисе.)
       Notes: Мужской род, Nominativ
       Audio: [sound:der_mann.mp3]
```

---

### **VERBS** - Additional Requirements

In addition to general rules above, verb cards must include:

1. **Infinitive Form** - Always show full infinitive
   - Format: "arbeiten" (not conjugated form)

2. **Perfekt Form** - Show auxiliary + Partizip II
   - Format: "hat gearbeitet" or "ist gegangen"
   - Helps learner know which auxiliary (haben/sein)

3. **Example with Conjugation** - Show verb in use
   - Include at least one conjugated example
   - Example: "Ich arbeite jeden Tag." (Я работаю каждый день.)

**Example Verb Card:**
```
Front: работать
Back:  arbeiten
       Perfekt: hat gearbeitet
       Example: Ich arbeite im Büro. (Я работаю в офисе.)
       Notes: Регулярный глагол • haben + Partizip II
       Audio: [sound:arbeiten.mp3]
```

**Note:** Conjugation patterns and separable prefixes are for grammar practice (Cloze cards), not vocabulary cards.

---

### **ADJECTIVES** - Additional Requirements

In addition to general rules above, adjective cards must include:

1. **Base Form** - Always show uninflected adjective
   - Format: "groß" (not "großer" or "große")

2. **Comparative & Superlative** - Show all three forms
   - Format: "groß – größer – am größten"
   - Helps with irregular forms (gut → besser → am besten)

3. **Example in Context** - Show adjective with declension
   - Use both predicative (no ending) and attributive (with ending)
   - Example: "Das Haus ist groß." AND "Das große Haus."

**Example Adjective Card:**
```
Front: большой
Back:  groß – größer – am größten
       Example: Das Haus ist groß. (Дом большой.)
                Ein großes Haus. (Большой дом.)
       Notes: С умлаутом в сравнительной и превосходной степени
       Audio: [sound:groß.mp3]
```

**Note:** Declension patterns (endings) are for grammar practice (Cloze cards), not vocabulary cards.

---

### **PREPOSITIONS** - Additional Requirements

In addition to general rules above, preposition cards must include:

1. **Case Governance** - Specify which case the preposition takes
   - Format: "mit + Dativ" or "durch + Akkusativ"
   - Essential for German prepositions

2. **Example Showing Case** - Demonstrate the case clearly
   - Show article/pronoun in correct case
   - Example: "mit dem Mann" (Dativ), "durch die Stadt" (Akkusativ)

**Example Preposition Card:**
```
Front: с, вместе с
Back:  mit (+ Dativ)
       Example: Ich gehe mit dem Kind. (Я иду с ребёнком.)
                Mit dir. (С тобой.)
       Notes: Всегда требует Dativ
       Audio: [sound:mit.mp3]
```

---

### **ADVERBS** - Additional Requirements

Adverbs follow the **general rule only** - no additional requirements.

- Show base form
- Include example sentences
- Grammatical notes about usage (time/manner/place)

**Example Adverb Card:**
```
Front: сегодня
Back:  heute
       Example: Heute ist Montag. (Сегодня понедельник.)
       Notes: Наречие времени
       Audio: [sound:heute.mp3]
```

---

### **OTHER WORD TYPES** (Conjunctions, Pronouns, etc.)

Follow the **general rule only** - no additional requirements.
Add grammatical notes as needed to clarify usage.

---

## 📄 Documentation: MD File Format

Every deck must have a corresponding `.md` file with the same name for discussion and review.

**Example:** `deck_name.apkg` → `deck_name.md`

### MD File Structure:

```markdown
# deck_name

**Deck Info:**
- Total cards: X
- Words: Y
- Card types: Reverse RU→DE (Y), Reverse DE→RU (Y), Cloze (for nouns)
- Generated: YYYY-MM-DD
- Follows: CARD_CREATION_RULES.md vX.X

## Cards

| # | Card Type | Word Type | Russian | German | Plural/Perfekt/Forms | Example_DE | Example_RU | Notes | Audio |
|---|-----------|-----------|---------|--------|----------------------|------------|------------|-------|-------|
| 1 | Reverse RU→DE | Noun (m) | ... | der Mann | die Männer | ... | ... | ... | Mann.mp3 |
| 2 | Reverse DE→RU | Noun (m) | ... | der Mann | die Männer | ... | ... | ... | Mann.mp3 |
| 3 | Cloze | Noun (m) | — | {{c1::der}} Mann | die Männer | ... | ... | ... | Mann.mp3 |
```

**Organization:**
- Cards grouped by word (all 2-3 cards for each word together)
- Sequential numbering across entire deck
- Cloze cards have blank Russian column
- All other columns filled for all card types

**Purpose:**
- Easy reference during discussions ("Card #5", "Card #12")
- Source of truth - script should reproduce same .apkg from .md data
- Human-readable review format

---

## ❌ Common Mistakes to Avoid

1. **Missing reverse direction** - Every word needs BOTH RU→DE AND DE→RU cards
2. **Missing gender cloze for nouns** - Every noun needs the gender cloze card
3. **No audio** - Every German card needs pronunciation
4. **No context** - Never show isolated words
5. **Missing Russian** - Always include translations and notes
6. **Too many concepts** - One card = one concept
7. **Ambiguous cloze** - Clear what grammar point is being tested
8. **Nouns without articles** - Always include der/die/das
9. **No MD file** - Every .apkg must have corresponding .md for discussions

---

## 🎨 Card Model Structure

### Reverse Card Fields (RU→DE):
1. `Russian` - Russian word/phrase
2. `German` - German translation (or specific fields for word type)
3. `Example_DE` - German example sentence
4. `Example_RU` - Russian translation of example
5. `Notes` - Grammatical notes in Russian
6. `Audio` - Audio file reference

### Reverse Card Fields (DE→RU):
- Same fields as RU→DE
- Front/Back are swapped in template
- German shown on question side, Russian on answer side

### Noun Card Fields (for both RU→DE and DE→RU):
1. `Russian` - Russian word
2. `Article` - der/die/das
3. `Noun` - German noun
4. `Plural` - Plural form
5. `Gender` - m/f/n (for CSS class)
6. `Example_DE` - German example
7. `Example_RU` - Russian translation
8. `Notes` - Grammatical notes
9. `Audio` - Audio file

### Gender Cloze Card Fields (Nouns only):
1. `Cloze_German` - German with cloze deletion: {{c1::der}} Mann
2. `Plural` - Plural form
3. `Example_DE` - German example
4. `Example_RU` - Russian translation
5. `Notes` - Grammatical notes
6. `Audio` - Audio file

### Grammar Cloze Card Fields:
1. `Text` - German sentence with {{c1::}} deletions
2. `Translation` - Russian translation of full sentence
3. `Notes` - Grammatical explanation in Russian
4. `Audio` - Audio of complete sentence

---

## 📊 Priority Topics (Based on B1 Test Gaps)

When creating cards, prioritize:

1. **Konjunktiv II** (30%) - würde-forms, conditional, polite requests
2. **Prepositions** (25%) - damit/darauf/wofür/daran/worauf
3. **Perfekt** (20%) - Word order, Partizip II placement
4. **Modal verbs** (15%) - nicht dürfen vs müssen distinctions
5. **Adjective declension** (10%) - Endings by case/gender

---

## ✅ Quality Checklist

Before creating cards for a word, verify:

**For ALL words:**
- [ ] Bidirectional cards created (RU→DE AND DE→RU)
- [ ] Russian translation present
- [ ] German word in natural form (with article for nouns)
- [ ] Example sentence in German + Russian
- [ ] Audio file available/referenced
- [ ] Grammatical notes in Russian
- [ ] Only ONE concept being tested per card
- [ ] Context makes answer derivable (for cloze)
- [ ] All word-type specific requirements met

**For NOUNS specifically:**
- [ ] Gender cloze card created ({{c1::der/die/das}} Noun)
- [ ] Total 3 cards: RU→DE, DE→RU, Gender Cloze

**For deck documentation:**
- [ ] MD file created with same name as .apkg file
- [ ] All cards documented in table format
- [ ] Cards grouped by word, numbered sequentially

---

**Implementation Status:**
✅ Complete rules for all word types (nouns, verbs, adjectives, prepositions, adverbs)
✅ Bidirectional card generation
✅ Gender cloze cards for nouns
✅ MD file documentation format
