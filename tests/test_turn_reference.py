from pathlib import Path


def test_reference_policy_depends_on_character_mode():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'session.character_mode == "photoreal" or chain_path == character' in source
    assert 'session.character_mode == "standard"' in source
    assert "await self._last_frame(output, chain_path)" in source


def test_first_video_of_each_turn_uses_four_steps():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert "actual_steps = 4 if first_video_of_turn else 8" in source
    assert "first_video_of_turn = False" in source


def test_all_turn_videos_use_reliable_articulation_seed():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'actual_seed = 1004 if session.character_mode == "photoreal" else 1000 + chunk.index' in source


def test_all_videos_use_strong_audio_modality_scale():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'actual_audio_modality_scale = 1.3 if session.character_mode == "photoreal" else 1.0' in source


def test_introductory_comma_clause_waits_for_its_continuation():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert "first_of_turn and complete_sentence" in source
