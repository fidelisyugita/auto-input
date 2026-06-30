from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
LOGIN_URL = "https://subsiditepatlpg.mypertamina.id/merchant-login"
HOMEPAGE_URL = "https://subsiditepatlpg.mypertamina.id/merchant/app"

DEFAULT_QUANTITY_PATTERN = "1,2,2"


def parse_quantity_pattern(raw: str | None) -> list[int]:
    """Parse a string like "1,2,2" into [1, 2, 2]. Falls back to [1]."""
    values: list[int] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            qty = int(chunk)
        except ValueError:
            continue
        if qty >= 1:
            values.append(qty)
    return values or [1]


@dataclass
class Config:
    phone_or_email: str
    pin: str
    nik_file: Path
    headless: bool
    action_delay_ms: int
    test_limit: int
    captcha_wait_seconds: int
    progress_file: Path
    filtered_file: Path
    quantity_pattern: list[int]

    @classmethod
    def from_env(cls) -> "Config":
        phone_or_email = os.getenv("MERCHANT_PHONE_OR_EMAIL", "").strip()
        pin = os.getenv("MERCHANT_PIN", "").strip()
        if not phone_or_email or not pin:
            raise ValueError(
                "Set MERCHANT_PHONE_OR_EMAIL and MERCHANT_PIN in .env "
                "(copy from .env.example)"
            )

        return cls(
            phone_or_email=phone_or_email,
            pin=pin,
            nik_file=BASE_DIR / os.getenv("NIK_FILE", "nik.json"),
            headless=os.getenv("HEADLESS", "false").lower() == "true",
            action_delay_ms=int(os.getenv("ACTION_DELAY_MS", "500")),
            test_limit=int(os.getenv("TEST_LIMIT", "200")),
            captcha_wait_seconds=int(os.getenv("CAPTCHA_WAIT_SECONDS", "120")),
            progress_file=BASE_DIR / "progress.json",
            filtered_file=BASE_DIR / "nik-filtered.json",
            quantity_pattern=parse_quantity_pattern(
                os.getenv("QUANTITY_PATTERN", DEFAULT_QUANTITY_PATTERN)
            ),
        )
