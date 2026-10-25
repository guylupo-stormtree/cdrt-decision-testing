"""Lab 8: scale run (RQ2; requirements A12, R-LOCK-2, R-LOCK-4).

Verifies the protocol lock, then runs the scale protocol (cdrt.harness.scale) over the four planes of the
fixtures handed over by Lab 7, with the counts of protocol/run_config.yaml. The lab passes when every
timed cycle was executed and recorded (mismatches, late completions and timeouts kept), every record
carries the lock stamp, the control guard counted no call and the run manifest is written. The result is
one number, the slowest update of the campaign against the budget, reported whatever it is (R-LOCK-5; D-015).
"""
from __future__ import annotations

import yaml

from .. import lock, paths
from ..harness import scale
from .framework import Check, LabContext, LabResult, rel


def run(ctx: LabContext) -> LabResult:
    h = ctx.inputs["handoff"]
    ok, problems, doc = lock.verify(ctx.dev)
    if not ok or doc["lock_root"] != h["lock_root"]:
        return LabResult([Check("protocol lock verifies (R-LOCK-2)", False,
                                "; ".join(problems) or "lock root differs from Lab 7's")], {})
    stamp = {k: h[k] for k in ("lock_root", "campaign_id", "git_commit", "pwexp_commit")}
    cfg = yaml.safe_load((paths.root() / "protocol" / "run_config.yaml").read_text())["scale"]
    res = scale.run(paths.root() / h["fixtures"], paths.root() / h["bundle"], cfg, stamp, ctx.progress)
    files = scale.write(ctx.attempt_dir, res, "DEVELOPMENT" if ctx.dev else "CAMPAIGN")
    recs, st = res["records"], res["stats"]
    checks = [
        Check("protocol lock verifies (R-LOCK-2)", True, h["lock_root"][:12]),
        Check(f"all {res['expected_cycles']} timed cycles executed and recorded (R-SCL-4, R-SCL-5)",
              len(recs) == res["expected_cycles"] and all(v["observations"] == cfg["blocks"] for v in st.values()),
              f"{len(recs)} records"),
        Check("every record carries the lock stamp (R-LOCK-4)",
              all(all(r.get(k) == v for k, v in stamp.items()) and r.get("binding") for r in recs)),
        Check("the control guard counted no call (R-ISO-1)", res["guard_calls"] == 0 and
              all(r["guard_calls"] == 0 for r in recs), f"{res['guard_calls']} calls"),
        Check("run manifest written (R-SCL-8)", files["run_manifest"].exists()),
        Check("baseline verdicts are both SUCCESS at every size (main-14 §4.5)",
              all(sorted(b.values()) == ["SUCCESS", "SUCCESS"] for b in res["manifest"]["baseline"].values())),
    ]
    fmt = lambda x: "—" if x is None else f"{x:.3f} s"  # noqa: E731
    hl = res["headline"]
    summary = {"slowest update (T_max)": f"{fmt(hl['worst_s'])} at N = {hl['worst_N']:,}" if hl["worst_N"] else "—"}
    summary.update({f"N = {v['N']:,}": f"slowest {fmt(v['slowest_s'])} · "
               f"{v['exceedances']}/{v['observations']} over {cfg['deadline_s']} s"
               + (f" · {v['mismatches']} mismatches" if v["mismatches"] else "")
               + (f" · {v['late']} late, {v['timeouts']} timeouts" if v["late"] or v["timeouts"] else "")
               for v in st.values()})
    summary["result"] = res["sentence"]
    return LabResult(checks, files, summary,
                     handoff={"timing_records": rel(files["timing_records"]), "scale_stats": rel(files["scale_stats"]),
                              "sentence": res["sentence"], **stamp,
                              **{k: h[k] for k in ("fixtures", "bundle", "selection", "parameters", "lock",
                                                   "functional_records", "A_comp")}},
                     next_hint=f"cdrt lab run 9{' --dev' if ctx.dev else ''}")
