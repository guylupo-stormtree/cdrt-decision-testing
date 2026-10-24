"""Lab framework: each lab reads the previous lab's hand-off, runs fixed checks, and seals its own hand-off.

  results/labs[-dev]/state.json              current status per lab
  results/labs[-dev]/lab-log.jsonl           hash-chained record of every attempt (passed or failed)
  results/labs[-dev]/lab<N>/attempt<k>/      that attempt's outputs, handoff.json and card.txt

A lab passes only when every check passes. A check whose code is not built yet is shown as "not built yet"
and keeps the lab from passing. Re-running a lab invalidates every later lab. Passing a lab means the run
was complete and intact; the result it reports is whatever it is (requirements A1, R-LOCK-5).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pwexp.chain import HashChainLog
from pwexp.hashing import manifest_hash, sha256_file, sha256_json, tree_manifest

from .. import paths

OK, FAIL, TODO = "✓", "✗", "◌"


class LabError(Exception):
    pass


@dataclass
class Check:
    name: str
    ok: bool | None          # None: the code for this check is not built yet
    detail: str = ""


@dataclass
class LabResult:
    checks: list[Check]
    outputs: dict[str, Path]                       # label -> file or directory
    summary: dict[str, Any] = field(default_factory=dict)
    handoff: dict[str, Any] = field(default_factory=dict)
    next_hint: str = ""

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.ok is True for c in self.checks)


@dataclass
class LabContext:
    n: int
    dev: bool
    attempt_dir: Path
    inputs: dict[str, Any] | None                  # previous lab's hand-off (verified), or None for the first lab
    progress: Callable[[str], None] = print


@dataclass
class Lab:
    n: int
    name: str
    purpose: str
    needs_model: bool
    run: Callable[[LabContext], LabResult] | None  # None: not built yet
    built_in: str                                  # build step that adds it
    views: dict[str, Callable[[LabContext], Path]] = field(default_factory=dict)
    dev_first: bool = False                        # first lab in dev mode (earlier labs need the real target)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(p: Path) -> str:
    p = Path(p)
    return manifest_hash(tree_manifest(p)) if p.is_dir() else sha256_file(p)


def rel(p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(paths.root()).as_posix()
    except ValueError:
        return str(p)


class LabBook:
    def __init__(self, labs: list[Lab], dev: bool):
        self.labs = {l.n: l for l in labs}
        self.dev = dev
        self.dir = paths.labs_dir(dev)
        self.log = HashChainLog(self.dir / "lab-log.jsonl")

    # ------------------------------------------------------------------ state
    def state(self) -> dict[str, Any]:
        f = self.dir / "state.json"
        return json.loads(f.read_text()) if f.exists() else {}

    def _save(self, st: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "state.json").write_text(json.dumps(st, indent=2, sort_keys=True) + "\n")

    def first(self) -> int:
        if self.dev:
            return min(l.n for l in self.labs.values() if l.dev_first)
        return min(self.labs)

    def status(self, n: int) -> str:
        if self.dev and n < self.first():
            return "not in dev mode"
        s = self.state().get(str(n), {}).get("status")
        if s:
            return s
        return "ready" if n == self.first() or self.status(n - 1) == "passed" else "locked"

    def handoff(self, n: int) -> dict[str, Any] | None:
        s = self.state().get(str(n))
        if not s or s.get("status") != "passed":
            return None
        return json.loads((paths.root() / s["handoff"]).read_text())

    def verify_handoff(self, n: int) -> tuple[bool, str]:
        h = self.handoff(n)
        if h is None:
            return False, f"Lab {n} has not passed"
        if sha256_json({k: v for k, v in h.items() if k != "handoff_sha256"}) != h.get("handoff_sha256"):
            return False, f"Lab {n} hand-off was altered"
        for label, o in h["outputs"].items():
            p = paths.root() / o["path"]
            if not p.exists() or digest(p) != o["sha256"]:
                return False, f"Lab {n} output {label} ({o['path']}) is missing or changed"
        return True, ""

    # ------------------------------------------------------------------ run
    def can_run(self, n: int) -> tuple[bool, str]:
        lab = self.labs.get(n)
        if lab is None:
            return False, f"no Lab {n}"
        if self.dev and n < self.first():
            return False, f"Lab {n} needs the real target and a model; dev mode starts at Lab {self.first()}"
        if lab.run is None:
            return False, f"Lab {n} is not built yet (build step {lab.built_in})"
        if n != self.first():
            ok, why = self.verify_handoff(n - 1)
            if not ok:
                return False, why
        return True, ""

    def run(self, n: int, progress: Callable[[str], None] = print) -> LabResult:
        ok, why = self.can_run(n)
        if not ok:
            raise LabError(why)
        lab = self.labs[n]
        st = self.state()
        done = [int(p.name.removeprefix("attempt")) for p in (self.dir / f"lab{n}").glob("attempt*")
                if p.name.removeprefix("attempt").isdigit()]     # attempts dropped from state stay on record
        attempt = max([st.get(str(n), {}).get("attempt", 0), *done]) + 1
        adir = self.dir / f"lab{n}" / f"attempt{attempt}"
        adir.mkdir(parents=True, exist_ok=False)
        inputs = self.handoff(n - 1) if n != self.first() else None
        started = _now()
        try:
            res = lab.run(LabContext(n, self.dev, adir, inputs, progress))
        except Exception as e:  # a crash is a failed attempt, recorded like any other
            res = LabResult([Check("lab ran to completion", False, f"{type(e).__name__}: {e}")], {})
        outputs = {k: {"path": rel(p), "sha256": digest(p)} for k, p in res.outputs.items() if Path(p).exists()}
        handoff = {"lab": n, "name": lab.name, "dev": self.dev, "attempt": attempt, "inputs_from": n - 1 if inputs else None,
                   "inputs_handoff_sha256": inputs.get("handoff_sha256") if inputs else None,
                   "outputs": outputs, "summary": res.summary, "handoff": res.handoff, "time": _now()}
        handoff["handoff_sha256"] = sha256_json(handoff)
        (adir / "handoff.json").write_text(json.dumps(handoff, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        card = render_card(lab, res, handoff, inputs, self.dev)
        (adir / "card.txt").write_text(card + "\n")
        status = "passed" if res.passed else "failed"
        st[str(n)] = {"status": status, "attempt": attempt, "handoff": rel(adir / "handoff.json"),
                      "handoff_sha256": handoff["handoff_sha256"], "started": started, "finished": handoff["time"]}
        for later in [k for k in st if int(k) > n]:      # later labs were built on an older hand-off
            st.pop(later)
        self._save(st)
        self.log.append({"event": f"lab_{status}", "lab": n, "attempt": attempt, "dev": self.dev,
                         "checks": {c.name: c.ok for c in res.checks}, "handoff_sha256": handoff["handoff_sha256"],
                         "time": handoff["time"]})
        res.summary.setdefault("_card", card)
        return res


def render_card(lab: Lab, res: LabResult, handoff: dict[str, Any], inputs: dict[str, Any] | None, dev: bool) -> str:
    status = "PASSED " + OK if res.passed else "NOT PASSED " + FAIL
    head = f"Lab {lab.n} · {lab.name}" + ("  [DEVELOPMENT]" if dev else "")
    lines = [f"{head} {'─' * max(3, 74 - len(head) - len(status))} {status}"]
    if inputs:
        lines.append(f"Inputs   Lab {inputs['lab']} hand-off {inputs['handoff_sha256'][:12]} (re-verified)")
    else:
        lines.append("Inputs   none (first lab)")
    for i, c in enumerate(res.checks):
        mark = {True: OK, False: FAIL, None: TODO}[c.ok]
        text = c.name + (f": {c.detail}" if c.detail else "") + (" (not built yet)" if c.ok is None else "")
        lines.append(f"{'Checks' if i == 0 else '':8} {mark} {text}")
    for i, (k, o) in enumerate(handoff["outputs"].items()):
        lines.append(f"{'Outputs' if i == 0 else '':8} {k}: {o['path']} ({o['sha256'][:12]})")
    for k, v in res.summary.items():
        if not k.startswith("_"):
            lines.append(f"{'':8} {k}: {v}")
    if res.passed and res.next_hint:
        lines.append(f"Next     {res.next_hint}")
    return "\n".join(lines)
