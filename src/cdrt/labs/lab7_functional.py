"""Lab 7: functional run (RQ1; requirements A10, R-LOCK-2, R-LOCK-4).

Verifies the protocol lock, then runs the functional protocol (cdrt.harness.functional) on the frozen bundle
and the fixtures handed over by Lab 6. The lab passes when the run is complete and intact: every step,
case, interleaving and boundary check executed, every record carries the lock root, and the control guard
counted no call. A_comp is the result, reported whatever it is (R-LOCK-5).
"""
from __future__ import annotations

import json

import yaml

from .. import lock, paths
from ..harness import functional
from .framework import Check, LabContext, LabResult, rel


def run(ctx: LabContext) -> LabResult:
    h = ctx.inputs["handoff"]
    ok, problems, doc = lock.verify(ctx.dev)
    if not ok:
        return LabResult([Check("protocol lock verifies (R-LOCK-2)", False, "; ".join(problems))], {})
    if doc["lock_root"] != h["lock_root"]:
        return LabResult([Check("protocol lock verifies (R-LOCK-2)", False, "lock root differs from Lab 6's")], {})
    stamp = {"lock_root": h["lock_root"], "campaign_id": h["campaign_id"], "git_commit": h["git_commit"],
             "pwexp_commit": h["pwexp_commit"]}
    cfg = yaml.safe_load((paths.root() / "protocol" / "run_config.yaml").read_text())
    replays = int(cfg["functional"]["replay_runs"])
    work = ctx.attempt_dir / "work"
    work.mkdir()
    env = functional.load_env(paths.root() / h["bundle"], paths.root() / h["fixtures"], work, stamp, h["f9"])
    trace: list[str] = []

    def progress(m: str) -> None:
        trace.append(m)
        ctx.progress(m)
    out = functional.run_protocol(env, replays, progress)
    recs, acc = out["records"], out["acceptance"]

    f_rec = ctx.attempt_dir / "functional_records.jsonl"
    f_rec.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in recs))
    f_acc = ctx.attempt_dir / "acceptance.json"
    f_acc.write_text(json.dumps({**acc, **stamp}, indent=2, sort_keys=True) + "\n")
    f_tr = ctx.attempt_dir / "trace.txt"
    f_tr.write_text("\n".join(trace) + "\n")

    errors = [r for r in recs if not r.get("executed")]
    iso = next((r for r in recs if r["id"] == "isolation"), {})
    calls = (iso.get("observed") or {}).get("guard_calls")
    checks = [
        Check("protocol lock verifies (R-LOCK-2)", True, h["lock_root"][:12]),
        Check("every step, case, interleaving and boundary check executed", not errors and not out["missing"],
              "; ".join([f"{r['id']}: {r['error']}" for r in errors] + [f"{i} missing" for i in out["missing"]])[:300]),
        Check("every record carries the lock stamp (R-LOCK-4)",
              all(all(r.get(k) == v for k, v in stamp.items()) and "binding" in r for r in recs), f"{len(recs)} records"),
        Check("the control guard counted no call (R-ISO-1)", calls == 0, f"{calls} calls"),
        Check(f"the protocol ran {replays} times for the replay comparison", len(out["digests"]) == replays),
    ]
    by = {r["id"]: r for r in recs}
    cases = " ".join(f"{i}{'✓' if by[i]['match'] else '✗'}" for i in [f"F{n}" for n in range(1, 9)] if i in by)
    summary = {"A_comp": acc["A_comp"],
               "acceptance": " ".join(f"{k}{'✓' if v['passes'] else '✗'}" for k, v in acc["acceptance"].items()),
               "cases": cases,
               "failing": "; ".join(f"{k}: {', '.join(v['failing'])}" for k, v in acc["acceptance"].items() if v["failing"])
               or "none",
               "F9": ", ".join(f"{k} H={v['H']} A={v['A']}" for k, v in (by.get("F9", {}).get("observed") or {}).items())
               or "none", "records": rel(f_rec)}
    return LabResult(checks, {"functional_records": f_rec, "acceptance": f_acc, "trace": f_tr}, summary,
                     handoff={"A_comp": acc["A_comp"], "acceptance": {k: v["passes"] for k, v in acc["acceptance"].items()},
                              "functional_records": rel(f_rec), **stamp,
                              **{k: h[k] for k in ("fixtures", "bundle", "selection", "f9", "parameters", "lock")}},
                     next_hint=f"cdrt lab run 8{' --dev' if ctx.dev else ''}")
