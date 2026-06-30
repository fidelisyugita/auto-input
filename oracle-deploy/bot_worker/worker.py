from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Ensure bot_core imports resolve
BOT_CORE = Path(__file__).resolve().parent.parent / "bot_core"
sys.path.insert(0, str(BOT_CORE))

from bot import MapBot  # noqa: E402
from config import (  # noqa: E402
    Config,
    DEFAULT_QUANTITY_PATTERN,
    parse_quantity_pattern,
)
from nik_store import NikStore  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(os.environ.get("DATA_DIR", "/data")) / "automation.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def data_dir() -> Path:
    path = Path(os.environ.get("DATA_DIR", "/data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_settings() -> dict:
    settings_path = data_dir() / "settings.json"
    if settings_path.exists():
        return json.loads(settings_path.read_text(encoding="utf-8"))

    return {
        "merchant_phone": os.getenv("MERCHANT_PHONE_OR_EMAIL", ""),
        "merchant_pin": os.getenv("MERCHANT_PIN", ""),
        "nik_file": "nik.json",
        "action_delay_ms": int(os.getenv("ACTION_DELAY_MS", "500")),
        "captcha_wait_seconds": int(os.getenv("CAPTCHA_WAIT_SECONDS", "120")),
        "quantity_pattern": os.getenv("QUANTITY_PATTERN", DEFAULT_QUANTITY_PATTERN),
    }


def build_config(settings: dict) -> Config:
    base = data_dir()
    nik_name = settings.get("nik_file", "nik.json")
    return Config(
        phone_or_email=settings["merchant_phone"].strip(),
        pin=settings["merchant_pin"].strip(),
        nik_file=base / nik_name,
        headless=True,
        action_delay_ms=int(settings.get("action_delay_ms", 500)),
        test_limit=0,
        captcha_wait_seconds=int(settings.get("captcha_wait_seconds", 120)),
        progress_file=base / "progress.json",
        filtered_file=base / "nik-filtered.json",
        quantity_pattern=parse_quantity_pattern(
            settings.get("quantity_pattern", DEFAULT_QUANTITY_PATTERN)
        ),
    )


def main() -> int:
    settings = load_settings()
    if not settings.get("merchant_phone") or not settings.get("merchant_pin"):
        logger.error("Merchant phone/email and PIN are required.")
        return 1

    nik_path = data_dir() / settings.get("nik_file", "nik.json")
    if not nik_path.exists():
        logger.error("NIK file not found: %s", nik_path)
        return 1

    config = build_config(settings)
    store = NikStore(
        main_path=config.nik_file,
        progress_path=config.progress_file,
        filtered_path=config.filtered_file,
    )
    logger.info(store.summary())

    try:
        MapBot(config, store).run(visible=False, wait_at_end=False)
    except Exception:
        logger.exception("Bot run failed")
        return 1

    logger.info("Bot finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
