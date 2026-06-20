from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class RunnerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class BotRunner:
    _process: subprocess.Popen | None = field(default=None, init=False)
    _state: RunnerState = field(default=RunnerState.IDLE, init=False)
    _last_exit_code: int | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def state(self) -> RunnerState:
        with self._lock:
            self._refresh()
            return self._state

    @property
    def last_exit_code(self) -> int | None:
        return self._last_exit_code

    def _refresh(self) -> None:
        if self._process is None:
            return
        code = self._process.poll()
        if code is None:
            self._state = RunnerState.RUNNING
            return
        self._last_exit_code = code
        self._process = None
        if self._state == RunnerState.STOPPING:
            self._state = RunnerState.STOPPED
        elif code == 0:
            self._state = RunnerState.STOPPED
        else:
            self._state = RunnerState.FAILED

    def is_running(self) -> bool:
        return self.state == RunnerState.RUNNING

    def start(self) -> tuple[bool, str]:
        with self._lock:
            self._refresh()
            if self._process is not None and self._process.poll() is None:
                return False, "Bot is already running."

            worker = Path("/app/bot_worker/worker.py")
            if not worker.exists():
                worker = Path(__file__).resolve().parent.parent / "bot_worker" / "worker.py"
            env = os.environ.copy()
            env.setdefault("DATA_DIR", "/data")
            env["HEADLESS"] = "true"
            env["PYTHONPATH"] = f"/app/bot_core:/app"

            self._process = subprocess.Popen(
                [sys.executable, str(worker)],
                cwd="/app",
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self._state = RunnerState.RUNNING
            self._last_exit_code = None
            threading.Thread(target=self._watch_output, daemon=True).start()
            return True, "Bot started."

    def _watch_output(self) -> None:
        proc = self._process
        if proc is None or proc.stdout is None:
            return
        log_path = Path(os.environ.get("DATA_DIR", "/data")) / "automation.log"
        for line in proc.stdout:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            self._refresh()
            if self._process is None or self._process.poll() is not None:
                return False, "Bot is not running."

            self._state = RunnerState.STOPPING
            proc = self._process
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            self._refresh()
            return True, "Bot stopped."

    def status_dict(self) -> dict:
        state = self.state
        return {
            "state": state.value,
            "running": state == RunnerState.RUNNING,
            "last_exit_code": self._last_exit_code,
        }


runner = BotRunner()
