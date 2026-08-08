"""Cosine learning rate scheduler with linear warmup (P0.3)."""

from __future__ import annotations

import math


class CosineWarmupScheduler:
    """Cosine learning rate scheduler with warmup."""

    def __init__(
        self,
        base_lr: float = 3e-4,
        min_lr: float = 3e-5,
        warmup_steps: int = 100,
        max_steps: int = 1000,
    ) -> None:
        self.base_lr = base_lr
        self.min_lr = min_lr
        self.warmup_steps = warmup_steps
        self.max_steps = max_steps

    def get_lr(self, step: int) -> float:
        if step < self.warmup_steps:
            return self.base_lr * float(step) / float(max(1, self.warmup_steps))
        if step >= self.max_steps:
            return self.min_lr
        progress = float(step - self.warmup_steps) / float(max(1, self.max_steps - self.warmup_steps))
        cosine_decay = 0.5 * (1.0 + math.cos(math.pi * progress))
        return self.min_lr + (self.base_lr - self.min_lr) * cosine_decay
