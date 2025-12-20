"""Project path configuration - all scripts import from this module"""
from pathlib import Path

# Project root is where this file lives
PROJECT_ROOT = Path(__file__).resolve().parent

# Directories
AUDIO_DIR = PROJECT_ROOT / "audio"
AUDIO_GENERATED = AUDIO_DIR / "generated_audio"
AUDIO_DUOLINGO = AUDIO_DIR / "words_from_duolingo"

FLASHCARDS_DIR = PROJECT_ROOT / "flashcards"
FLASHCARDS_SCRIPTS = FLASHCARDS_DIR / "scripts"

VOCABULARY_DIR = PROJECT_ROOT / "vocabulary"

# Common files
DECK_FILE = FLASHCARDS_DIR / "german_vocabulary_b1.md"
WORD_TRACKING_FILE = FLASHCARDS_DIR / "word_tracking.md"
CLEANED_WORDS_FILE = VOCABULARY_DIR / "cleaned_german_words.md"
