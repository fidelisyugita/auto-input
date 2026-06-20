from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Progress:
    next_index: int = 0
    main_next_index: int = 0
    used_niks: list[str] = field(default_factory=list)
    skipped_niks: list[dict] = field(default_factory=list)
    success_count: int = 0
    last_run: str | None = None
    using_filtered: bool = False

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> tuple["Progress", bool]:
        if not path.exists():
            return cls(), False
        data = json.loads(path.read_text())
        migrated = False
        if "main_next_index" not in data:
            data["main_next_index"] = data.get("next_index", 0)
            data["next_index"] = 0
            data["using_filtered"] = True
            migrated = True
        progress = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return progress, migrated


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


def _unique_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def save_filtered_file(
    path: Path,
    working: list[str],
    queue: list[str],
) -> None:
    payload = {
        "description": (
            "Working NIKs (successful sales) and remaining queue for fast iteration. "
            "Auto-updated by the bot."
        ),
        "working": working,
        "total": len(queue),
        "niks": queue,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_main_file(path: Path, niks: list[str]) -> None:
    payload = {
        "description": (
            "NIK list for MAP automation. Working NIKs (successful sales) listed first."
        ),
        "total": len(niks),
        "niks": niks,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class NikStore:
    def __init__(
        self,
        main_path: Path,
        progress_path: Path,
        filtered_path: Path | None = None,
    ):
        self.main_path = main_path
        self.filtered_path = filtered_path or main_path.parent / "nik-filtered.json"
        self.progress_path = progress_path
        self.progress, migrated = Progress.load(progress_path)

        self.working = _unique_preserve(self.progress.used_niks)
        self.niks = _unique_preserve(_load_niks(main_path))
        self._save_filtered()
        self.progress.using_filtered = True
        if migrated:
            self.progress.save(progress_path)

    def remaining_count(self) -> int:
        return max(0, len(self.niks) - self.progress.next_index)

    def next_nik(self) -> str | None:
        if not self.niks:
            return None
        if self.progress.next_index >= len(self.niks):
            self._complete_cycle()
        nik = self.niks[self.progress.next_index]
        self.progress.next_index += 1
        return nik

    def mark_used(self, nik: str) -> None:
        self.progress.used_niks.append(nik)
        self.progress.success_count += 1
        if nik not in self.working:
            self.working.append(nik)
        self._touch()
        self._save_filtered()
        self.progress.save(self.progress_path)

    def mark_skipped(self, nik: str, reason: str) -> None:
        self.progress.skipped_niks.append(
            {"nik": nik, "reason": reason, "at": _now()}
        )
        self._touch()
        self.progress.save(self.progress_path)

    def _complete_cycle(self) -> None:
        """End of queue: move working NIKs into nik.json, then restart at index 0."""
        logger.info(
            "Reached last NIK — moving %s working NIK(s) into %s, restarting at index 0",
            len(self.working),
            self.main_path.name,
        )
        self._sync_working_to_main()
        self.niks = _unique_preserve(_load_niks(self.main_path))
        self.progress.next_index = 0
        self._save_filtered()
        self.progress.save(self.progress_path)

    def _sync_working_to_main(self) -> None:
        if not self.working:
            return
        main_niks = _unique_preserve(_load_niks(self.main_path))
        merged = _unique_preserve(self.working + main_niks)
        save_main_file(self.main_path, merged)
        self.niks = merged

    def _save_filtered(self) -> None:
        queue = self.niks[self.progress.next_index :]
        save_filtered_file(self.filtered_path, self.working, queue)

    def _touch(self) -> None:
        self.progress.last_run = _now()

    def summary(self) -> str:
        p = self.progress
        at_end = p.next_index >= len(self.niks) if self.niks else False
        return (
            f"Source: {self.main_path.name} ({len(self.niks)} NIKs, loops at end)\n"
            f"Working NIKs saved: {len(self.working)}\n"
            f"Queue remaining (this pass): {self.remaining_count()}\n"
            f"Queue index: {p.next_index}"
            f"{' (at end — next NIK restarts at 0)' if at_end else ''}\n"
            f"Success: {p.success_count}\n"
            f"Skipped: {len(p.skipped_niks)}\n"
            f"Last run: {p.last_run or '-'}"
        )


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
