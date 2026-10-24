"""Locations. CDRT_ROOT overrides the repository root (tests)."""
from __future__ import annotations

import os
from pathlib import Path


def root() -> Path:
    env = os.environ.get("CDRT_ROOT")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[2]


def pwexp_checkout() -> Path:
    """The pinned ProofWeave checkout (git submodule at tag pw-v0.2.0)."""
    return root() / "vendor" / "proofweave-decision-assurance"


def records_root(dev: bool) -> Path:
    """Where pwexp keeps the capture cycles (Stage 1-2 output)."""
    return root() / "capture" / ("records-dev" if dev else "records")


def protocol_file(dev: bool) -> Path:
    return root() / "capture" / ("dev/protocol.yaml" if dev else "cdrt-protocol.yaml")


def bundle_dir(dev: bool) -> Path:
    """The frozen corpus E_C (Lab 4). The real one is committed and read-only."""
    return root() / "capture" / ("bundle-dev" if dev else "bundle")


def labs_dir(dev: bool) -> Path:
    return root() / "results" / ("labs-dev" if dev else "labs")
