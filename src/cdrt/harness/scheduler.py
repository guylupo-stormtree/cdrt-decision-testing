"""Delayed-result scheduler (requirements A10.3): verdicts held in a controllable queue.

`hold_leaf(leaf)` is passed to monitor.reassess as its `hold` callback: verdicts for that leaf are queued
instead of admitted. `release(i)` hands the i-th queued verdict to the consumer, at the time the harness
chooses, and returns what admission decided. Nothing else about the verdict changes while it waits.
"""
from __future__ import annotations

from typing import Any, Callable

from ..posture import Consumer


class DelayQueue:
    def __init__(self, consumer: Consumer):
        self.consumer = consumer
        self.queue: list[dict[str, Any]] = []

    def hold_leaf(self, leaf: str) -> Callable[[dict[str, Any]], bool]:
        def hold(v: dict[str, Any]) -> bool:
            if v["binding"]["d"] != leaf:
                return False
            self.queue.append(v)
            return True
        return hold

    def release(self, i: int, t: str) -> tuple[dict[str, Any], bool, str]:
        v = self.queue.pop(i)
        ok, why = self.consumer.admit(v, t)
        return v, ok, why
