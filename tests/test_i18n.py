from pathlib import Path

from app.llm import pop_speakable
from app.models import NarrationSession
from app.orchestrator import system_prompt


def test_session_language_defaults_are_backward_compatible():
    session = NarrationSession(text="", voice_id=1)
    assert session.ui_language == "ja"
    assert session.conversation_language == "auto"


def test_system_prompt_follows_explicit_conversation_language():
    assert "日本語" in system_prompt("ja")
    assert "English-speaking" in system_prompt("en")
    assert "same language" in system_prompt("auto")


def test_english_chunking_uses_longer_units_than_japanese():
    text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima"
    english, _ = pop_speakable(text, language="en")
    japanese, _ = pop_speakable(text, language="ja")
    assert len(english[0]) > len(japanese[0])


def test_browser_contains_bilingual_controls_and_persists_language():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    javascript = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'id="ui-language"' in html
    assert 'name="conversation_language"' in html
    assert 'localStorage.setItem("uiLanguage"' in javascript
    assert "Display language" in javascript
