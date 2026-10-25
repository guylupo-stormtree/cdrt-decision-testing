"""Code fingerprints (R-ISO-2): the control guard, resolver, executor, record view and posture consumer must be
byte-identical before and after test registration and before and after every requirement change."""
from __future__ import annotations

from pathlib import Path

from pwexp.hashing import sha256_file, sha256_json

PKG = Path(__file__).resolve().parents[1]
MODULES = ("control_guard.py", "resolver/__init__.py", "executor/__init__.py", "records/view.py",
           "records/assessments.py", "posture/__init__.py", "taip_stub.py", "evaluation.py", "monitor.py")


def fingerprint() -> str:
    return sha256_json({m: sha256_file(PKG / m) for m in MODULES})
