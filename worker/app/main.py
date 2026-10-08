"""HTTP worker called by the n8n workflow. One endpoint per workflow step."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .folders import Folders
from .generate import generate
from .transcribe import Transcriber, WhisperTranscriber


class FileRequest(BaseModel):
    file: str


class GenerateRequest(FileRequest):
    platforms: list[str] | None = None


class ArchiveRequest(FileRequest):
    status: str
    reason: str = ""


def create_app(folders: Folders | None = None, transcriber: Transcriber | None = None, llm_transport=None) -> FastAPI:
    app = FastAPI(title="video-content-pipeline worker")
    folders = folders or Folders(Path(os.getenv("DATA_DIR", "/data")), float(os.getenv("SETTLE_SECONDS", "10")))
    transcriber = transcriber or WhisperTranscriber()

    def transcript_file(name: str) -> Path:
        return folders.output / f"{Path(name).stem}.transcricao.txt"

    def resolve(name: str) -> Path:
        try:
            return folders.working_path(name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/claim")
    def claim():
        return {"files": [{"file": name} for name in folders.claim()]}

    @app.post("/transcribe")
    def transcribe(req: FileRequest):
        path = resolve(req.file)
        try:
            transcript = transcriber(path)
        except Exception as e:
            raise HTTPException(500, f"transcription failed: {e}") from e
        if not transcript.text.strip():
            raise HTTPException(422, "no speech found in the file")
        transcript_file(req.file).write_text(transcript.text, encoding="utf-8")
        return {
            "file": req.file,
            "language": transcript.language,
            "duration_seconds": transcript.duration_seconds,
            "chars": len(transcript.text),
        }

    @app.post("/generate")
    def generate_content(req: GenerateRequest):
        resolve(req.file)
        source = transcript_file(req.file)
        if not source.is_file():
            raise HTTPException(409, f"{req.file} has not been transcribed yet")
        output_file = folders.output / f"{Path(req.file).stem}.md"
        try:
            summary = generate(source, output_file, req.platforms, transport=llm_transport)
        except Exception as e:
            raise HTTPException(502, f"content generation failed: {e}") from e
        return {"file": req.file, "output_file": output_file.name, **summary}

    @app.post("/archive")
    def archive(req: ArchiveRequest):
        resolve(req.file)
        try:
            target = folders.archive(req.file, req.status, req.reason)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"file": req.file, "status": req.status, "moved_to": f"{target.parent.name}/{target.name}"}

    return app


def app() -> FastAPI:
    return create_app()
