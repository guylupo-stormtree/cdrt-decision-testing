"""Capture support for Labs 0-2: the authors' declaration, the target snapshot, the scope manifests, the
generated ProofWeave capture protocol, the pilot threshold rule and the pwexp command line.

Everything the authors declare lives in capture/capture.yaml. Lab 0 fetches the target at its commit, drafts
the two manifests from our own `ast` parse (never from RepoAudit output) for a person to review and approve,
and writes the policy and the protocol. Lab 1 runs the pilot, sets tau_h by the declared rule and locks the
protocol; Lab 2 runs the locked campaign. RepoAudit is driven only through the pwexp command line (R-CAP-1).
API keys are passed to pwexp on standard input and are never written anywhere.
"""
from __future__ import annotations

import ast
import fnmatch
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

import yaml

from pwexp.hashing import manifest_hash, sha256_file, tree_manifest

from . import paths

PROVIDERS = ("openai", "anthropic")
# Rehearsal only: CDRT_REHEARSAL_LOCAL=<OpenAI-compatible base URL> allows pwexp's dev-only "local" provider, so
# Labs 0-1 can be rehearsed with a local model. pwexp refuses to lock or run a campaign with it; never a result.
REHEARSAL = os.environ.get("CDRT_REHEARSAL_LOCAL", "")


def model_args(cfg: dict[str, Any]) -> list[str]:
    m = cfg["model"]
    return ["--model", f"{m['provider']}:{m['model']}"] + (["--base-url", REHEARSAL] if m["provider"] == "local" else [])


class CaptureError(Exception):
    pass


# ------------------------------------------------------------------ declaration
def capture_dir() -> Path:
    return paths.root() / "capture"


def declaration() -> dict[str, Any]:
    f = capture_dir() / "capture.yaml"
    if not f.exists():
        raise CaptureError(f"{f} not found")
    return yaml.safe_load(f.read_text()) or {}


def problems(cfg: dict[str, Any]) -> list[str]:
    out = []

    def todo(v: Any) -> bool:
        return v is None or v == "" or (isinstance(v, str) and v.strip().upper().startswith("TODO"))
    t, m, r = cfg.get("target") or {}, cfg.get("model") or {}, cfg.get("runs") or {}
    for k, v in (("target.repository", t.get("repository")), ("target.commit", t.get("commit")),
                 ("model.provider", m.get("provider")), ("model.model", m.get("model")),
                 ("runs.campaign", r.get("campaign"))):
        if todo(v):
            out.append(f"{k} is not set")
    if not todo(m.get("provider")) and m.get("provider") not in PROVIDERS + (("local",) if REHEARSAL else ()):
        out.append(f"model.provider must be one of {', '.join(PROVIDERS)}")
    if not todo(t.get("commit")) and not re.fullmatch(r"[0-9a-f]{40}", str(t.get("commit"))):
        out.append("target.commit must be a full 40-character commit SHA")
    for k in ("pilot", "campaign", "semgrep_standalone"):
        v = r.get(k)
        if not todo(v) and (not isinstance(v, int) or isinstance(v, bool) or v < (0 if k == "semgrep_standalone" else 1)):
            out.append(f"runs.{k} must be a positive integer")
    if cfg.get("bug_type", "NPD") != "NPD":
        out.append("bug_type must be NPD (RepoAudit's null-pointer detector)")
    if not re.fullmatch(r"[+-]\d\d:\d\d", str(cfg.get("log_utc_offset", ""))):
        out.append('log_utc_offset must look like "+00:00"')
    return out


def host_utc_offset() -> str:
    z = datetime.now().astimezone().strftime("%z")
    return f"{z[:3]}:{z[3:]}"


# ------------------------------------------------------------------ target snapshot
def target_dir() -> Path:
    return capture_dir() / "target"


