from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from enum import Enum

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from browser_setup import launch_browser
from captcha_solver import solve_slider_captcha
from config import Config, HOMEPAGE_URL, LOGIN_URL
from nik_store import NikStore

logger = logging.getLogger(__name__)

NIK_PLACEHOLDER = "Masukkan 16 digit NIK Pelanggan"

SKIP_PATTERNS = [
    "tidak terdaftar",
    "nik tidak ditemukan",
    "tidak ditemukan",
    "harus didaftarkan",
    "sudah mencapai",
    "kuota",
    "tidak berhak",
]

SUCCESS_PATTERNS = [
    "berhasil",
    "sukses",
    "telah dicatat",
    "penjualan berhasil",
    "transaksi berhasil",
    "kirim struk",
    "kembali ke halaman utama",
]


class SaleResult(str, Enum):
    SUCCESS = "success"
    SKIP = "skip"
    STOCK_EMPTY = "stock_empty"
    ERROR = "error"


@dataclass
class SaleOutcome:
    result: SaleResult
    message: str = ""


class MapBot:
    def __init__(self, config: Config, store: NikStore):
        self.config = config
        self.store = store

    def run(
        self,
        limit: int | None = None,
        visible: bool | None = None,
        wait_at_end: bool = False,
    ) -> None:
        show_browser = visible if visible is not None else not self.config.headless
        if show_browser:
            logger.info("Opening visible browser window...")

        with sync_playwright() as p:
            browser = launch_browser(
                p,
                headless=not show_browser,
                slow_mo=300 if show_browser else 0,
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="id-ID",
            )
            page = context.new_page()
            page.set_default_timeout(30000)

            try:
                self._login(page)

                processed = 0
                try:
                    self._process_sales(page, limit, processed)
                except KeyboardInterrupt:
                    logger.info("Stopped by user (Ctrl+C). Progress saved.")

            finally:
                if wait_at_end and show_browser:
                    print("\n>>> Finished. Press Enter to close the browser...")
                    input()
                browser.close()

    def _process_sales(self, page: Page, limit: int | None, processed: int) -> None:
        while True:
            if limit is not None and processed >= limit:
                logger.info("Reached limit (%s NIKs)", limit)
                break

            try:
                self._go_homepage(page)
            except (PlaywrightTimeout, RuntimeError) as exc:
                logger.error("Homepage error: %s — trying to recover...", exc)
                try:
                    self._login(page)
                except Exception:
                    page.goto(HOMEPAGE_URL, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2000)

            stock = self._get_stock(page)
            logger.info(
                "Current stock: %s",
                f"{stock} Tabung" if stock is not None else "unknown",
            )

            if stock is not None and stock <= 0:
                logger.info("Stock is 0. Stopping.")
                break

            nik = self.store.next_nik()
            if nik is None:
                logger.info("No more NIKs in file.")
                break

            outcome = self._try_record_sale(page, nik)
            processed += 1

            if outcome.result == SaleResult.SUCCESS:
                self.store.mark_used(nik)
                logger.info("SUCCESS: %s", nik)
            elif outcome.result == SaleResult.SKIP:
                self.store.mark_skipped(nik, outcome.message)
                logger.info("SKIP: %s - %s", nik, outcome.message)
            elif outcome.result == SaleResult.STOCK_EMPTY:
                self.store.mark_skipped(nik, "stock empty")
                logger.info("Stock empty while processing %s. Stopping.", nik)
                break
            else:
                self.store.mark_skipped(nik, outcome.message or "unknown error")
                logger.error("ERROR: %s - %s", nik, outcome.message)

            self._pause()

    def inspect(self) -> None:
        with sync_playwright() as p:
            browser = launch_browser(p, headless=False, slow_mo=200)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            self._login(page)
            self._open_catat_penjualan(page)
            self._dump_page(page)
            input("\nPress Enter to close browser...")
            browser.close()

    def _pause(self) -> None:
        if self.config.action_delay_ms > 0:
            time.sleep(self.config.action_delay_ms / 1000)

    def _login(self, page: Page) -> None:
        logger.info("Opening login page...")
        page.goto(LOGIN_URL, wait_until="networkidle")
        page.wait_for_timeout(1500)

        if "merchant/app" in page.url:
            logger.info("Already logged in: %s", page.url)
            return

        page.get_by_placeholder("Masukkan Nomor Ponsel atau Email").fill(
            self.config.phone_or_email
        )
        self._pause()
        page.get_by_placeholder("Masukkan nomor PIN Anda").fill(self.config.pin)
        self._pause()
        page.get_by_role("button", name="MASUK").click()

        page.wait_for_url("**/merchant/app**", timeout=60000)
        page.wait_for_timeout(2000)

        if page.get_by_placeholder("Masukkan Nomor Ponsel atau Email").is_visible():
            raise RuntimeError(
                "Login failed. Check MERCHANT_PHONE_OR_EMAIL and MERCHANT_PIN in .env"
            )

        logger.info("Login successful. URL: %s", page.url)

    def _go_homepage(self, page: Page) -> None:
        for attempt in range(3):
            try:
                if "merchant-login" in page.url:
                    self._login(page)
                    return

                page.goto(HOMEPAGE_URL, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(1500)
                self._close_modals(page)

                catat = page.get_by_text("Catat Penjualan", exact=True)
                if catat.is_visible():
                    return
                catat.wait_for(state="visible", timeout=8000)
                return
            except PlaywrightTimeout:
                logger.warning("Homepage not ready, retry %s/3", attempt + 1)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                if attempt == 2:
                    page.reload(wait_until="networkidle")
                    page.wait_for_timeout(2000)

        raise RuntimeError("Could not return to homepage. Run again or use: python3 main.py test --visible")

    def _return_home(self, page: Page) -> None:
        """Close any open dialog and ensure homepage is reachable."""
        self._click_button(page, "KEMBALI KE HALAMAN UTAMA")
        self._click_button(page, "TUTUP")
        self._close_modals(page)
        try:
            self._go_homepage(page)
        except (PlaywrightTimeout, RuntimeError):
            logger.warning("Force-reloading homepage...")
            page.goto(HOMEPAGE_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            self._close_modals(page)

    def _open_catat_penjualan(self, page: Page) -> None:
        self._go_homepage(page)
        logger.info("Clicking Catat Penjualan...")
        page.get_by_text("Catat Penjualan", exact=True).click()
        page.wait_for_timeout(1500)
        page.get_by_placeholder(NIK_PLACEHOLDER).wait_for(state="visible", timeout=10000)
        logger.info("NIK input ready")

    def _close_modals(self, page: Page) -> None:
        for _ in range(10):
            catat = page.get_by_text("Catat Penjualan", exact=True)
            body = page.locator("body").inner_text()
            nik_modal_open = "MASUKKAN NIK KTP" in body or page.get_by_placeholder(
                NIK_PLACEHOLDER
            ).is_visible()

            if catat.is_visible() and not nik_modal_open:
                return

            clicked = False
            for name in [
                "KEMBALI KE HALAMAN UTAMA",
                "TUTUP",
                "UBAH PESANAN",
                "Ganti Pelanggan",
                "Batal",
            ]:
                btn = page.get_by_role("button", name=name)
                if btn.count() > 0 and btn.first.is_visible():
                    try:
                        btn.first.click(timeout=2000)
                        page.wait_for_timeout(800)
                        clicked = True
                        break
                    except PlaywrightTimeout:
                        pass

            if not clicked:
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
                if catat.is_visible() and not page.get_by_placeholder(
                    NIK_PLACEHOLDER
                ).is_visible():
                    return
                break

    def _get_stock(self, page: Page) -> int | None:
        text = page.locator("body").inner_text()
        match = re.search(r"Stok\s*\n?\s*(\d+)\s*Tabung", text, re.I)
        if match:
            return int(match.group(1))
        return None

    def _try_record_sale(self, page: Page, nik: str) -> SaleOutcome:
        logger.info("Trying NIK: %s", nik)
        self._open_catat_penjualan(page)

        page.get_by_placeholder(NIK_PLACEHOLDER).fill("")
        page.get_by_placeholder(NIK_PLACEHOLDER).fill(nik)
        self._pause()
        page.get_by_role("button", name="LANJUTKAN PENJUALAN").click()
        page.wait_for_timeout(2500)

        body = page.locator("body").inner_text()
        if "Pelanggan Tidak Terdaftar" in body or "tidak terdaftar" in body.lower():
            self._click_button(page, "TUTUP")
            self._return_home(page)
            return SaleOutcome(SaleResult.SKIP, "Pelanggan Tidak Terdaftar")

        if self._should_skip(body):
            self._return_home(page)
            return SaleOutcome(SaleResult.SKIP, body[:120])

        if not page.get_by_role("button", name="CEK PESANAN").is_visible():
            self._click_button(page, "TUTUP")
            self._return_home(page)
            return SaleOutcome(SaleResult.SKIP, "NIK not accepted")

        page.get_by_role("button", name="CEK PESANAN").click()
        page.wait_for_timeout(2000)
        page.get_by_role("button", name="PROSES PENJUALAN").click()
        page.wait_for_timeout(2000)

        if page.locator(".rc-slider-captcha").count() > 0:
            if not solve_slider_captcha(page):
                self._return_home(page)
                return SaleOutcome(SaleResult.SKIP, "Captcha solve failed")
            page.wait_for_timeout(1500)

        body = page.locator("body").inner_text()
        if self._is_success(body):
            self._finish_sale(page)
            return SaleOutcome(SaleResult.SUCCESS, "sale recorded")

        if page.get_by_placeholder(NIK_PLACEHOLDER).is_visible():
            self._return_home(page)
            return SaleOutcome(SaleResult.ERROR, "sale not completed")

        self._return_home(page)
        return SaleOutcome(SaleResult.SUCCESS, "sale submitted")

    def _finish_sale(self, page: Page) -> None:
        for name in ["KEMBALI KE HALAMAN UTAMA", "TUTUP", "OK"]:
            btn = page.get_by_role("button", name=name)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(1500)
                return
        self._close_modals(page)

    def _click_button(self, page: Page, name: str) -> bool:
        btn = page.get_by_role("button", name=name)
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            page.wait_for_timeout(1000)
            return True
        return False

    def _should_skip(self, text: str) -> bool:
        lower = text.lower()
        return any(p in lower for p in SKIP_PATTERNS)

    def _is_success(self, text: str) -> bool:
        lower = text.lower()
        return any(p in lower for p in SUCCESS_PATTERNS)

    def _dump_page(self, page: Page) -> None:
        print("\n=== PAGE URL ===")
        print(page.url)
        print("\n=== INPUTS ===")
        for inp in page.locator("input").all():
            print(
                f"  type={inp.get_attribute('type')} "
                f"placeholder={inp.get_attribute('placeholder')} "
                f"id={inp.get_attribute('id')}"
            )
        print("\n=== BUTTONS ===")
        for btn in page.locator("button").all():
            try:
                print(f"  {btn.inner_text()[:60]}")
            except Exception:
                pass
        print("\n=== BODY TEXT (first 1500 chars) ===")
        print(page.locator("body").inner_text()[:1500])
