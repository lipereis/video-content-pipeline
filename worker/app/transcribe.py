"""Speech-to-text with faster-whisper. The model loads on first use and stays in memory."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Transcript:
    text: str
    language: str
    duration_seconds: float


# path -> Transcript. Tests inject a fake one.
Transcriber = Callable[[Path], Transcript]


def extract_audio(path: Path):
    """Decode the audio track with ffmpeg into the 16 kHz mono float array Whisper expects."""
    import numpy as np

    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read the audio: {result.stderr.decode(errors='replace').strip()[:300]}")
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0


class WhisperTranscriber:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.getenv("WHISPER_MODEL", "small")
        self._model = None

    def __call__(self, path: Path) -> Transcript:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        segments, info = self._model.transcribe(extract_audio(path), vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments)
        return Transcript(text=text, language=info.language, duration_seconds=round(info.duration, 1))
