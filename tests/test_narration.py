from pathlib import Path

from app.models import NarrationSession
from app.orchestrator import Orchestrator


def test_direct_narration_starts_pipeline_without_llm(monkeypatch, tmp_path):
    created = []
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.sessions = {}
    orchestrator.tasks = {}

    def create_task(coroutine):
        created.append(coroutine)
        coroutine.close()
        return object()

    monkeypatch.setattr("app.orchestrator.asyncio.create_task", create_task)
    session = NarrationSession(text="", voice_id=1)
    orchestrator.narrate(session, tmp_path / "character.png", "朗読する文章です。")

    assert orchestrator.sessions[session.id] is session
    assert len(created) == 1


def test_direct_narration_route_and_ui_are_available():
    main = Path("app/main.py").read_text(encoding="utf-8")
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert '/api/sessions/{session_id}/narrations' in main
    assert 'id="narration-source"' in html
    assert 'id="narrate-button"' in html


def test_audio_assembly_does_not_merge_past_target_duration():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")

    assert "parts_duration + part_duration > session.target_chunk_seconds" in source
    assert "target_chunk_seconds * 0.65" not in source
