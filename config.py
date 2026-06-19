import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
LOGIN_URL = "https://subsiditepatlpg.mypertamina.id/merchant-login"
HOMEPAGE_URL = "https://subsiditepatlpg.mypertamina.id/merchant/app"


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
        )
