# German Language Learning Project

**A comprehensive, structured approach to learning German from A1 to B2**

## Overview

This repository contains materials, flashcard generation tools, and progress tracking for German language learning, with a focus on the **telc B1 exam** preparation.

**Target Audience:** Russian native speakers learning German (but adaptable to other learners)

**Key Features:**
- 📚 Organized vocabulary lists by CEFR level (A1, A2, B1)
- 🎴 Automated Anki flashcard generation from markdown
- 📝 Grammar-focused study materials with priority-based learning
- 🎯 telc B1 exam-specific practice materials
- 📊 Progress tracking and test analysis

**Learning Context:**
- **Goal:** B2 certification
- **Current Focus:** telc B1 exam (February-March 2026)
- **Native Language:** Russian
- **Current Level:** A2 → B1 transition

## Getting Started

### Prerequisites
- Python 3.7+ (for flashcard generation)
- Anki Desktop or AnkiMobile (for flashcard study)

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/YOUR_USERNAME/german-learning.git
cd german-learning
```

2. **Install dependencies (for flashcard generation):**
```bash
pip install genanki
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
Audio pronunciation files (141MB) are excluded from this repo. You can:
- Generate your own using TTS tools (see `audio/generated_audio/scripts/`)
- Download from pronunciation websites (Forvo.com, Google Translate)
- Use Anki's built-in TTS features

## Current Learning Status (November 2025)
- **A1 test:** 87% (strong foundation)
- **A2 test:** 68% (ready for B1)
- **B1 test:** 43% (specific gaps identified - not general weakness)
- **Study time:** 5-6 hours per week
- **Next milestone:** November practice test (target: 65-70%)

## Project Structure

### 📚 Study Plan
Create your own study plan based on the grammar priorities and test schedules outlined in this README.

### 📖 Vocabulary
Word lists organized by level and topic.
- `vocabulary/cleaned_german_words.md` - Core vocabulary list (800+ words)
- `vocabulary/by-level/` - Words organized by CEFR level (A1, A2, B1)
- `vocabulary/by-topic/` - Thematic word groups (transport, food, work, etc.)
- `vocabulary/problem-words.md` - Frequently forgotten words

### 📝 Grammar
Focused grammar study materials organized by priority for B1 exam.

**Priority Order:**
1. `grammar/konjunktiv-ii/` - **30% of study time** - Conditional mood, polite requests
2. `grammar/prepositions/` - **25% of study time** - Prepositional cases and pronouns
3. `grammar/perfekt/` - **20% of study time** - Perfect tense and word order
4. `grammar/modal-verbs/` - **15% of study time** - Modal verb usage and distinctions
5. `grammar/adjective-declension/` - **10% of study time** - Adjective endings

### 🎴 Flashcards
Anki decks and spaced repetition materials.
- `flashcards/anki_indefinite_articles_cards.txt` - Indefinite article declension practice

**Daily Goal:** 25 new cards + 100% review completion

### 🎧 Audio
Pronunciation and listening practice materials.
- `audio/words_from_duolinguo/` - Duolingo audio files (not included in repo - generate your own)
- `audio/generated_audio/scripts/` - TTS generation scripts using Piper

### ✍️ Writing
Writing practice and corrections.
- `writing/exercises/` - Practice emails and texts in telc format
- `writing/corrections/` - Corrected versions with learning notes

**Weekly Goal:** One telc-format email (80-100 words) every Sunday

### 🗣️ Speaking
Conversation practice notes and pronunciation tracking.
- `speaking/conversation-notes.md` - Conversation practice notes
- `speaking/pronunciation-issues.md` - Sounds requiring focused practice

**Practice Ideas:**
- Language exchange meetups
- Online tutoring sessions (iTalki, Preply)
- Conversation groups

### 👂 Listening
Listening comprehension materials and exercises.
- `listening/deutsche-welle/` - DW B1 level content
- `listening/tagesschau/` - Tagesschau in einfacher Sprache

**Weekly Goal:** 50 minutes listening practice (Saturdays)

