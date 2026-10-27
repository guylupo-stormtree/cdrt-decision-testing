"""Lab 9: report (requirements A13, A12.1; R-REP-1 … R-REP-5).

Refuses unless the lock verifies, the campaign is complete (every functional step, case, interleaving and
boundary check; every scheduled timed cycle) and every record carries the active lock root (R-REP-1). It then
generates the manuscript's generated/ folder (main-15: macros, the experiment record subsection, Table 3,
Table 4, the pathway and scale figures) from those records only, places it beside a copy of
the manuscript with them and compiles the copy. The manuscript itself is never written here: blocks the
manuscript does not have yet (the A17 revision) are inserted into the copy only, and listed.

Manuscript: $CDRT_MANUSCRIPT, or ../ComposableCDRT/Manuscript/main-17.tex next to this repository. The folder name is
the one the manuscript reads: generated/ (the campaign) or generated-pending/ (the development mockup).
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
    """$CDRT_MANUSCRIPT, else the newest main-<N>.tex in ../ComposableCDRT/Manuscript."""
    env = os.environ.get("CDRT_MANUSCRIPT")
    if env:
        return Path(env)
    d = paths.root().parent / "ComposableCDRT" / "Manuscript"
    found = [(int(m.group(1)), f) for f in d.glob("main-*.tex") if (m := re.fullmatch(r"main-(\d+)\.tex", f.name))]
    return max(found)[1] if found else d / "main.tex"


def repoaudit_commit() -> str:
    out = lock.git("submodule", "status", "vendor/RepoAudit", cwd=paths.pwexp_checkout())
    return out.split()[0].lstrip("+-U") if out else ""


def latex(d: Path, name: str) -> tuple[bool, list[str], int]:
    """(built, LaTeX error lines, undefined citations): pdflatex, BibTeX when the document has a bibliography,
    then pdflatex twice. Errors are counted on the final pass."""
    if not shutil.which("pdflatex"):
        return False, ["pdflatex not installed"], 0
    stem = Path(name).stem
    run = lambda *cmd: subprocess.run(list(cmd), cwd=d, capture_output=True, timeout=600)  # noqa: E731  (bytes: TeX output need not be UTF-8)
    run("pdflatex", "-interaction=nonstopmode", name)
    aux = d / f"{stem}.aux"
    if aux.exists() and "\\bibdata" in aux.read_text(errors="replace") and shutil.which("bibtex"):
        run("bibtex", stem)
    for _ in range(2):
        run("pdflatex", "-interaction=nonstopmode", name)
    log = (d / f"{stem}.log").read_text(errors="replace") if (d / f"{stem}.log").exists() else ""
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
    tag = lock.git("describe", "--tags", "--exact-match", doc["git_commit"]) if doc.get("git_commit") else ""
    text = src.read_text()
    folder = "generated-pending" if "\\input{generated-pending/" in text else "generated"
    gen, trace = report.blocks(d, ctx.dev, root, repoaudit_commit(), tag, folder=folder)
    fig_tex, fig_csv = report.figure(d, int(cfg["seed"]), dev=ctx.dev)
    path_tex = report.pathway_figure(d, h["selection"], dev=ctx.dev)
    cov_tex = report.coverage_figure(d, dev=ctx.dev)

    # the folder the manuscript reads with \input; after the campaign it replaces the manuscript's folder
    bdir = ctx.attempt_dir / folder
    (bdir / "figures").mkdir(parents=True)
    for name, body in report.files(gen).items():
        (bdir / name).write_text(body)
    (bdir / "figures" / "scale_latency.tex").write_text(fig_tex)
    (bdir / "figures" / "scale_latency.csv").write_text(fig_csv)
    (bdir / "figures" / "pathways.tex").write_text(path_tex)
    (bdir / "figures" / "coverage.tex").write_text(cov_tex)
    (bdir / "README.md").write_text(
        f"# Generated experiment content{' (DEVELOPMENT DATA, not a result)' if ctx.dev else ''}\n\n"
        f"Written by `cdrt lab run 9` from the locked campaign `{doc['campaign_id']}` (lock root `{doc['lock_root']}`, "
        f"code commit `{doc['git_commit'][:12]}`). Replace the manuscript's `generated/` folder with this one; the "
        "manuscript itself does not change.\n")

    mdir = ctx.attempt_dir / "manuscript"
    wanted = [f"\\input{{{folder}/{n[:-4]}}}" for n in report.FILES]
    input_mode = f"\\input{{{folder}/" in text
    if input_mode:                                         # main-15 onwards: the manuscript copy reads generated/
        missing_inputs = [w for w in wanted if w not in text]
        mdir.mkdir()
        (mdir / src.name).write_text(text)
        shutil.copytree(bdir, mdir / folder)
        replaced, inserted = [n for n in report.FILES if f"\\input{{{folder}/{n[:-4]}}}" in text], []
    else:                                                  # older manuscripts hold the blocks inline
        missing_inputs = []
        (mdir / "figures").mkdir(parents=True)
        filled, replaced, inserted = report.fill(text, gen)
        (mdir / src.name).write_text(filled.replace(f"{folder}/figures/", "figures/"))
        for f in ("scale_latency.tex", "pathways.tex", "coverage.tex"):
            shutil.copyfile(bdir / "figures" / f, mdir / "figures" / f)
    bib = src.with_name("references.bib")
    if bib.exists():
        shutil.copyfile(bib, mdir / bib.name)
    ctx.progress(f"compiling the filled copy of {src.name}")
    built, errors, cites = latex(mdir, src.name)

    pdir = ctx.attempt_dir / "figure-preview"
    pdir.mkdir()
    for f in ("scale_latency.tex", "pathways.tex", "coverage.tex"):
        shutil.copyfile(bdir / "figures" / f, pdir / f)
    (pdir / "preview.tex").write_text("\\documentclass[border=4pt]{standalone}\n\\usepackage{pgfplots}\n"
                                      "\\pgfplotsset{compat=1.18}\n\\newlength{\\cw}\\setlength{\\cw}{9cm}\n"
                                      "\\begin{document}\n{\\columnwidth=\\cw\\input{scale_latency.tex}}\n\\end{document}\n")
    (pdir / "pathways-preview.tex").write_text("\\documentclass[border=4pt]{standalone}\n\\usepackage{tikz}\n"
                                               "\\begin{document}\n\\input{pathways.tex}\n\\end{document}\n")
    (pdir / "coverage-preview.tex").write_text("\\documentclass[border=4pt]{standalone}\n\\usepackage{pgfplots}\n"
                                               "\\pgfplotsset{compat=1.18}\n\\newlength{\\cw}\\setlength{\\cw}{9cm}\n"
                                               "\\begin{document}\n{\\columnwidth=\\cw\\input{coverage.tex}}\n\\end{document}\n")
    cov_ok, cov_errors, _ = latex(pdir, "coverage-preview.tex")
    fig_ok, fig_errors, _ = latex(pdir, "preview.tex")
    path_ok, path_errors, _ = latex(pdir, "pathways-preview.tex")

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
        Check("the manuscript reads every generated file", not missing_inputs,
              "missing: " + ", ".join(missing_inputs) if missing_inputs else
              (f"{len(wanted)} \\input{{{folder}/...}} files" if input_mode else "inline blocks (pre-main-15 manuscript)")),
        Check("the filled manuscript copy compiles with 0 errors", built and not errors,
              (f"{len(errors)} errors: {errors[0]}" if errors else "0 errors") +
              (f"; {cites} citations undefined (no references.bib next to the manuscript)" if cites and not bib.exists() else "")),
        Check("the scale figure compiles on its own", fig_ok and not fig_errors, "; ".join(fig_errors[:1])),
        Check("the composed-coverage figure compiles on its own", cov_ok and not cov_errors,
              "; ".join(cov_errors[:1]) or tx["CoverageSentence"]),
        Check("the same-green-different-paths figure compiles on its own", path_ok and not path_errors,
              "; ".join(path_errors[:1]) or tx["PathwaySentence"]),
    ]
    acc = d["acceptance"]
    summary = {"RQ1": f"A_comp = {str(acc['A_comp']).lower()}; " +
               ", ".join(f"{k} {'✓' if v['passes'] else '✗ (' + ', '.join(v['failing']) + ')'}"
                         for k, v in acc["acceptance"].items()),
               "RQ2": d["scale"]["sentence"],
               "generated": (f"{rel(bdir)} ({len(report.FILES)} files + figures): replace the manuscript's generated/ "
                             "folder with it" if input_mode else f"replaced {', '.join(replaced)}" +
                             (f"; inserted into the copy only: {', '.join(inserted)}" if inserted else "")),
               "pdf": rel(mdir / src.with_suffix(".pdf").name)}
    unattainable = [r["id"] for r in d["functional"] if r.get("attainable") is False]
    if unattainable:
        summary["not attainable"] = ", ".join(unattainable)                 # R-REP-3
    st = d["scale"]["stats"]
    for k in ("mismatches", "late", "timeouts"):
        if sum(v[k] for v in st.values()):
            summary[k] = sum(v[k] for v in st.values())
    return LabResult(checks, {"generated": bdir, "manuscript_copy": mdir / src.name, "trace": ctx.attempt_dir / "trace.json",
                              "figure_preview": pdir / "preview.pdf", "pathways_preview": pdir / "pathways-preview.pdf"},
                     {**summary, "coverage": tx["CoverageSentence"]},
                     handoff={"generated": rel(bdir), "manuscript_copy": rel(mdir / src.name), "A_comp": acc["A_comp"],
                              "sentence": d["scale"]["sentence"], "lock_root": doc["lock_root"]},
                     next_hint="the generated blocks are ready for the A17 manuscript revision" if not ctx.dev else
                     "development preview only; the reported campaign is B8")
