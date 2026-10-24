"""A throw-away CDRT root per test: the pinned ProofWeave checkout, the dev capture protocol and the oracle
are linked in."""
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
    (tmp_path / "oracle").symlink_to(REPO / "oracle")
    monkeypatch.setenv("CDRT_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture()
def dev_bundle(cdrt_root):
    """Labs 3 and 4 run in dev mode; returns (book, frozen bundle path)."""
    from cdrt.labs import book
    b = book(dev=True)
    assert b.run(3, progress=lambda m: None).passed
    b.run(4, progress=lambda m: None)
    return b, cdrt_root / "capture" / "bundle-dev"
