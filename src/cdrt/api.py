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


def manifest_store(*dirs: Path):
    from .records.manifests import ManifestStore
    return ManifestStore(*dirs)


def registry_entries() -> list[dict[str, Any]]:
    from .registry import Registry
    return Registry().describe()


def resolve(profile: dict[str, Any], s: Snapshot, manifests) -> list:
    """Profile → typed, version-bound invocations, one per requirement (pure)."""
    from .registry import Registry
    from .resolver import resolve as _resolve
    return _resolve(profile, s, Registry(), manifests)


def evaluate(invocation, s: Snapshot, manifests) -> dict[str, Any]:
    """One invocation → verdict (pure, no admission)."""
    from .evaluation import evaluate as _evaluate
    return _evaluate(invocation, s, manifests)


def posture(profile: dict[str, Any], invocations: list, verdicts: list[dict[str, Any]], t: str | None = None) -> dict[str, Any]:
    """The posture card a fresh consumer publishes for these verdicts under `profile` (pure)."""
    from .posture import Consumer
    c = Consumer()
    c.activate(profile, {i.leaf: i.binding for i in invocations})
    for v in verdicts:
        c.admit(v, t or "")
    return c.card(t)
