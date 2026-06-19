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
from nik_store import NikStore, Progress


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
    print("Setup complete. Run: python3 main.py test")


def cmd_test(config: Config) -> None:
    ensure_playwright_browser()
    config.headless = False
    store = NikStore(config.nik_file, config.progress_file)
    logging.info("TEST MODE - visible browser, limit %s NIKs", config.test_limit)
    logging.info(store.summary())
    MapBot(config, store).run(limit=config.test_limit, visible=True)


def cmd_run(config: Config) -> None:
    ensure_playwright_browser()
    config.headless = True
    store = NikStore(config.nik_file, config.progress_file)
    logging.info("AUTOMATION MODE - headless, until stock = 0")
    logging.info(store.summary())
    MapBot(config, store).run()


def cmd_inspect(config: Config) -> None:
    ensure_playwright_browser()
    store = NikStore(config.nik_file, config.progress_file)
    logging.info("INSPECT MODE - login and dump page elements")
    MapBot(config, store).inspect()


def cmd_status(config: Config) -> None:
    store = NikStore(config.nik_file, config.progress_file)
    print(store.summary())
    if store.progress.skipped_niks:
        print("\nLast 5 skipped:")
        for item in store.progress.skipped_niks[-5:]:
            print(f"  {item['nik']}: {item['reason']}")


def cmd_reset(config: Config) -> None:
    if config.progress_file.exists():
        config.progress_file.unlink()
    print("Progress reset. Will start from first NIK again.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automate Catat Penjualan on Subsidi Tepat MAP"
    )
    parser.add_argument(
        "command",
        choices=["test", "run", "inspect", "status", "reset", "setup"],
        help=(
            "test=visible browser limited NIKs | "
            "run=full headless automation | "
            "inspect=debug page elements | "
            "status=show progress | "
            "reset=clear progress | "
            "setup=install dependencies and browser"
        ),
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
            config = Config(
                phone_or_email="",
                pin="",
                nik_file=Path("nik.json"),
                headless=True,
                action_delay_ms=500,
                test_limit=100,
                captcha_wait_seconds=120,
                progress_file=Path("progress.json"),
            )
            if args.command == "status":
                cmd_status(config)
                return
            cmd_reset(config)
            return
        print(f"Error: {exc}")
        print("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    commands = {
        "test": cmd_test,
        "run": cmd_run,
        "inspect": cmd_inspect,
        "status": cmd_status,
        "reset": cmd_reset,
    }
    commands[args.command](config)


if __name__ == "__main__":
    main()
