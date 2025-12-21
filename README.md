# German Language Learning Project

A structured approach to learning German from A1 to B2, with focus on telc B1 exam preparation.

**Target Audience:** Russian native speakers learning German (adaptable to other learners)

**Key Features:**
- 📚 Organized vocabulary lists by CEFR level (A1, A2, B1)
- 🎴 Automated Anki flashcard generation from markdown
- 📝 Priority-based grammar materials aligned with exam gaps
- 🎯 telc B1 exam-specific practice materials
- 🎤 Voice conversation practice setup guide
- 📊 Progress tracking and test analysis tools

**Learning Context:**
- **Goal:** B2 certification
- **Current Focus:** telc B1 exam preparation
- **Native Language:** Russian
- **Study Approach:** Priority-based learning targeting identified weak areas

## Getting Started

### Prerequisites
- Python 3.7+ (for flashcard generation)
- Anki Desktop or AnkiMobile (for flashcard study)

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/NikKosmo/german-learning.git
cd german-learning
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Generate Anki flashcards:**
```bash
cd flashcards/scripts
python3 generate_deck_from_md.py
```

4. **Import to Anki:**
   - Open generated `.apkg` file in `flashcards/` directory
   - Import into Anki Desktop or sync to AnkiMobile

### Audio Files Note
Audio pronunciation files (141MB, 1,189 files) are excluded from this repo due to size. You can:
- Generate your own using TTS tools (see `audio/generated_audio/scripts/`)
- Download from pronunciation websites (Forvo.com, Google Translate)
- Use Anki's built-in TTS features

## Project Structure

### 📖 Vocabulary
Word lists organized by level and topic:
- `vocabulary/cleaned_german_words.md` - Core vocabulary list (800+ words)
- `vocabulary/by_level/` - Words organized by CEFR level (A1, A2, B1)
- `vocabulary/by_topic/` - Thematic word groups (transport, food, work, etc.)
- `vocabulary/problem_words.md` - Frequently forgotten words needing extra practice

### 📝 Grammar
Focused grammar study materials organized by priority for B1 exam:

**Priority order based on identified gaps:**
1. `grammar/konjunktiv_ii/` - Conditional mood, polite requests, hypothetical situations
2. `grammar/prepositions/` - Prepositional cases and pronouns (da-/wo-compounds)
3. `grammar/perfekt/` - Perfect tense and word order in complex sentences
4. `grammar/modal_verbs/` - Modal verb usage and distinctions
5. `grammar/adjective_declension/` - Adjective endings by case/gender


### 🎴 Flashcards
Anki deck generation system with automated workflow.

**Complete workflow documentation:**
- `flashcards/WORKFLOW.md` - Full 7-step card generation process
- `flashcards/CARD_CREATION_RULES.md` - Card formatting standards

**Key scripts:**
- `flashcards/scripts/generate_deck_from_md.py` - Generate .apkg from markdown source
- `flashcards/scripts/update_word_tracking.py` - Sync word status with deck
- `flashcards/scripts/validate_deck.py` - Validate deck against source markdown
- `flashcards/scripts/unpack_deck.py` - Unpack .apkg for analysis

**Generated deck:** `flashcards/german_vocabulary_b1.apkg`

### 🎤 Resources
Study guides and reference materials:
- `resources/voice_language_practice_guide.md` - Complete setup guide for AI voice conversations (English)
- `resources/voice_language_practice_guide_ru.md` - Complete setup guide for AI voice conversations (Russian)
- `resources/das_leben_book_analysis.md` - "Das Leben" textbook chapter analysis mapped to exam gaps

**Voice practice guide features:**
- Setup Open WebUI for conversation practice
- Configure local (Ollama) or cloud (OpenRouter) LLM
- Setup TTS (browser voices or local Piper)
- Create German tutor personas with custom instructions

