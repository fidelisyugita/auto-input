from __future__ import annotations

import json
import os
from pathlib import Path


def data_dir() -> Path:
    path = Path(os.environ.get("DATA_DIR", "/data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return data_dir() / "settings.json"


def default_settings() -> dict:
    return {
        "merchant_phone": os.getenv("MERCHANT_PHONE_OR_EMAIL", ""),
        "merchant_pin": os.getenv("MERCHANT_PIN", ""),
        "nik_file": "nik.json",
        "action_delay_ms": int(os.getenv("ACTION_DELAY_MS", "500")),
        "captcha_wait_seconds": int(os.getenv("CAPTCHA_WAIT_SECONDS", "120")),
        "quantity_pattern": os.getenv("QUANTITY_PATTERN", "1,2,2"),
    }


def load_settings() -> dict:
    path = settings_path()
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        merged = default_settings()
        merged.update(stored)
        return merged
    return default_settings()


def save_settings(settings: dict) -> None:
    current = load_settings()
    current.update(settings)
    settings_path().write_text(
        json.dumps(current, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def nik_path() -> Path:
    settings = load_settings()
    return data_dir() / settings.get("nik_file", "nik.json")


def nik_info() -> dict:
    path = nik_path()
    if not path.exists():
        return {"exists": False, "total": 0, "filename": path.name}
    data = json.loads(path.read_text(encoding="utf-8"))
    niks = data.get("niks", [])
    return {"exists": True, "total": len(niks), "filename": path.name}


def progress_summary() -> str:
    path = data_dir() / "progress.json"
    if not path.exists():
        return "No runs yet."
    try:
        import sys

        bot_core = Path(__file__).resolve().parent.parent / "bot_core"
        if str(bot_core) not in sys.path:
            sys.path.insert(0, str(bot_core))
        from nik_store import NikStore

        settings = load_settings()
        store = NikStore(
            main_path=nik_path(),
            progress_path=path,
            filtered_path=data_dir() / "nik-filtered.json",
        )
        return store.summary()
    except Exception as exc:
        return f"Could not load progress: {exc}"


def tail_log(lines: int = 40) -> str:
    log_path = data_dir() / "automation.log"
    if not log_path.exists():
        return "(no logs yet)"
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:]) if content else "(empty log)"
