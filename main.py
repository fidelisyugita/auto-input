#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from bot import MapBot
from browser_setup import ensure_playwright_browser
from config import Config


def make_store(config: Config):
    from nik_store import NikStore

    return NikStore(
        main_path=config.nik_file,
        progress_path=config.progress_file,
        filtered_path=config.filtered_file,
    )


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("automation.log", encoding="utf-8"),
        ],
    )


def cmd_setup() -> None:
    print("Installing Python packages...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        check=True,
        cwd=Path(__file__).parent,
    )
    print("Installing Playwright Chromium browser...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium", "--force"],
        check=True,
    )
    print("Setup complete.")
    print("  Headless:  python3 main.py run")
    print("  Visible:   python3 main.py run --visible")


def cmd_test(config: Config, limit: int | None = None) -> None:
    ensure_playwright_browser()
    store = make_store(config)
    effective_limit = limit if limit is not None else config.test_limit
    if effective_limit == 0:
        effective_limit = None
        logging.info(
            "TEST MODE - visible browser, until stock=0 or Ctrl+C (no limit)"
        )
    else:
        logging.info(
            "TEST MODE - visible browser, up to %s NIKs (Ctrl+C to stop early)",
            effective_limit,
        )
    logging.info(store.summary())
    MapBot(config, store).run(
        limit=effective_limit, visible=True, wait_at_end=True
    )


def cmd_run(config: Config, visible: bool) -> None:
    ensure_playwright_browser()
    store = make_store(config)
    mode = "visible browser" if visible else "headless"
    logging.info("RUN MODE (%s) - until stock = 0", mode)
    logging.info(store.summary())
    MapBot(config, store).run(visible=visible, wait_at_end=False)


def cmd_inspect(config: Config) -> None:
    ensure_playwright_browser()
    store = make_store(config)
    logging.info("INSPECT MODE - login and dump page elements")
    MapBot(config, store).inspect()


def cmd_status(config: Config) -> None:
    store = make_store(config)
    print(store.summary())
    if store.progress.skipped_niks:
        print("\nLast 5 skipped:")
        for item in store.progress.skipped_niks[-5:]:
            print(f"  {item['nik']}: {item['reason']}")


def cmd_reset(config: Config) -> None:
    if config.progress_file.exists():
        config.progress_file.unlink()
    print("Progress reset. Will start from first NIK again.")
    print("Note: nik-filtered.json is kept. Delete it manually to rebuild from scratch.")


def _fallback_config() -> Config:
    return Config(
        phone_or_email="",
        pin="",
        nik_file=Path("nik.json"),
        headless=True,
        action_delay_ms=500,
        test_limit=200,
        captcha_wait_seconds=120,
        progress_file=Path("progress.json"),
        filtered_file=Path("nik-filtered.json"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automate Catat Penjualan on Subsidi Tepat MAP"
    )
    parser.add_argument(
        "command",
        choices=["test", "run", "inspect", "status", "reset", "setup"],
        help=(
            "test=visible browser (default 200 NIKs, Ctrl+C to stop) | "
            "run=full automation (add --visible to watch live) | "
            "inspect=debug page | status=progress | reset=clear progress"
        ),
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Open browser window (use with: run --visible)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max NIKs for test mode (0 = no limit). Default: TEST_LIMIT from .env (200)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command == "setup":
        cmd_setup()
        return

    try:
        config = Config.from_env()
    except ValueError as exc:
        if args.command in ("status", "reset"):
            config = _fallback_config()
            if args.command == "status":
                cmd_status(config)
                return
            cmd_reset(config)
            return
        print(f"Error: {exc}")
        print("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    if args.command == "test":
        cmd_test(config, limit=args.limit)
    elif args.command == "run":
        cmd_run(config, visible=args.visible)
    elif args.command == "inspect":
        cmd_inspect(config)
    elif args.command == "status":
        cmd_status(config)
    elif args.command == "reset":
        cmd_reset(config)


if __name__ == "__main__":
    main()
