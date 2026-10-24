"""A throw-away CDRT root per test: the pinned ProofWeave checkout and the dev capture protocol are linked in."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]


@pytest.fixture()
def cdrt_root(tmp_path, monkeypatch):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "proofweave-decision-assurance").symlink_to(REPO / "vendor" / "proofweave-decision-assurance")
    (tmp_path / "capture").mkdir()
    (tmp_path / "capture" / "dev").symlink_to(REPO / "capture" / "dev")
    monkeypatch.setenv("CDRT_ROOT", str(tmp_path))
    return tmp_path
