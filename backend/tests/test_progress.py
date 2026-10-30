from app.services.progress import default_progress, init_progress, progress_for, update_stage


def test_init_and_stage_updates(tmp_path, monkeypatch) -> None:
    from app.services import progress as progress_mod

    monkeypatch.setattr(progress_mod.settings, "upload_dir", str(tmp_path))
    audio_id = "audio-progress-1"
    init_progress(audio_id)
    update_stage(audio_id, "conversion", percent=40, status="running", label="Convirtiendo")
    data = progress_for(audio_id, "transcribing")
    assert data["conversion"]["percent"] == 40
    assert data["conversion"]["status"] == "running"
    assert data["transcription"]["status"] == "pending"

    update_stage(audio_id, "conversion", status="done")
    update_stage(audio_id, "transcription", percent=12, status="running", label="Transcribiendo")
    data = progress_for(audio_id, "transcribing")
    assert data["conversion"]["status"] == "done"
    assert data["conversion"]["percent"] == 100
    assert data["transcription"]["percent"] == 12

    done = progress_for(audio_id, "completed")
    assert all(row["percent"] == 100 and row["status"] == "done" for row in done.values())


def test_default_progress_has_three_stages() -> None:
    data = default_progress()
    assert set(data) == {"conversion", "transcription", "analysis"}
