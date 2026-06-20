from __future__ import annotations

import base64
import logging
import random

import cv2
import numpy as np
from playwright.sync_api import Page

logger = logging.getLogger(__name__)


def _decode_image(data_url: str) -> np.ndarray:
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def find_gap_x(bg_data_url: str, puzzle_data_url: str) -> int:
    """Return horizontal offset (px) where the puzzle piece fits the background."""
    bg = _decode_image(bg_data_url)
    puzzle = _decode_image(puzzle_data_url)
    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    puzzle_gray = cv2.cvtColor(puzzle, cv2.COLOR_BGR2GRAY)

    ph, pw = puzzle_gray.shape
    trim = 5
    puzzle_inner = puzzle_gray[trim : ph - trim, trim : pw - trim]
    result = cv2.matchTemplate(bg_gray, puzzle_inner, cv2.TM_CCOEFF_NORMED)
    _, confidence, _, max_loc = cv2.minMaxLoc(result)
    gap_x = max_loc[0] + trim
    logger.debug("Captcha gap x=%s confidence=%.3f", gap_x, confidence)
    return gap_x


def _drag_slider(page: Page, distance: float) -> None:
    button = page.locator(".rc-slider-captcha-button").first
    box = button.bounding_box()
    if not box:
        raise RuntimeError("Captcha slider button not found")

    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.wait_for_timeout(100)
    page.mouse.down()

    steps = 30
    for i in range(1, steps + 1):
        progress = 1 - (1 - i / steps) ** 2
        page.mouse.move(
            start_x + distance * progress,
            start_y + random.randint(-1, 1),
        )
        page.wait_for_timeout(12)

    page.mouse.up()


def _captcha_solved(page: Page) -> bool:
    if page.locator(".rc-slider-captcha").count() == 0:
        return True
    captcha = page.locator(".rc-slider-captcha").first
    if not captcha.is_visible():
        return True
    if page.locator(".rc-slider-captcha-success").count() > 0:
        return True
    body = page.locator("body").inner_text().lower()
    return any(
        k in body
        for k in ("kirim struk", "kembali ke halaman utama", "berhasil", "sukses")
    )


def _click_ganti(page: Page) -> bool:
    ganti = page.get_by_text("Ganti", exact=True)
    if ganti.count() > 0 and ganti.first.is_visible():
        ganti.first.click()
        page.wait_for_timeout(1500)
        return True
    return False


def solve_slider_captcha(page: Page, max_attempts: int = 5) -> bool:
    """Auto-slide the rc-slider-captcha puzzle. Returns True if solved."""
    if page.locator(".rc-slider-captcha").count() == 0:
        return True

    logger.info("Solving slide captcha...")
    offsets = [0, -3, 3, -6, 6, -9, 9]

    for attempt in range(max_attempts):
        page.locator(".rc-slider-captcha-jigsaw-bg").first.wait_for(
            state="visible", timeout=5000
        )

        for off in offsets:
            bg_src = page.locator(".rc-slider-captcha-jigsaw-bg").first.get_attribute(
                "src"
            )
            puzzle_src = page.locator(
                ".rc-slider-captcha-jigsaw-puzzle"
            ).first.get_attribute("src")
            if not bg_src or not puzzle_src:
                return False

            gap_x = find_gap_x(bg_src, puzzle_src)
            _drag_slider(page, gap_x + off)
            page.wait_for_timeout(2000)

            if _captcha_solved(page):
                logger.info("Captcha solved")
                return True

            if off != offsets[-1]:
                _click_ganti(page)

        if attempt < max_attempts - 1:
            _click_ganti(page)

    logger.warning("Captcha solve failed after %s attempts", max_attempts)
    return False