### 🎧 Audio
Pronunciation and listening practice:
- `audio/words_from_duolingo/` - Duolingo audio files (gitignored - 141MB, 1,189 files)
- `audio/words_from_duolingo/learned_lexemes.csv` - Audio metadata and tracking
- `audio/generated_audio/scripts/` - TTS generation scripts using Piper

### ✍️ Writing
Writing practice and corrections:
- `writing/exercises/` - Practice emails and texts in telc format (80-100 words)
- `writing/corrections/` - Corrected versions with learning notes

### 🗣️ Speaking
Conversation practice tracking:
- `speaking/conversation_notes.md` - Conversation practice notes
- `speaking/pronunciation_issues.md` - Sounds requiring focused practice

**Practice ideas:**
- Language exchange meetups
- Online tutoring (iTalki, Preply)
- AI voice conversations (see `resources/voice_language_practice_guide.md`)

### 📊 Tests
Test results and practice exams:
- `tests/results/` - Practice test scores and analysis
- `tests/practice_exams/` - Full-length telc B1 format practice tests
- Test infrastructure with pytest for code validation

## How to Use This Repository

### For Vocabulary Learning
1. Browse `vocabulary/by_level/` or `vocabulary/by_topic/` for word lists
2. Generate flashcards using `flashcards/scripts/` (see `WORKFLOW.md`)
3. Study with Anki using spaced repetition

### For Grammar Practice
1. Start with priority topics in `grammar/` (ordered by importance for B1)
2. Focus on identified weak areas first (Konjunktiv II, prepositions, Perfekt)
3. Use example sentences to understand context and natural usage

### For Voice Conversation Practice
1. Follow setup guide in `resources/voice_language_practice_guide.md` (or `_ru.md` for Russian)
2. Install Open WebUI and configure LLM (local or cloud)
3. Set up TTS (browser voices or local Piper)
4. Create German tutor persona and start practicing

### For Exam Preparation
1. Review grammar priorities based on your test performance
2. Practice with materials in `tests/practice_exams/`
3. Do regular writing exercises (telc format emails: 80-100 words)
4. Use voice practice to improve speaking fluency
5. Track progress and adjust focus areas

## Flashcard Generation Workflow

The flashcard system uses `genanki` to create Anki decks from markdown source files.

**See `flashcards/WORKFLOW.md` for complete 7-step process.**

**Quick commands:**
```bash
# Update word tracking status
python3 flashcards/scripts/update_word_tracking.py

# Insert new cards into source markdown
python3 flashcards/scripts/insert_cards.py

# Generate .apkg deck
python3 flashcards/scripts/generate_deck_from_md.py

# Validate deck consistency
python3 flashcards/scripts/validate_deck.py flashcards/german_vocabulary_b1.apkg flashcards/german_vocabulary_b1.md
```

## Study Resources

**Main Materials:**
- "Das Leben" B1 textbook (Cornelsen) - see analysis in `resources/`
- Deutsche Welle B1 learning materials
- Anki spaced repetition system
- AI voice conversation practice

**Online Practice:**
- Deutsche Grammatik B1 (Schubert-Verlag)
- Forvo.com for pronunciation
- OpenRouter / Ollama for voice practice

**telc Exam Information:**
- Official website: [telc.net](https://www.telc.net)
- Find exam centers in your country
- Typical cost: €150-250 (varies by location)

## Contributing

This is a personal learning repository, but contributions are welcome:
- **Corrections:** Found an error? Open an issue or submit a PR
- **Additions:** Have useful resources or improvements? Share them!
- **Improvements:** Better explanations or examples? Let's discuss!

**Note:** Follow `common_rules/naming_conventions.md` for file/directory naming (snake_case standard).

## License

This project is open-source and available for educational purposes. Feel free to use, modify, and share.

## Acknowledgments

- **Deutsche Welle** for excellent B1 learning materials
- **Duolingo** for audio pronunciation files
- **Anki** for spaced repetition system
- **telc** for standardized certification framework
- **Open WebUI** community for voice conversation tools

---

**Last Updated:** 2025-12-20
**Status:** Active development - B1 exam preparation phase
