"""Lab 1: pilot capture (requirements R-CAP-2, R-CAP-4; A5.1).

Runs the pilot G-main decisions through pwexp (Stages 1-2) into capture/records (pilot cycles, never results),
reads each GREEN pilot decision's coverage of M_h through the record view, sets tau_h by the declared rule (the
largest multiple of 1/20 at which at least 80% of the pilot runs would conform), writes P1 and the campaign
protocol, and takes the capture lock. The API key is typed once at the start of `cdrt lab run 1-2`.
"""
from __future__ import annotations

import json
from fractions import Fraction

from .. import capture, paths
from ..records import view
from ..records.assessments import BASE, assessments
from .framework import Check, LabContext, LabResult, rel


def run(ctx: LabContext) -> LabResult:
    cfg = capture.declaration()
    key = ctx.secrets.get("key")
    if not key:
        return LabResult([Check("API key entered and checked at the start of the run", False,
                                "run `cdrt lab run 1-2` (the key is asked for once, then checked)")], {})
    model = f"{cfg['model']['provider']}:{cfg['model']['model']}"
    records = capture.capture_dir() / "records"
    proto = paths.root() / ctx.inputs["handoff"]["pilot_protocol"]
    cid = capture.new_cycle(records, proto, "pilot")
    ctx.progress(f"pilot cycle {cid}: {cfg['runs']['pilot']} RepoAudit runs with {model}")
    rc1, _ = capture.pwexp(records, proto, "run-stage", "1", "--cycle", cid, *capture.model_args(cfg), "--key-stdin",
                           key=key, progress=ctx.progress)
    rc2, _ = capture.pwexp(records, proto, "run-stage", "2", "--cycle", cid, "--repetitions", "1", progress=ctx.progress)
    checks = [Check("pilot Stage 1 passed its checks (every run kept, below the timeout, no key in any output)", rc1 == 0),
              Check("pilot Stage 2 bound every pilot decision", rc2 == 0)]
    if rc1 or rc2:
        return LabResult(checks, {})
    data = json.loads((records / "cycles" / cid / "cycle.json").read_text())
    corpus = records / "cycles" / cid / "stage2" / data["stages"]["2"]["outcome"]["attempt_dir"] / "corpus"
    s = view.load_snapshot(corpus, capture.target_dir())
    mh = set(json.loads((capture.manifest_dir() / "M_h.json").read_text())["functions"])
    rows, cov = {}, []
    for d in view.list_decisions(s):
        green = view.get_decision(s, d)["decision"]["payload"]["verdict"] == "green"
        got = {r["target"] for r in assessments(s, d)["records"] if r["validator"] == BASE} & mh
        c = Fraction(len(got), len(mh)) if mh else Fraction(0)
        rows[d] = {"green": green, "coverage_M_h": f"{len(got)}/{len(mh)}"}
        if green:
            cov.append(c)
    n = int(cfg["runs"]["pilot"])
    tau, need = capture.tau_h_rule(cov, n)
    greens = sum(v["green"] for v in rows.values())
    checks += [Check(f"at least {need} of {n} pilot runs GREEN (A5.1)", greens >= need, f"{greens} GREEN"),
               Check("tau_h set by the declared rule and above zero (R-CAP-4)", tau is not None and tau > 0,
                     f"tau_h = {tau}" if tau is not None else "too few GREEN pilot runs")]
    if not all(c.ok for c in checks):
        return LabResult(checks, {}, {"pilot decisions": json.dumps(rows)})
    final = capture.write_protocol(cfg, capture.capture_dir(), int(cfg["runs"]["campaign"]),
                                   int(cfg["runs"]["semgrep_standalone"]), tau)
    rc, out = capture.pwexp(records, final, "protocol", "lock")
    checks.append(Check("capture protocol locked (R-CAP-2)", rc == 0, out.strip().splitlines()[-1] if out.strip() else ""))
    lockf = capture.capture_dir() / "protocol.lock.json"
    summary = {"pilot cycle": cid, "pilot decisions": ", ".join(f"{d} {'GREEN' if v['green'] else 'not green'} {v['coverage_M_h']}"
                                                                 for d, v in rows.items()),
               "tau_h": f"{tau} ({float(tau):.0%})"}
    return LabResult(checks, {"protocol": final, "lock": lockf}, summary,
                     handoff={"pilot_cycle": cid, "tau_h": f"{tau.numerator}/{tau.denominator}", "protocol": rel(final),
                              "lock": rel(lockf)},
                     next_hint="Lab 2 (the campaign capture) follows in the same run")
