"""Stable read façade (R-API-1, R-API-2). The harness uses it internally; the workbench uses nothing else.

API_VERSION is part of the lock: a breaking change needs a new lock. Functions not built yet raise
NotImplementedError and name the build step that adds them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import API_VERSION  # noqa: F401  (re-exported)
from .records import view as _view
from .records.view import IntegrityFinding, Snapshot  # noqa: F401


def load_snapshot(corpus: Path, target: Path, expected_corpus_sha256: str | None = None,
                  allow_synthetic: bool = False) -> Snapshot:
    return _view.load_snapshot(corpus, target, expected_corpus_sha256, allow_synthetic)


def get_decision(s: Snapshot, decision_id: str) -> dict[str, Any]:
    return _view.get_decision(s, decision_id)


def list_decisions(s: Snapshot) -> list[str]:
    return _view.list_decisions(s)


def export_decision_dot(s: Snapshot, decision_id: str, path: Path) -> Path:
    from pwexp.proofweave.export_dot import export_decision
    return export_decision(s.store, Path(path), decision_id)


def _later(step: str):
    def f(*_a, **_k):
        raise NotImplementedError(f"added in build step {step}")
    return f


registry_entries = _later("B3")
resolve = _later("B3")      # resolve(profile) -> invocations
evaluate = _later("B3")     # evaluate(invocation, view) -> verdict (pure, no admission)
posture = _later("B3")      # posture(profile, verdicts) -> posture card (pure)
