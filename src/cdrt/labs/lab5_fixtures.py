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
    t2 = p["tau_q"]
    tr = p["tau_rel"]
    rows = {"CDRTcobs": p["c_obs_count"], "CDRTtauQ": f"{t2['numerator']}/{t2['denominator']}",
            "CDRTtauRel": f"{tr['numerator']}/{tr['denominator']}",
            "CDRTrunCount": f"{p['captured']}", "CDRTassessmentTime": p["t_e"],
            "CDRTmaxAge": f"{p['max_age_seconds']}", "CDRTnZero": f"{p['n0']}",
            "CDRTscaleSizes": ", ".join(f"{n:,}" for n in p["actual_sizes"])}
    return "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in rows.items())


def run(ctx: LabContext) -> LabResult:
    h = ctx.inputs["handoff"]
    bundle = paths.root() / h["bundle"]
    sel = {"main": h["selection"]["main"]}
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
        recs = [view.get_decision(s, d) for d in pl["decisions"].values()]
        ok = all(r["status"] == "complete" for r in recs) and \
            sum(r["binding"]["payload"]["basis_count"] for r in recs) == pl["basis_count"]
        planes_ok &= ok
        plane_notes.append(f"N={pl['basis_count']:,}{'' if ok else ' (not complete)'}")

    c_obs, tau2 = Fraction(p["c_obs"]), Fraction(p["tau_q"]["numerator"], p["tau_q"]["denominator"])
    (ctx.attempt_dir / "fixture_macros.preview.tex").write_text(macros(p))
    checks = [
        Check("tau_q and tau_rel declared in run_config before capture (not derived from the data)",
              p["checks"]["tau_q and tau_rel declared"], f"tau_q = {tau2}, tau_rel = {Fraction(p['tau_rel']['numerator'], p['tau_rel']['denominator'])}"),
        Check("profiles rev 1-3 and the one-decision observation profile written",
              sorted(x.name for x in (out / "profiles").iterdir()) == ["obs2.yaml", "rev1.yaml", "rev2.yaml", "rev3.yaml"]),
        Check("every scale plane verified and checkpointed", planes_ok, " · ".join(plane_notes)),
        Check("two builds give identical bytes (R-FIX-5)", not differ,
              f"{len(a)} files" if not differ else f"{len(differ)} files differ, e.g. {differ[0]}"),
    ]
    summary = {"captured decisions": f"{p['captured']} ({len(p['green'])} GREEN)", "c_obs (main alone)": p["c_obs_count"], "tau_q": f"{tau2}",
               "t_e": p["t_e"], "max_age_seconds (Delta_q)": p["max_age_seconds"],
               "scale sizes (actual N)": ", ".join(f"{n:,}" for n in p["actual_sizes"]),
               "fixtures_sha256": manifest_hash(a)}
    return LabResult(checks, {"fixtures": out, "macros_preview": ctx.attempt_dir / "fixture_macros.preview.tex"}, summary,
                     handoff={"fixtures": rel(out), "bundle": h["bundle"], "bundle_sha256": h["bundle_sha256"],
                              "selection": sel, "green": h["green"], "parameters": rel(out / "parameters.json")},
                     next_hint=f"cdrt lab run 6{' --dev' if ctx.dev else ''}")
