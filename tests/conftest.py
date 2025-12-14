import sys
from pathlib import Path
import types
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_paths(monkeypatch, tmp_path):
    """Monkeypatch paths.DECK_FILE and paths.WORD_TRACKING_FILE to temp files."""
    import paths
    deck = tmp_path / "german_vocabulary_b1.md"
    tracking = tmp_path / "word_tracking.md"
    deck.write_text("", encoding="utf-8")
    tracking.write_text("", encoding="utf-8")
    monkeypatch.setattr(paths, "DECK_FILE", deck, raising=False)
    monkeypatch.setattr(paths, "WORD_TRACKING_FILE", tracking, raising=False)
    return deck, tracking


@pytest.fixture
def fake_genanki(monkeypatch):
    """Provide a dummy genanki module so generate_deck_from_md can be imported."""
    fake = types.ModuleType("genanki")
    # Provide minimal attributes if needed by create_note_models (not used in tests)
    monkeypatch.setitem(sys.modules, "genanki", fake)
    return fake