def fetch_target(url: str, commit: str, progress: Callable[[str], None] = print) -> Path:
    """The target at exactly `commit`, as a plain file tree (no .git), in capture/target/."""
    dst = target_dir()
    stamp = dst / ".cdrt-target.json"
    if stamp.exists() and json.loads(stamp.read_text()).get("commit") == commit:
        return dst
    work = capture_dir() / ".target-clone"
    shutil.rmtree(work, ignore_errors=True)
    progress(f"fetching {url} at {commit[:12]}")
    run = lambda *c: subprocess.run(list(c), cwd=work if work.exists() else None, capture_output=True, text=True)  # noqa: E731
    p = run("git", "clone", "--quiet", "--no-checkout", url, str(work))
    if p.returncode != 0:
        raise CaptureError(f"git clone failed: {p.stderr.strip()[-300:]}")
    p = run("git", "checkout", "--quiet", commit)
    if p.returncode != 0:
        raise CaptureError(f"commit {commit} not found: {p.stderr.strip()[-300:]}")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(work, dst, ignore=shutil.ignore_patterns(".git"))
    shutil.rmtree(work, ignore_errors=True)
    stamp.write_text(json.dumps({"repository": url, "commit": commit}) + "\n")
    return dst


def licence(target: Path) -> str | None:
    for p in sorted(target.iterdir()):
        if p.is_file() and re.match(r"(?i)(licen[cs]e|copying)(\.|$)", p.name):
            first = next((l.strip() for l in p.read_text(errors="replace").splitlines() if l.strip()), "")
            return f"{p.name}: {first[:80]}"
    return None


def snapshot_sha256(target: Path) -> str:
    return manifest_hash({k: v for k, v in tree_manifest(target).items() if k != ".cdrt-target.json"})


# ------------------------------------------------------------------ manifests (D-005)
def _call_name(n: ast.Call) -> str | None:
    f = n.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _may_be_none(e: ast.AST | None) -> bool:
    """The expression can evaluate to the None literal: None itself, or a branch of `a if c else b` / `a or b`.
    A None inside a comparison (`x is None`) is not a returned None."""
    if isinstance(e, ast.Constant):
        return e.value is None
    if isinstance(e, ast.IfExp):
        return _may_be_none(e.body) or _may_be_none(e.orelse)
    if isinstance(e, ast.BoolOp):
        return any(_may_be_none(v) for v in e.values)
    return False


def _returns_none(fn: ast.AST) -> bool:
    return any(isinstance(n, ast.Return) and _may_be_none(n.value) for n in ast.walk(fn))


