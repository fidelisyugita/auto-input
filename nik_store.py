from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Progress:
    next_index: int = 0
    used_niks: list[str] = field(default_factory=list)
    skipped_niks: list[dict] = field(default_factory=list)
    success_count: int = 0
    last_run: str | None = None

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "Progress":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(**data)


def _load_niks(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"NIK file not found: {path}")

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            raw = data.get("niks") or data.get("nik") or []
        else:
            raise ValueError("JSON must be an array or object with 'niks' key")
    elif path.suffix.lower() in {".xlsx", ".xls"}:
        import pandas as pd

        df = pd.read_excel(path)
        if "nik" not in df.columns:
            raise ValueError("Excel must have a 'nik' column")
        raw = df["nik"].dropna().astype(str).tolist()
    else:
        raw = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and line.strip().lower() != "nik"
        ]

    return [
        str(v).strip()
        for v in raw
        if str(v).strip() and str(v).strip().lower() not in {"nan", "nik"}
    ]


class NikStore:
    def __init__(self, nik_path: Path, progress_path: Path):
        self.niks = _load_niks(nik_path)
        self.progress = Progress.load(progress_path)
        self.progress_path = progress_path

    def remaining_count(self) -> int:
        return max(0, len(self.niks) - self.progress.next_index)

    def next_nik(self) -> str | None:
        if self.progress.next_index >= len(self.niks):
            return None
        nik = self.niks[self.progress.next_index]
        self.progress.next_index += 1
        return nik

    def mark_used(self, nik: str) -> None:
        self.progress.used_niks.append(nik)
        self.progress.success_count += 1
        self._touch()
        self.progress.save(self.progress_path)

    def mark_skipped(self, nik: str, reason: str) -> None:
        self.progress.skipped_niks.append(
            {"nik": nik, "reason": reason, "at": _now()}
        )
        self._touch()
        self.progress.save(self.progress_path)

    def _touch(self) -> None:
        self.progress.last_run = _now()

    def summary(self) -> str:
        p = self.progress
        return (
            f"Total NIK: {len(self.niks)}\n"
            f"Next index: {p.next_index}\n"
            f"Remaining: {self.remaining_count()}\n"
            f"Success: {p.success_count}\n"
            f"Skipped: {len(p.skipped_niks)}\n"
            f"Last run: {p.last_run or '-'}"
        )


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
