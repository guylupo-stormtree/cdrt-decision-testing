"""Control isolation (R-ISO-1): while CDRT reassesses decisions, the capture entry points are replaced by a
guard that counts calls instead of running RepoAudit. The count must stay 0."""
from __future__ import annotations

from contextlib import contextmanager

import pwexp.stages.stage1_acquire as stage1

ENTRY_POINTS = ("run", "_run_repoaudit", "_run_semgrep", "_run_decisions")


class Guard:
    def __init__(self):
        self.calls: list[str] = []

    def _stub(self, name: str):
        def f(*_a, **_k):
            self.calls.append(name)
            raise RuntimeError(f"control isolation: {name} called during reassessment")
        return f


@contextmanager
def disabled_control():
    g, saved = Guard(), {n: getattr(stage1, n) for n in ENTRY_POINTS}
    for n in ENTRY_POINTS:
        setattr(stage1, n, g._stub(n))
    try:
        yield g
    finally:
        for n, f in saved.items():
            setattr(stage1, n, f)
