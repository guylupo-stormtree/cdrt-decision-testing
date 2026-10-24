"""Lab 9: report (requirements A13, A12.1; R-REP-1 … R-REP-5).

Refuses unless the lock verifies, the campaign is complete (every functional step, case, interleaving and
boundary check; every scheduled timed cycle) and every record carries the active lock root (R-REP-1). It then
generates the five manuscript blocks and figures/scale_latency.tex from those records only, fills a copy of
the manuscript with them and compiles the copy. The manuscript itself is never written here: blocks the
manuscript does not have yet (the A17 revision) are inserted into the copy only, and listed.

Manuscript: $CDRT_MANUSCRIPT, or ../ComposableCDRT/Manuscript/main-13.tex next to this repository.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from pwexp.hashing import sha256_file

from .. import lock, paths, report
from ..harness import functional
from .framework import Check, LabContext, LabResult, rel


def manuscript() -> Path:
    env = os.environ.get("CDRT_MANUSCRIPT")
    return Path(env) if env else paths.root().parent / "ComposableCDRT" / "Manuscript" / "main-13.tex"


def repoaudit_commit() -> str:
    out = lock.git("submodule", "status", "vendor/RepoAudit", cwd=paths.pwexp_checkout())
    return out.split()[0].lstrip("+-U") if out else ""


def latex(d: Path, name: str) -> tuple[bool, list[str], int]:
    """(ran, LaTeX error lines, undefined citations) for latexmk -pdf on d/name."""
    if not shutil.which("latexmk"):
        return False, ["latexmk not installed"], 0
    subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", name], cwd=d,
                   capture_output=True, text=True, timeout=600)
    log = (d / Path(name).with_suffix(".log")).read_text(errors="replace") if (d / Path(name).with_suffix(".log")).exists() else ""
    errors = [l for l in log.splitlines() if l.startswith("!")]
    cites = len(set(re.findall(r"Citation `([^']+)' on page \d+ undefined", log)))
    return (d / Path(name).with_suffix(".pdf")).exists(), errors, cites


def run(ctx: LabContext) -> LabResult:
    h = ctx.inputs["handoff"]
    root = paths.root()
    ok, problems, doc = lock.verify(ctx.dev)
    if not ok or doc["lock_root"] != h["lock_root"]:
        return LabResult([Check("protocol lock verifies (R-LOCK-2)", False,
                                "; ".join(problems) or "lock root differs from Lab 8's")], {})
    cfg = yaml.safe_load((root / "protocol" / "run_config.yaml").read_text())["scale"]
    d = report.gather(root, h, doc)
    expected = int(cfg["blocks"]) * len(d["params"]["scale_target_sizes"])
    gaps = report.completeness(d, expected, functional.IDS)
    if gaps:                                               # R-REP-1: nothing is filled
        return LabResult([Check("lock verifies and the campaign is complete (R-REP-1)", False, "; ".join(gaps))], {})

    src = manuscript()
    if not src.exists():
        return LabResult([Check("manuscript found", False, f"{src} (set CDRT_MANUSCRIPT)")], {})
    gen, trace = report.blocks(d, ctx.dev, root, repoaudit_commit())
    fig_tex, fig_csv = report.figure(d, int(cfg["seed"]))

    bdir = ctx.attempt_dir / "generated"
    (bdir / "figures").mkdir(parents=True)
    for n, body in gen.items():
        (bdir / f"{n}.tex").write_text(f"% BEGIN GENERATED:{n}\n{body}\n% END GENERATED:{n}\n")
    (bdir / "figures" / "scale_latency.tex").write_text(fig_tex)
    (bdir / "figures" / "scale_latency.csv").write_text(fig_csv)

    mdir = ctx.attempt_dir / "manuscript"
    (mdir / "figures").mkdir(parents=True)
    filled, replaced, inserted = report.fill(src.read_text(), gen)
    (mdir / src.name).write_text(filled)
    shutil.copyfile(bdir / "figures" / "scale_latency.tex", mdir / "figures" / "scale_latency.tex")
    bib = src.with_name("references.bib")
    if bib.exists():
        shutil.copyfile(bib, mdir / bib.name)
    ctx.progress(f"compiling the filled copy of {src.name}")
    built, errors, cites = latex(mdir, src.name)

    pdir = ctx.attempt_dir / "figure-preview"
    pdir.mkdir()
    shutil.copyfile(bdir / "figures" / "scale_latency.tex", pdir / "scale_latency.tex")
    (pdir / "preview.tex").write_text("\\documentclass[border=4pt]{standalone}\n\\usepackage{pgfplots}\n"
                                      "\\pgfplotsset{compat=1.18}\n\\newlength{\\cw}\\setlength{\\cw}{9cm}\n"
                                      "\\begin{document}\n{\\columnwidth=\\cw\\input{scale_latency.tex}}\n\\end{document}\n")
    fig_ok, fig_errors, _ = latex(pdir, "preview.tex")

    words = "\n".join(gen.values())
    from ..harness.scale import headline
    within = headline(d["scale"]["stats"], float(cfg["deadline_s"]))["within"]
    tx = report.texts(d, ctx.dev)
    scale_words = " ".join(tx[k] for k in ("ScaleResultText", "ScaleAbstractText", "ScaleIntroText", "ConclusionResultText"))
    wording = "real-time" not in words.lower() and "guarantee" not in words.lower() and \
        "p95" not in words and "percentile" not in words.lower() and \
        (("exceeded" not in scale_words) if within else ("within" not in scale_words.replace("beyond", "")))
    traced = {k: v for k, v in trace.items()}
    sources_locked = all(r.get("lock_root") == doc["lock_root"] for r in d["functional"] + d["timing"])
    (ctx.attempt_dir / "trace.json").write_text(json.dumps(
        {"lock_root": doc["lock_root"], "values": traced,
         "sources": {k: {"path": rel(p), "sha256": sha256_file(p)} for k, p in d["src"].items()},
         "manuscript": {"path": str(src), "sha256": sha256_file(src), "replaced": replaced, "inserted_in_copy": inserted}},
        indent=2, sort_keys=True) + "\n")
    checks = [
        Check("lock verifies and the campaign is complete (R-REP-1)", True,
              f"{len(d['functional'])} functional and {len(d['timing'])} timing records, lock {doc['lock_root'][:12]}"),
        Check("every value traces to a record carrying the lock root", sources_locked and all(traced.values()),
              f"{len(traced)} values traced (trace.json)"),
        Check("wording rules (R-REP-5)", wording),
        Check("the filled manuscript copy compiles with 0 errors", built and not errors,
              (f"{len(errors)} errors: {errors[0]}" if errors else "0 errors") +
              (f"; {cites} citations undefined (no references.bib next to the manuscript)" if cites and not bib.exists() else "")),
        Check("the scale figure compiles on its own", fig_ok and not fig_errors, "; ".join(fig_errors[:1])),
    ]
    acc = d["acceptance"]
    summary = {"RQ1": f"A_comp = {str(acc['A_comp']).lower()}; " +
               ", ".join(f"{k} {'✓' if v['passes'] else '✗ (' + ', '.join(v['failing']) + ')'}"
                         for k, v in acc["acceptance"].items()),
               "RQ2": d["scale"]["sentence"],
               "blocks": f"replaced {', '.join(replaced)}" + (f"; inserted into the copy only: {', '.join(inserted)}"
                                                             if inserted else ""),
               "pdf": rel(mdir / src.with_suffix(".pdf").name)}
    unattainable = [r["id"] for r in d["functional"] if r.get("attainable") is False]
    if unattainable:
        summary["not attainable"] = ", ".join(unattainable)                 # R-REP-3
    st = d["scale"]["stats"]
    for k in ("mismatches", "late", "timeouts"):
        if sum(v[k] for v in st.values()):
            summary[k] = sum(v[k] for v in st.values())
    return LabResult(checks, {"generated": bdir, "manuscript_copy": mdir / src.name, "trace": ctx.attempt_dir / "trace.json",
                              "figure_preview": pdir / "preview.pdf"}, summary,
                     handoff={"generated": rel(bdir), "manuscript_copy": rel(mdir / src.name), "A_comp": acc["A_comp"],
                              "sentence": d["scale"]["sentence"], "lock_root": doc["lock_root"]},
                     next_hint="the generated blocks are ready for the A17 manuscript revision" if not ctx.dev else
                     "development preview only; the reported campaign is B8")
