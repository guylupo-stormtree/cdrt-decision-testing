"""Lab 5: build the fixtures (requirements A6, R-FIX-1 … R-FIX-5).

Runs the fixture build (cdrt.fixtures) offline over the frozen bundle handed over by Lab 4, with the counts
of protocol/run_config.yaml, into fixtures/out[-dev]/. It then builds a second time into the attempt folder
and compares the two trees byte for byte (R-FIX-5); the second copy is removed once compared. Each scale
plane is loaded back through the record view (synthetic records allowed) and its decision must be complete.
"""
from __future__ import annotations

import shutil
from fractions import Fraction

import yaml

from pwexp.hashing import manifest_hash, tree_manifest

from .. import fixtures, lock, paths
from ..records import view
from .framework import Check, LabContext, LabResult, rel


def macros(p: dict) -> str:
    """Preview of the fixture macros for the manuscript (Lab 9 generates the real block)."""
    t2, t3 = p["tau_q_rev2"], p["tau_q_rev3b"]
    rows = {"CDRTcobs": p["c_obs_count"], "CDRTtauQrevTwo": f"{t2['numerator']}/{t2['denominator']}",
            "CDRTtauQrevThreeB": f"{t3['numerator']}/{t3['denominator']}", "CDRTassessmentTime": p["t_e"],
            "CDRTmaxAge": f"{p['max_age_seconds']}", "CDRTnZero": f"{p['n0']}",
            "CDRTscaleSizes": ", ".join(f"{n:,}" for n in p["actual_sizes"])}
    return "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in rows.items())


def run(ctx: LabContext) -> LabResult:
    h = ctx.inputs["handoff"]
    bundle = paths.root() / h["bundle"]
    sel = {k: h["selection"][k] for k in ("main", "strict", "pipeline")}
    cfg = yaml.safe_load((paths.root() / "protocol" / "run_config.yaml").read_text())
    out = lock.fixtures_dir(ctx.dev)
    if out.exists():
        shutil.rmtree(out)
    ctx.progress(f"building fixtures into {rel(out)}")
    p = fixtures.build(bundle, sel, out, cfg, progress=ctx.progress)
    ctx.progress("second build, to compare bytes (R-FIX-5)")
    again = ctx.attempt_dir / "rebuild"
    fixtures.build(bundle, sel, again, cfg, progress=lambda m: None)
    a, b = tree_manifest(out), tree_manifest(again)
    differ = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    shutil.rmtree(again)

    planes_ok, plane_notes = True, []
    target = bundle / "target"
    for n, pl in p["planes"].items():
        s = view.load_snapshot(out / "planes" / f"N{n}", target, allow_synthetic=True)
        rec = view.get_decision(s, pl["decision"])
        ok = rec["status"] == "complete" and rec["binding"]["payload"]["basis_count"] == pl["basis_count"]
        planes_ok &= ok
        plane_notes.append(f"N={pl['basis_count']:,}{'' if ok else ' (not complete)'}")

    c_obs, tau2 = Fraction(p["c_obs"]), Fraction(p["tau_q_rev2"]["numerator"], p["tau_q_rev2"]["denominator"])
    (ctx.attempt_dir / "fixture_macros.preview.tex").write_text(macros(p))
    checks = [
        Check("tau_q(rev2) >= 1/2 (otherwise the capture is unsuitable, R-FIX-2)", tau2 >= Fraction(1, 2),
              f"tau_q(rev2) = {tau2}"),
        Check("c_obs < 1 (rev 3b can fail on coverage, R-FIX-2)", c_obs < 1, f"c_obs = {p['c_obs_count']}"),
        Check("derived copies F4, B1, B2, B3 written", sorted(p["derived"]) == ["B1", "B2", "B3", "F4"]),
        Check("every scale plane verified and checkpointed", planes_ok, " · ".join(plane_notes)),
        Check("two builds give identical bytes (R-FIX-5)", not differ,
              f"{len(a)} files" if not differ else f"{len(differ)} files differ, e.g. {differ[0]}"),
    ]
    t3 = p["tau_q_rev3b"]
    summary = {"c_obs": p["c_obs_count"], "tau_q": f"rev2 {tau2} · rev3b {t3['numerator']}/{t3['denominator']}",
               "t_e": p["t_e"], "max_age_seconds (Delta_q)": p["max_age_seconds"],
               "scale sizes (actual N)": ", ".join(f"{n:,}" for n in p["actual_sizes"]),
               "fixtures_sha256": manifest_hash(a)}
    return LabResult(checks, {"fixtures": out, "macros_preview": ctx.attempt_dir / "fixture_macros.preview.tex"}, summary,
                     handoff={"fixtures": rel(out), "bundle": h["bundle"], "bundle_sha256": h["bundle_sha256"],
                              "selection": sel, "f9": h["f9"], "parameters": rel(out / "parameters.json")},
                     next_hint=f"cdrt lab run 6{' --dev' if ctx.dev else ''}")
