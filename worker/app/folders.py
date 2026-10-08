"""Folder state machine: inbox -> processando -> processados | falhou."""

import os
import time
from pathlib import Path

MEDIA_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".mp3", ".wav", ".m4a"}


class Folders:
    def __init__(self, root: Path, settle_seconds: float = 10.0):
        self.root = Path(root)
        self.settle_seconds = settle_seconds
        self.inbox = self.root / "inbox"
        self.working = self.root / "processando"
        self.done = self.root / "processados"
        self.failed = self.root / "falhou"
        self.output = self.root / "saida"
        for folder in (self.inbox, self.working, self.done, self.failed, self.output):
            folder.mkdir(parents=True, exist_ok=True)

    def claim(self) -> list[str]:
        """Move finished uploads from inbox to processando and return their names.

        A file still being copied keeps changing its mtime, so only files untouched for
        settle_seconds are taken. Moving them is what stops the next poll from picking
        the same video twice.
        """
        claimed = []
        now = time.time()
        for path in sorted(self.inbox.iterdir()):
            if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            stat = path.stat()
            if stat.st_size == 0 or now - stat.st_mtime < self.settle_seconds:
                continue
            target = self.working / path.name
            if target.exists():
                continue
            os.replace(path, target)
            claimed.append(path.name)
        return claimed

    def working_path(self, name: str) -> Path:
        """Resolve a claimed file by bare name; anything with a path in it is rejected."""
        if not name or Path(name).name != name:
            raise ValueError(f"invalid file name: {name!r}")
        path = self.working / name
        if not path.is_file():
            raise FileNotFoundError(f"{name} is not in processando/")
        return path

    def archive(self, name: str, status: str, reason: str = "") -> Path:
        source = self.working_path(name)
        if status not in ("done", "failed"):
            raise ValueError(f"unknown status: {status!r}")
        folder = self.done if status == "done" else self.failed
        target = folder / name
        if target.exists():
            target = folder / f"{source.stem}_{int(time.time())}{source.suffix}"
        os.replace(source, target)
        if status == "failed":
            target.with_name(target.name + ".erro.txt").write_text(reason or "sem detalhe", encoding="utf-8")
        return target
