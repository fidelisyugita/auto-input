from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DOCKER_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


def ensure_playwright_browser() -> None:
    """Chromium is pre-installed in the Playwright Docker base image."""
    pass


def launch_browser(playwright, headless: bool, slow_mo: int = 0):
    opts = {
        "headless": headless,
        "slow_mo": slow_mo,
        "args": DOCKER_CHROMIUM_ARGS,
    }
    browser = playwright.chromium.launch(**opts)
    logger.info("Using Playwright Chromium (headless=%s)", headless)
    return browser
