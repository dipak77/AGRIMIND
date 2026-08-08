"""Laptop training controller — session limits, safe stop, resume (P1.18)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class LaptopTrainingController:
    max_session_minutes: float = 60.0
    checkpoint_interval_minutes: float = 10.0
    checkpoint_interval_tokens: int = 1_000_000
    max_gpu_memory_gb: float | None = None

    _start: float = field(default_factory=time.monotonic, init=False)
    _last_ckpt: float = field(default_factory=time.monotonic, init=False)
    _tokens_since_ckpt: int = field(default=0, init=False)
    _paused: bool = field(default=False, init=False)
    _stop_requested: bool = field(default=False, init=False)

    def request_stop(self) -> None:
        self._stop_requested = True

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def note_tokens(self, n: int) -> None:
        self._tokens_since_ckpt += max(0, n)

    def session_elapsed_minutes(self) -> float:
        return (time.monotonic() - self._start) / 60.0

    def should_stop(self) -> bool:
        if self._stop_requested:
            return True
        return self.session_elapsed_minutes() >= self.max_session_minutes

    def should_checkpoint(self) -> bool:
        if self._paused:
            return False
        mins = (time.monotonic() - self._last_ckpt) / 60.0
        if mins >= self.checkpoint_interval_minutes:
            return True
        if self._tokens_since_ckpt >= self.checkpoint_interval_tokens:
            return True
        return False

    def mark_checkpoint_done(self) -> None:
        self._last_ckpt = time.monotonic()
        self._tokens_since_ckpt = 0

    def run_step_loop(
        self,
        step_fn: Callable[[], int],
        on_checkpoint: Callable[[], None] | None = None,
        max_steps: int | None = None,
    ) -> dict[str, int | float | bool]:
        """
        Call step_fn() repeatedly; it returns tokens consumed this step.
        Stops on session limit or request_stop.
        """
        steps = 0
        while not self.should_stop():
            if self._paused:
                time.sleep(0.05)
                continue
            tokens = step_fn()
            self.note_tokens(int(tokens))
            steps += 1
            if self.should_checkpoint() and on_checkpoint:
                on_checkpoint()
                self.mark_checkpoint_done()
            if max_steps is not None and steps >= max_steps:
                break
        return {
            "steps": steps,
            "elapsed_minutes": self.session_elapsed_minutes(),
            "stopped": self.should_stop(),
        }
