"""Protocol lock (Lab 6; R-LOCK-1 … R-LOCK-5).

protocol.lock.json holds a SHA-256 per component and one root hash over them: the frozen capture bundle,
the fixture build, the oracle, the profiles, the CDRT runtime (src/cdrt, which contains the registered tests
and the harness), the run configuration, uv.lock and the resolved pwexp commit. The workbench is excluded.
Every later lab verifies the lock before it starts and refuses on any mismatch.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pwexp.hashing import manifest_hash, sha256_file, sha256_json, tree_manifest

from . import paths

SKIP = ("__pycache__", ".pyc", ".work")


def tree(p: Path) -> str:
    files = {k: v for k, v in tree_manifest(p).items() if not any(s in k for s in SKIP)}
    return manifest_hash(files)


def lock_file(dev: bool) -> Path:
    return paths.labs_dir(True) / "protocol.lock.json" if dev else paths.root() / "protocol" / "protocol.lock.json"


def fixtures_dir(dev: bool) -> Path:
    return paths.root() / "fixtures" / ("out-dev" if dev else "out")


def git(*args: str, cwd: Path | None = None) -> str:
    p = subprocess.run(["git", *args], cwd=cwd or paths.root(), capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def pwexp_commit() -> dict[str, Any]:
    d = paths.pwexp_checkout()
    return {"commit": git("rev-parse", "HEAD", cwd=d), "tag": git("describe", "--tags", "--exact-match", cwd=d),
            "clean": git("status", "--porcelain", "--untracked-files=no", cwd=d) == ""}


def components(dev: bool) -> dict[str, Any]:
    root = paths.root()
    fx = fixtures_dir(dev)
    return {
        "capture_bundle": tree(paths.bundle_dir(dev)),
        "fixtures": tree(fx),
        "profiles": tree(fx / "profiles"),
        "oracle": tree(root / "oracle"),
        "runtime_src_cdrt": tree(root / "src" / "cdrt"),
        "harness": tree(root / "src" / "cdrt" / "harness"),
        "run_config": sha256_file(root / "protocol" / "run_config.yaml"),
        "uv_lock": sha256_file(root / "uv.lock"),
        "pwexp": pwexp_commit(),
    }


def write(dev: bool, campaign: str) -> dict[str, Any]:
    comps = components(dev)
    doc = {"components": comps, "lock_root": sha256_json(comps), "campaign_id": campaign, "development": dev,
           "git_commit": git("rev-parse", "HEAD"),
           "working_tree_dirty": git("status", "--porcelain", "--untracked-files=no") != "",
           "locked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    f = lock_file(dev)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return doc


def verify(dev: bool) -> tuple[bool, list[str], dict[str, Any] | None]:
    """R-LOCK-2: recompute every component; any difference aborts the run."""
    f = lock_file(dev)
    if not f.exists():
        return False, ["no lock file"], None
    doc = json.loads(f.read_text())
    if sha256_json(doc["components"]) != doc["lock_root"]:
        return False, ["lock file altered"], doc
    now = components(dev)
    diff = [k for k in sorted(set(now) | set(doc["components"])) if now.get(k) != doc["components"].get(k)]
    return not diff, [f"{k} changed since the lock" for k in diff], doc


def oracle_committed_first() -> tuple[bool, str]:
    """R-ORC-1: the oracle expectations were committed before the decision tests."""
    first = lambda path: (git("log", "--reverse", "--format=%H", "--", path).splitlines() or [""])[0]  # noqa: E731
    o, t = first("oracle/expectations.yaml"), first("src/cdrt/tests_registered")
    if not o or not t:
        return False, "expectations or decision tests not committed"
    ok = o != t and subprocess.run(["git", "merge-base", "--is-ancestor", o, t], cwd=paths.root()).returncode == 0
    return ok, f"expectations {o[:8]} · decision tests {t[:8]}"
