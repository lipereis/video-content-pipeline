"""Turn a transcript into hooks, a script and captions using Metis."""

import os
import sys
from pathlib import Path

METIS_PATH = Path(os.getenv("METIS_PATH", "/opt/metis"))
sys.path.insert(0, str(METIS_PATH / "scripts"))

import module1_pipeline as metis  # noqa: E402

DEFAULT_PLATFORMS = ["instagram", "tiktok"]


def tone_path() -> Path:
    return Path(os.getenv("TONE_FILE", METIS_PATH / "templates" / "tone_of_voice.yaml"))


def generate(transcript_file: Path, output_file: Path, platforms: list[str] | None = None, *, transport=None) -> dict:
    """Run the Metis pipeline on a transcript file and write the result to output_file."""
    tone = metis.load_tone_profile(tone_path())
    result = metis.run_pipeline(transcript_file, tone, platforms or DEFAULT_PLATFORMS, transport=transport)
    written = metis.write_output(result, output_file.parent)
    os.replace(written, output_file)
    return {
        "hooks": len(result.hooks),
        "script_rows": len(result.script_table),
        "captions": [caption.platform for caption in result.captions],
    }