def draft_manifests(target: Path, exclude: list[str]) -> dict[str, Any]:
    """Functions that can receive a None from another function, from our own parse of the target.

    sources  functions that return a None literal (alone or inside the returned expression)
    M_h      their callers: functions that receive a None as a callee's return value
    M_q      M_h, plus functions passed a literal None as an argument, plus the callers of functions in M_h
             that can return a None themselves (the None travels one more step)
    Only function names that are unique in the target are used, as ProofWeave resolves them."""
    defs: dict[str, list[tuple[str, ast.AST]]] = {}
    for p in sorted(target.rglob("*.py")):
        rel = p.relative_to(target).as_posix()
        if any(fnmatch.fnmatch(rel, g) for g in exclude):
            continue
        try:
            tree = ast.parse(p.read_text(errors="replace"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.setdefault(n.name, []).append((rel, n))
    unique = {name: (rel, n) for name, v in defs.items() if len(v) == 1 for rel, n in v}
    fid = lambda name: f"{unique[name][0]}::{name}"  # noqa: E731
    sources = {name for name, (_, n) in unique.items() if _returns_none(n)}
    callers: dict[str, set[str]] = {}
    arg_none: set[str] = set()
    for name, (_, fn) in unique.items():
        for c in ast.walk(fn):
            if not isinstance(c, ast.Call):
                continue
            callee = _call_name(c)
            if callee in unique and callee != name:
                callers.setdefault(callee, set()).add(name)
                if any(isinstance(a, ast.Constant) and a.value is None for a in [*c.args, *(k.value for k in c.keywords)]):
                    arg_none.add(callee)
    m_h = {c for s in sources for c in callers.get(s, ())}
    onward = {c for f in m_h & sources for c in callers.get(f, ())}
    m_q = m_h | arg_none | onward
    return {"sources": sorted(fid(n) for n in sources), "M_h": sorted(fid(n) for n in m_h),
            "M_q": sorted(fid(n) for n in m_q), "functions_parsed": len(unique),
            "ambiguous_names_skipped": sorted(n for n, v in defs.items() if len(v) > 1)}


def manifest_dir() -> Path:
    return capture_dir() / "manifests"


def write_drafts(d: dict[str, Any], cfg: dict[str, Any]) -> Path:
    out = manifest_dir() / "drafts"
    out.mkdir(parents=True, exist_ok=True)
    t = cfg["target"]
    for name, about in (("M_h", "Auditor scope: functions that receive a None as a callee's return value."),
                        ("M_q", "Release scope: M_h, functions passed a None as an argument, and callers one step "
                                "further where the None can travel on.")):
        doc = {"id": name, "about": about, "target": {"repository": t["repository"], "commit": t["commit"]},
               "derivation": "cdrt capture.draft_manifests: own ast parse of the target, never RepoAudit output",
               "functions": d[name]}
        (out / f"{name}.json").write_text(json.dumps(doc, indent=2) + "\n")
    return out


def approve(by: str) -> dict[str, Any]:
    """A person approves the reviewed drafts (possibly edited): they become the manifests, with a record."""
    drafts = manifest_dir() / "drafts"
    if not (drafts / "M_h.json").exists():
        raise CaptureError("no drafts to approve: run Lab 0 first")
    docs = {n: json.loads((drafts / f"{n}.json").read_text()) for n in ("M_h", "M_q")}
    if not set(docs["M_h"]["functions"]) <= set(docs["M_q"]["functions"]):
        raise CaptureError("M_h must be a subset of M_q")
    for n, doc in docs.items():
        (manifest_dir() / f"{n}.json").write_text(json.dumps(doc, indent=2) + "\n")
    rec = {"approved_by": by, "approved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "files": {f"{n}.json": sha256_file(manifest_dir() / f"{n}.json") for n in docs},
           "sizes": {n: len(d["functions"]) for n, d in docs.items()}}
    (manifest_dir() / "REVIEW.json").write_text(json.dumps(rec, indent=2) + "\n")
    return rec


def approval_status() -> tuple[bool, str]:
    f = manifest_dir() / "REVIEW.json"
    if not f.exists():
        return False, "not yet reviewed and approved"
    rec = json.loads(f.read_text())
    for name, h in rec["files"].items():
        p = manifest_dir() / name
        if not p.exists() or sha256_file(p) != h:
            return False, f"{name} changed after approval: approve again"
    return True, f"approved by {rec['approved_by']} at {rec['approved_at']} (M_h {rec['sizes']['M_h']}, M_q {rec['sizes']['M_q']})"


# ------------------------------------------------------------------ policy and protocol
def write_policy(dir_: Path, tau_h: Fraction | None, manifest_rel: str) -> Path:
    """P1@1: base-check on at least tau_h of M_h. Before the pilot, tau_h is 0 (pilot only, never a result)."""
    t = tau_h if tau_h is not None else Fraction(0)
    doc = {"id": "P1", "version": 1, "validators": ["base-check"],
           "threshold": {"numerator": t.numerator, "denominator": t.denominator},
           "manifest": {"file": manifest_rel, "sha256": sha256_file(manifest_dir() / "M_h.json")},
           **({} if tau_h is not None else {"note": "PILOT ONLY: tau_h is set from the pilot before the capture lock"})}
    (dir_ / "policies").mkdir(parents=True, exist_ok=True)
    f = dir_ / "policies" / "P1@1.json"
    f.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return f


def protocol(cfg: dict[str, Any], where: Path, count: int, semgrep_runs: int) -> dict[str, Any]:
    """A pwexp decision protocol (DR-23) at `where` (relative paths resolve against it)."""
    rel = lambda p: os.path.relpath(p, where)  # noqa: E731
    t = cfg["target"]
    return {
        "protocol_version": 1,
        "target": {"repository": t["repository"], "commit": t["commit"], "language": "Python", "bug_type": "NPD",
                   "snapshot_path": rel(target_dir())},
        "green_mapping": "DR-11",
        "capture": {"log_utc_offset": cfg["log_utc_offset"]},
        "acquisition": {"temperature": 0.0, "call_depth": 3, "workers": 4, "timeout_s": 3600,
                        "semgrep_runs": semgrep_runs,
                        "models": [{"provider": cfg["model"]["provider"], "model": cfg["model"]["model"]}]},
        "semgrep": {"version": "1.181.0",
                    "ruleset": rel(paths.pwexp_checkout() / "protocol" / "semgrep-rules" / "python-none-deref.yaml")},
        "timing": {"reference_threshold_s": 5, "repetitions": 1, "volumes": [10], "durability": "fsync-per-bundle"},
        "manifests": {"M_h": {"file": rel(manifest_dir() / "M_h.json")}, "M_q": {"file": rel(manifest_dir() / "M_q.json")}},
        "policies": {"P1@1": {"file": "policies/P1@1.json"}},
        "decisions": {"seed": int(cfg["seed"]),
                      "intent": {"action": "release", "repo": t["repository"], "commit": t["commit"], "bug_type": "NPD",
                                 "scope": rel(manifest_dir() / "M_h.json"), "requested_by": cfg["requested_by"]},
                      "groups": [{"group": "G-main", "control": "repoaudit", "basis": ["repoaudit"], "policy": "P1@1",
                                  "rule": "DR-11", "count": count}]},
    }


def write_protocol(cfg: dict[str, Any], where: Path, count: int, semgrep_runs: int, tau_h: Fraction | None) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    write_policy(where, tau_h, os.path.relpath(manifest_dir() / "M_h.json", where))
    f = where / ("cdrt-protocol.yaml" if where == capture_dir() else "protocol.yaml")
    f.write_text("# GENERATED by cdrt (Labs 0-1) from capture/capture.yaml and the approved manifests. Do not edit.\n"
                 + yaml.safe_dump(protocol(cfg, where, count, semgrep_runs), sort_keys=False))
    return f


# ------------------------------------------------------------------ the declared pilot rule (R-CAP-4)
def tau_h_rule(coverages: list[Fraction], n_runs: int, step: int = 20) -> tuple[Fraction | None, int]:
    """The largest multiple of 1/step at which at least ceil(0.8 n) of the n pilot runs would conform.
    `coverages`: the M_h coverage of each GREEN pilot decision. Returns (tau_h or None, runs needed)."""
    need = math.ceil(0.8 * n_runs)
    ranked = sorted(coverages, reverse=True)
    if len(ranked) < need:
        return None, need
    c = ranked[need - 1]
    return Fraction(math.floor(step * c), step), need


# ------------------------------------------------------------------ pwexp
def pwexp(records_root: Path, proto: Path, *args: str, key: str | None = None,
          progress: Callable[[str], None] | None = None) -> tuple[int, str]:
    """Run the pinned pwexp command line; the key, if any, goes on standard input (never argv or env)."""
    cmd = [sys.executable, "-m", "pwexp.cli", "--records-root", str(records_root), "--protocol", str(proto), *args]
    env = {k: v for k, v in os.environ.items() if not k.startswith("PWEXP_") and not k.endswith("_API_KEY")}
    if REHEARSAL:
        env["PWEXP_DEV"] = "1"
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    try:
        p.stdin.write((key + "\n") if key else "")
        p.stdin.close()
        lines = []
        for line in p.stdout:
            lines.append(line.rstrip("\n"))
            if progress:
                progress(line.rstrip("\n"))
        p.wait()
    finally:
        if p.poll() is None:
            p.kill()
    return p.returncode, "\n".join(lines)


def model_check(provider: str, model: str, key: str) -> tuple[bool, str]:
    rc, out = pwexp(capture_dir() / "records", capture_dir() / "capture.yaml", "model-check",
                    *model_args({"model": {"provider": provider, "model": model}}), "--key-stdin", key=key)
    return rc == 0, out.strip().splitlines()[-1] if out.strip() else f"exit {rc}"


def new_cycle(records_root: Path, proto: Path, mode: str) -> str:
    rc, out = pwexp(records_root, proto, "cycle", "new", "--mode", mode)
    m = re.search(r"created (\S+)", out)
    if rc != 0 or not m:
        raise CaptureError(f"pwexp cycle new failed: {out.strip()[-300:]}")
    return m.group(1)
