from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _install_playwright_chromium() -> None:
    logger.info("Downloading Playwright Chromium (one-time setup)...")
    print("Installing Chromium for Playwright... (~170MB, one-time only)")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium", "--force"],
        check=True,
    )
    logger.info("Chromium installed.")


def ensure_playwright_browser() -> None:
    """Pre-flight: install Playwright Chromium if not present in user cache."""
    cache = Path.home() / "Library/Caches/ms-playwright"
    if not cache.exists() or not any(cache.glob("chromium-*")):
        _install_playwright_chromium()


def launch_browser(playwright, headless: bool, slow_mo: int = 0):
    opts = {
        "headless": headless,
        "slow_mo": slow_mo,
        "args": ["--start-maximized"] if not headless else [],
    }

    # Prefer user's installed Google Chrome (no extra download)
    try:
        browser = playwright.chromium.launch(channel="chrome", **opts)
        logger.info("Using Google Chrome")
        return browser
    except Exception as exc:
        logger.debug("Google Chrome not available: %s", exc)

    try:
        return playwright.chromium.launch(**opts)
    except Exception as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        _install_playwright_chromium()
        return playwright.chromium.launch(**opts)