### 📊 Tests
Test results and practice exams.
- `tests/results/` - Monthly progress test scores
- `tests/practice-exams/` - Full-length telc B1 practice tests

**Testing Schedule:**
- **November 2025:** Reach 65-70% on practice tests
- **December 2025:** Reach 75%+ for confident exam performance
- **January 2026:** Final practice under exam conditions

### 🔗 Resources
Reference materials and useful information.
- `resources/initial_instructions.md` - Learning approach and teacher guidelines
- `resources/useful-links.md` - Online resources and tools
- `resources/textbooks.md` - Recommended textbooks and courses

## Critical Areas for B1 Success

### 🚨 Top Priority Issues
1. **Konjunktiv II** - All würde-form errors in B1 test
2. **Prepositional pronouns** - Confusion with damit/darauf/wofür/daran
3. **Perfekt word order** - Complex sentences with Partizip II
4. **Modal verbs** - Distinguishing nicht dürfen vs müssen

## Weekly Study Schedule (5-6 hours)

- **Monday (60 min):** Konjunktiv II intensive study
- **Tuesday (60 min):** Group conversation class + 15 min homework
- **Wednesday (60 min):** Prepositions and pronouns
- **Thursday (60 min):** Group conversation class + 15 min homework
- **Friday (45 min):** Combined session (Perfekt, modals, adjectives)
- **Saturday (60 min):** Listening practice (DW, Tagesschau)
- **Sunday (60 min):** Writing practice + weekly review
- **Daily (15-20 min):** Anki flashcard review

## Timeline to B1 Exam

```
November 2025  → Intensive gap-closing, practice test format
December 2025  → Exam registration, specialized prep for writing/speaking
January 2026   → Final preparation, full practice exams
Feb-Mar 2026   → telc B1 Exam! 🎯
```

## Resources & Tools

**Main Study Resources:**
- Babbel B1 course
- Deutsche Welle B1 materials
- Anki deck (ID: 1586166030)
- "Das Leben" B1 textbook

**Online Practice:**
- Deutsche Grammatik B1 (Schubert-Verlag)
- Forvo.com for pronunciation

**telc Exam Information:**
- Official website: [telc.net](https://www.telc.net)
- Find exam centers in your country
- Typical cost: €150-250 (varies by location)

## Progress Tracking

Track progress by updating:
1. Test scores in `tests/results/`
2. Weekly completion in study plan
3. Problem areas in error tracking documents
4. Anki statistics (daily consistency)

## How to Use This Repository

### For Vocabulary Learning
1. Browse `vocabulary/by-level/` or `vocabulary/by-topic/` for word lists
2. Generate flashcards using scripts in `flashcards/scripts/`
3. Study with Anki daily (recommended: 25 new cards + reviews)

### For Grammar Practice
1. Start with priority topics in `grammar/` (ordered by importance for B1)
2. Focus on Konjunktiv II, prepositions, and Perfekt (highest priority)
3. Use example sentences to understand context

### For Exam Preparation
1. Follow the weekly schedule and grammar priorities outlined above
2. Practice with materials in `tests/practice-exams/`
3. Do weekly writing exercises (telc format emails: 80-100 words)
4. Track your progress in test results

## Contributing

This is a personal learning repository, but contributions are welcome:
- **Corrections:** Found an error? Open an issue or submit a PR
- **Additions:** Have useful resources? Share them!
- **Improvements:** Better explanations or examples? Let's discuss!

## Flashcard Generation

The flashcard system uses `genanki` to create Anki decks from markdown source:

```bash
# Update word tracking status
python3 flashcards/scripts/update_word_tracking.py

# Generate Anki deck from markdown
python3 flashcards/scripts/generate_deck_from_md.py
```

See `flashcards/WORKFLOW.md` for detailed instructions.

## License

This project is open-source and available for educational purposes. Feel free to use, modify, and share.

## Acknowledgments

- **Deutsche Welle** for excellent B1 learning materials
- **Duolingo** for gamified vocabulary building
- **Anki** for spaced repetition system
- **telc** for standardized certification framework

---

**Last Updated:** December 2025
**Status:** Active development - B1 exam preparation phase
