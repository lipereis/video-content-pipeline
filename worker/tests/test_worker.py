"""Worker tests. Whisper and the LLM are faked, so no model download, GPU or network is needed."""
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.folders import Folders
from app.main import create_app
from app.transcribe import Transcript

HOOK_TYPES = ["curiosity", "contrarian", "pain_point", "social_proof", "bold_statement"]


def fake_llm(system: str, user: str) -> str:
    """Answers each Metis request according to the schema it asked for."""
    if '"hooks"' in system:
        return json.dumps({"hooks": [{"hook_type": t, "text": f"hook {t}", "platform_fit": ["tiktok"]}
                                     for t in HOOK_TYPES]})
    if '"rows"' in system:
        return json.dumps({"rows": [{"time_range": f"{i * 5}-{i * 5 + 5}s", "voiceover": f"line {i}",
                                     "broll": "shot", "text_overlay": "TEXT", "sfx": "none"} for i in range(6)]})
    if '"core_thesis"' in system:
        return json.dumps({"core_thesis": "Editing takes too long", "arguments": ["a"], "data_points": [],
                           "soundbites": [], "pain_points": ["p"]})
    return json.dumps({"content": "A caption from the transcript. #video"})


def old_file(path: Path, age_seconds: float = 60) -> Path:
    path.write_bytes(b"video")
    past = time.time() - age_seconds
    os.utime(path, (past, past))
    return path


@pytest.fixture
def folders(tmp_path):
    return Folders(tmp_path, settle_seconds=10)


@pytest.fixture
def client(folders):
    transcriber = lambda path: Transcript("We talked about why captions take an afternoon.", "en", 12.0)
    return TestClient(create_app(folders, transcriber, fake_llm))


def test_claim_takes_only_finished_media_files(folders):
    old_file(folders.inbox / "ready.mp4")
    old_file(folders.inbox / "notes.txt")
    old_file(folders.inbox / "still_copying.mp4", age_seconds=1)

    assert folders.claim() == ["ready.mp4"]
    assert (folders.working / "ready.mp4").is_file()
    assert (folders.inbox / "still_copying.mp4").is_file()


def test_a_claimed_video_is_not_claimed_twice(folders):
    old_file(folders.inbox / "a.mp4")
    assert folders.claim() == ["a.mp4"]
    assert folders.claim() == []


def test_full_run_writes_content_and_archives_the_video(client, folders):
    old_file(folders.inbox / "clip.mp4")

    assert client.post("/claim").json() == {"files": [{"file": "clip.mp4"}]}
    transcribed = client.post("/transcribe", json={"file": "clip.mp4"}).json()
    assert transcribed["language"] == "en" and transcribed["chars"] > 0
    generated = client.post("/generate", json={"file": "clip.mp4", "platforms": ["tiktok"]}).json()
    assert generated == {"file": "clip.mp4", "output_file": "clip.md", "hooks": 5, "script_rows": 6,
                         "captions": ["tiktok"]}
    archived = client.post("/archive", json={"file": "clip.mp4", "status": "done"}).json()

    assert archived["moved_to"] == "processados/clip.mp4"
    assert "hook curiosity" in (folders.output / "clip.md").read_text(encoding="utf-8")
    assert "captions take an afternoon" in (folders.output / "clip.transcricao.txt").read_text(encoding="utf-8")
    assert not any(folders.working.iterdir())


def test_failed_video_is_kept_with_the_reason(client, folders):
    old_file(folders.inbox / "bad.mp4")
    client.post("/claim")

    client.post("/archive", json={"file": "bad.mp4", "status": "failed", "reason": "no speech found"})

    assert (folders.failed / "bad.mp4").is_file()
    assert (folders.failed / "bad.mp4.erro.txt").read_text(encoding="utf-8") == "no speech found"


def test_silent_video_is_rejected_instead_of_generating_from_nothing(folders):
    old_file(folders.inbox / "silent.mp4")
    client = TestClient(create_app(folders, lambda path: Transcript("  ", "en", 3.0), fake_llm))
    client.post("/claim")

    assert client.post("/transcribe", json={"file": "silent.mp4"}).status_code == 422
    assert client.post("/generate", json={"file": "silent.mp4"}).status_code == 409


def test_file_names_cannot_escape_the_working_folder(client, folders):
    (folders.root / "secret.mp4").write_bytes(b"x")
    assert client.post("/transcribe", json={"file": "../secret.mp4"}).status_code == 400
    assert client.post("/transcribe", json={"file": "missing.mp4"}).status_code == 404
