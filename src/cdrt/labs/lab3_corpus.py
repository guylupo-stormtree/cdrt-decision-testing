"""Lab 3: build the corpus E_C (requirements R-CAP-1, R-CAP-7; PW-BIND).

pwexp Stage 2 ingests the sealed Stage 1 runs and then each decision bundle after its runs, binding every
decision to its intent, policy-at-event and basis. CDRT drives pwexp only through its command line
(R-CAP-1). In dev mode the Stage 1 input is `pwexp import-dev` over the ProofWeave development fixtures,
with development decision bundles (contexts written after the runs; never a result).

The lab then loads the corpus through CDRT's record view (R-REC-1), which re-verifies it independently of
pwexp's own Stage 2 checks.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from .. import paths
from ..records import view
from .framework import Check, LabContext, LabResult, rel


def pwexp(*args: str, dev: bool) -> subprocess.CompletedProcess:
    """Run the pinned pwexp CLI against CDRT's own records root and capture protocol."""
    cmd = [sys.executable, "-m", "pwexp.cli", "--records-root", str(paths.records_root(dev)),
           "--protocol", str(paths.protocol_file(dev)), *args]
    env = {k: v for k, v in os.environ.items() if not k.startswith("PWEXP_")}
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def _cycles(dev: bool) -> set[str]:
    d = paths.records_root(dev) / "cycles"
    return {p.name for p in d.iterdir() if p.is_dir()} if d.is_dir() else set()


def target_path(dev: bool) -> Path:
    proto = yaml.safe_load(paths.protocol_file(dev).read_text())
    return (paths.protocol_file(dev).parent / proto["target"]["snapshot_path"]).resolve()


def run(ctx: LabContext) -> LabResult:
    checks: list[Check] = []
    if ctx.dev:
        before = _cycles(True)
        p = pwexp("import-dev", dev=True)
        ctx.progress(p.stdout.strip().splitlines()[0] if p.stdout.strip() else p.stderr.strip()[-200:])
        new = sorted(_cycles(True) - before)
        checks.append(Check("development Stage 1 imported with decision bundles", p.returncode == 0 and len(new) == 1,
                            "" if p.returncode == 0 else p.stdout + p.stderr))
        if not new:
            return LabResult(checks, {})
        cycle = new[0]
    else:
        handoff = (ctx.inputs or {}).get("handoff", {})
        cycle = handoff.get("cycle")
        checks.append(Check("Stage 1 cycle handed over by Lab 2", bool(cycle)))
        if not cycle:
            return LabResult(checks, {})
    ctx.progress(f"pwexp Stage 2 on {cycle} …")
    p = pwexp("run-stage", "2", "--cycle", cycle, "--repetitions", "1", dev=ctx.dev)
    for line in p.stdout.splitlines():
        if line.strip().startswith(("✓", "✗")) and "Stage 2" in line:
            ctx.progress(line.strip())
    cdir = paths.records_root(ctx.dev) / "cycles" / cycle
    data = json.loads((cdir / "cycle.json").read_text())
    s2 = data["stages"]["2"]
    checks.append(Check("pwexp Stage 2 passed all its checks", s2["status"] == "complete" and all(s2["checks"].values()),
                        ", ".join(k for k, v in s2["checks"].items() if not v)))
    if s2["status"] != "complete":
        return LabResult(checks, {})
    o = s2["outcome"]
    corpus = cdir / "stage2" / o["attempt_dir"] / "corpus"
    target = target_path(ctx.dev)
    try:
        snap = view.load_snapshot(corpus, target, o["corpus_sha256"])
        checks.append(Check("record view re-verified the corpus (hash, ledger chain, graph rebuild)", True))
    except view.IntegrityFinding as e:
        checks.append(Check("record view re-verified the corpus (hash, ledger chain, graph rebuild)", False, str(e)))
        return LabResult(checks, {"corpus": corpus})
    decisions = view.list_decisions(snap)
    status = {d: view.get_decision(snap, d)["status"] for d in decisions}
    verdicts = {d: view.get_decision(snap, d)["decision"]["payload"]["verdict"] for d in decisions}
    checks.append(Check("every scheduled decision is bound", bool(decisions) and set(decisions) ==
                        {p.name for p in (cdir / "stage1" / data["stages"]["1"]["outcome"]["attempt_dir"] / "decisions").iterdir()}))
    checks.append(Check("every binding complete (basis resolves, basis root recomputes)",
                        bool(status) and all(v == "complete" for v in status.values()),
                        ", ".join(f"{d} {s}" for d, s in status.items() if s != "complete")))
    by_group: dict[str, list[str]] = {}
    for d, v in verdicts.items():
        by_group.setdefault(d.rsplit("-", 1)[0], []).append(v)
    summary = {"corpus_sha256": snap.corpus_sha256, "records": snap.ledger_head[0] + 1,
               "decisions": " · ".join(f"{g} {sum(v == 'green' for v in vs)}/{len(vs)} green"
                                       for g, vs in sorted(by_group.items()))}
    return LabResult(checks, {"corpus": corpus}, summary,
                     handoff={"cycle": cycle, "corpus": rel(corpus), "corpus_sha256": snap.corpus_sha256,
                              "stage1": rel(cdir / "stage1" / data["stages"]["1"]["outcome"]["attempt_dir"]),
                              "target": rel(target), "protocol": rel(paths.protocol_file(ctx.dev)),
                              "decisions": verdicts},
                     next_hint=f"cdrt lab run 4{' --dev' if ctx.dev else ''}")
