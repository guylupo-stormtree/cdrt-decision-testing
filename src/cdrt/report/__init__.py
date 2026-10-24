"""Report generation (requirements A13, A12.1; R-REP-1 … R-REP-5).

Every value is read from the locked campaign's own outputs: the functional records and acceptance of Lab 7,
the timing records, statistics and run manifest of Lab 8, the fixture parameters and the frozen bundle.
`generate()` returns the five generated blocks of the manuscript, the figure files and a trace of where each
value came from. Wording follows R-REP-5: "within the 5 s budget at p95 for the measured workload" only when
every p95 is at most 5 s, any exceedance is stated with its count, never "real-time". Development data are
marked as such in every generated sentence and caption.

`fill()` replaces the `% BEGIN GENERATED:<name>` … `% END GENERATED:<name>` blocks of a manuscript text.
A block the manuscript does not have yet is inserted after its anchor block and reported, so that a copy can
be compiled before the manuscript revision (A17) adds it.
"""
from __future__ import annotations

import json
import random
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

from pwexp.hashing import sha256_file

GENERATOR = "cdrt.report 1"
BLOCKS = ("results_macros", "fixture_macros", "functional_table", "scale_table", "scale_figure")
ANCHORS = {"fixture_macros": "results_macros", "scale_figure": "scale_table"}   # inserted after these if absent
ROWS = {"AC1": "Conformance/adequacy distinction", "AC2": "Second-test composition",
        "AC3": "Correct posture publication", "AC4": "Policy-at-event binding preserved",
        "AC5": "Missing or invalid record handling", "AC6": "Delayed or misrouted verdict rejection",
        "AC7": "Control isolation and code stability", "AC8": "Semantic replay"}


def tex(s: Any) -> str:
    """Escape plain text for LaTeX."""
    out = str(s)
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                 ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")):
        out = out.replace(a, b)
    return out.replace(r"\textbackslash\{\}", r"\textbackslash{}")


def num(n: int) -> str:
    return f"{n:,}"


def secs(x: float | None) -> str:
    if x is None:
        return "--"
    return f"{x:.3f}" if x < 1 else f"{x:.2f}"


def share(f: Fraction) -> str:
    p = f * 100
    return f"{p.numerator // p.denominator}\\%" if p.denominator == 1 else f"{f.numerator}/{f.denominator}"


def listing(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def macro(name: str, value: str) -> str:
    return f"\\newcommand{{\\{name}}}{{{value}}}"


# ------------------------------------------------------------------ inputs
def gather(root: Path, h: dict[str, Any], lock_doc: dict[str, Any]) -> dict[str, Any]:
    fr = root / h["functional_records"]
    tr = root / h["timing_records"]
    src = {"functional_records": fr, "acceptance": fr.with_name("acceptance.json"), "timing_records": tr,
           "scale_stats": tr.with_name("scale_stats.json"), "run_manifest": tr.with_name("run_manifest.json"),
           "parameters": root / h["parameters"], "bundle": root / h["bundle"] / "BUNDLE.json",
           "protocol": root / h["bundle"] / "protocol" / "protocol.yaml"}
    import yaml
    d = {"src": src, "lock": lock_doc,
         "functional": [json.loads(l) for l in fr.read_text().splitlines() if l.strip()],
         "acceptance": json.loads(src["acceptance"].read_text()),
         "timing": [json.loads(l) for l in tr.read_text().splitlines() if l.strip()],
         "scale": json.loads(src["scale_stats"].read_text()),
         "manifest": json.loads(src["run_manifest"].read_text()),
         "params": json.loads(src["parameters"].read_text()),
         "bundle": json.loads(src["bundle"].read_text()),
         "protocol": yaml.safe_load(src["protocol"].read_text())}
    pol = next(iter(sorted((root / h["bundle"] / "stage1" / "decisions" / h["selection"]["main"] / "policy").glob("*.json"))))
    d["policy_main"] = json.loads(pol.read_text())
    src["policy_main"] = pol
    return d


def completeness(d: dict[str, Any], expected_cycles: int, ids: list[str]) -> list[str]:
    """R-REP-1: the campaign is complete and every record carries the active lock root."""
    root = d["lock"]["lock_root"]
    problems = []
    missing = [i for i in ids if not any(r["id"] == i and r.get("executed") for r in d["functional"])]
    if missing:
        problems.append("functional protocol incomplete: " + ", ".join(missing))
    if len(d["timing"]) != expected_cycles:
        problems.append(f"{len(d['timing'])} timed cycles recorded, {expected_cycles} scheduled")
    for name in ("functional", "timing"):
        bad = sum(1 for r in d[name] if r.get("lock_root") != root)
        if bad:
            problems.append(f"{bad} {name} records do not carry lock root {root[:12]}")
    if d["acceptance"].get("lock_root") != root:
        problems.append("acceptance does not carry the active lock root")
    return problems


# ------------------------------------------------------------------ texts
def scale_rows(d: dict[str, Any]) -> list[dict[str, Any]]:
    k = dict(zip([str(n) for n in d["params"]["scale_target_sizes"]], d["params"]["scale_k"]))
    return [{**v, "size": s, "k": k[s]} for s, v in sorted(d["scale"]["stats"].items(), key=lambda x: int(x[0]))]


def texts(d: dict[str, Any], dev: bool) -> dict[str, str]:
    acc = d["acceptance"]["acceptance"]
    by = {r["id"]: r for r in d["functional"]}
    rows = scale_rows(d)
    budget = float(d["manifest"]["deadline_s"])
    mark = "Development data, not a result. " if dev else ""
    passing = [k for k, v in acc.items() if v["passes"]]
    failing = {k: v["failing"] for k, v in acc.items() if not v["passes"]}
    unattainable = [i for i, r in by.items() if r.get("kind") == "case" and r.get("attainable") is False]
    missed = [i for i, r in sorted(by.items()) if r.get("kind") == "case" and r.get("match") is False]
    lock = f"lock \\texttt{{{d['lock']['lock_root'][:12]}}}"
    if d["acceptance"]["A_comp"]:
        f = f"$A_{{\\mathrm{{comp}}}}$ is true: all {len(acc)} acceptance checks pass."
    else:
        why = "; ".join(f"{k} ({ROWS[k].lower()}) fails on {listing([tex(x) for x in v])}" for k, v in failing.items())
        f = f"$A_{{\\mathrm{{comp}}}}$ is false: {len(passing)} of {len(acc)} acceptance checks pass; {why}."
    if missed:
        f += f" Cases whose observed states differ from the expected ones: {listing(missed)}."
    if unattainable:
        f += f" Not attainable on this corpus and reported, not forced: {listing(unattainable)}."
    f9 = (by.get("F9") or {}).get("observed") or {}
    if f9:
        decisions = sorted({k.split()[0] for k in f9})
        f += (f" The other {len(decisions)} green \\texttt{{G-main}} decisions were assessed as an observation "
              "of Green Verdict Ambiguity and are not part of $A_{\\mathrm{comp}}$.")
    functional = f"{mark}The functional protocol ran in full on the sealed corpus under {lock}. {f}"

    sizes = listing([num(r["N"]) for r in rows])
    p95 = listing([secs(r["p95_s"]) for r in rows])
    total = sum(r["observations"] for r in rows)
    over = sum(r["exceedances"] for r in rows)
    within = all(r["p95_s"] is not None and r["p95_s"] <= budget for r in rows)
    s = (f"{mark}Across {num(total)} timed cycles at {sizes} decision-basis records, the nearest-rank p95 of "
         f"requirement-change-to-posture latency was {p95}\\,s respectively.")
    s += f" This is within the {budget:g}\\,s budget at p95 for the measured workload." if within else \
        " The p95 exceeds the budget at " + listing([num(r["N"]) for r in rows if r["p95_s"] is None or r["p95_s"] > budget]) + " records."
    s += " No observation exceeded the budget." if over == 0 else f" {over} of {num(total)} observations exceeded it."
    extra = [f"{sum(r[k] for r in rows)} {k}" for k in ("mismatches", "late", "timeouts") if sum(r[k] for r in rows)]
    if extra:
        s += " Recorded and kept: " + listing(extra) + "."
    state = "development data, not a result" if dev else f"measured (campaign {tex(d['lock']['campaign_id'])})"
    conclusion = (f"{mark}On the measured workload, $A_{{\\mathrm{{comp}}}}$ is "
                  f"{'true' if d['acceptance']['A_comp'] else 'false'}, and the p95 latency "
                  f"{'stays within' if within else 'exceeds'} the {budget:g}\\,s budget at "
                  f"{'every size' if within else 'some sizes'} up to {num(rows[-1]['N'])} basis records.")
    return {"ResultState": state, "FunctionalResultText": functional, "ScaleResultText": s,
            "ConclusionResultText": conclusion, "ScaleFigureSentence": tex(d["scale"]["sentence"])}   # the caption carries the dev mark


# ------------------------------------------------------------------ blocks
def header(name: str, d: dict[str, Any], inputs: list[str], root: Path) -> str:
    rel = lambda p: Path(p).resolve().relative_to(root).as_posix() if Path(p).resolve().is_relative_to(root) else str(p)  # noqa: E731
    return "\n".join([f"% generator: {GENERATOR} ({name})",
                      "% inputs: " + "; ".join(f"{rel(d['src'][i])} {sha256_file(d['src'][i])[:12]}" for i in inputs),
                      f"% lock_root: {d['lock']['lock_root']}  campaign: {d['lock']['campaign_id']}",
                      f"% commit: {d['lock']['git_commit']}"
                      + ("  (working tree dirty at lock)" if d["lock"].get("working_tree_dirty") else "")])


def blocks(d: dict[str, Any], dev: bool, root: Path, repoaudit_commit: str) -> tuple[dict[str, str], dict[str, Any]]:
    t = texts(d, dev)
    p, proto, rows = d["params"], d["protocol"], scale_rows(d)
    trace: dict[str, Any] = {}

    res = {**t, "CorpusHash": d["bundle"]["corpus_sha256"], "PWVersion": d["lock"]["components"]["pwexp"]["tag"],
           "RepoAuditCommit": repoaudit_commit[:7], "ModelId": tex(proto["acquisition"]["models"][0]["model"]),
           "TargetRepo": tex(f"{proto['target']['repository']}@{proto['target']['commit']}")}
    for k in t:
        trace[k] = ["functional_records", "acceptance"] if "Functional" in k or "Conclusion" in k or k == "ResultState" \
            else ["timing_records", "scale_stats", "run_manifest"]
    trace["ConclusionResultText"] = ["acceptance", "scale_stats"]
    trace.update(CorpusHash=["bundle"], PWVersion=["lock"], RepoAuditCommit=["lock (pwexp checkout)"],
                 ModelId=["protocol"], TargetRepo=["protocol"])
    out = {"results_macros": "\n".join([header("results_macros", d, ["functional_records", "acceptance", "scale_stats",
                                                                        "bundle", "protocol"], root),
                                        *[macro(k, v) for k, v in res.items()]])}

    pol = d["policy_main"]
    fix = {"FixMh": num(p["M_h_size"]), "FixMq": num(p["M_q_size"]),
           "FixTauH": share(Fraction(int(pol["threshold"]["numerator"]), int(pol["threshold"]["denominator"]))),
           "FixTauQ": share(Fraction(p["tau_q_rev2"]["numerator"], p["tau_q_rev2"]["denominator"])),
           "FixTauQb": share(Fraction(p["tau_q_rev3b"]["numerator"], p["tau_q_rev3b"]["denominator"])),
           "FixAgeMax": f"{num(p['max_age_seconds'])}\\,s", "FixAssessTime": f"\\texttt{{{tex(p['t_e'])}}}",
           "FixSizes": listing([num(r["N"]) for r in rows]), "FixBasisMain": num(p["n0"]),
           "FixCoverageMain": tex(p["c_obs_count"])}
    trace.update({k: ["parameters"] for k in fix}, FixTauH=["policy_main"])
    out["fixture_macros"] = "\n".join([header("fixture_macros", d, ["parameters", "policy_main"], root),
                                       *[macro(k, v) for k, v in fix.items()]])

    acc = d["acceptance"]["acceptance"]
    lines = [header("functional_table", d, ["functional_records", "acceptance"], root),
             r"\begin{table}[pos=tbp]", r"\centering\small",
             r"\caption{Functional results" + (" (development data, not a result)" if dev else "") +
             f", lock \\texttt{{{d['lock']['lock_root'][:12]}}}. A failing check names the cases behind it.}}",
             r"\label{tab:functional-results}", r"\begin{tabularx}{\columnwidth}{@{}Yl@{}}", r"\toprule",
             r"Acceptance check & Outcome \\", r"\midrule"]
    for k, row in ROWS.items():
        v = acc[k]
        lines.append(f"{row} & {'Pass' if v['passes'] else 'Fail (' + ', '.join(tex(x) for x in v['failing']) + ')'} \\\\")
    lines += [r"\midrule", f"Overall $A_{{\\mathrm{{comp}}}}$ & {'True' if d['acceptance']['A_comp'] else 'False'} \\\\",
              r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    out["functional_table"] = "\n".join(lines)
    trace["functional_table"] = ["acceptance"]

    budget = float(d["manifest"]["deadline_s"])
    lines = [header("scale_table", d, ["timing_records", "scale_stats", "run_manifest", "parameters"], root),
             r"\begin{table}[pos=tbp]", r"\centering\small",
             r"\caption{Requirement-change-to-posture latency per decision-basis size" +
             (" (development data, not a result)" if dev else "") +
             f": {rows[0]['observations']} timed cycles each. $N$ basis records, $k$ copies of the main run; median, "
             f"nearest-rank p95 and maximum in seconds; Over counts observations above the {budget:g}\\,s budget.}}",
             r"\label{tab:scale-results}",
             r"\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}rrrrrr@{}}", r"\toprule",
             r"$N$ & $k$ & Median & p95 & Max & Over \\", r"\midrule"]
    for r in rows:
        lines.append(f"{num(r['N'])} & {num(r['k'])} & {secs(r['median_s'])} & {secs(r['p95_s'])} & {secs(r['max_s'])} & "
                     f"{r['exceedances']}/{r['observations']} \\\\")
    lines += [r"\bottomrule", r"\end{tabular*}", r"\end{table}"]
    out["scale_table"] = "\n".join(lines)
    trace["scale_table"] = ["scale_stats", "parameters"]

    out["scale_figure"] = "\n".join([
        header("scale_figure", d, ["timing_records", "scale_stats"], root), r"\begin{figure}[pos=tbp]", r"\centering",
        r"\input{figures/scale_latency.tex}",
        r"\caption{Requirement-change-to-posture latency at four decision-basis sizes (\FixSizes{} records), "
        f"{rows[0]['observations']} observations each on a single warm host"
        + (" (development data, not a result)" if dev else "") +
        r". Markers show the nearest-rank p95 and the median; the dashed line is the 5\,s gateway budget. "
        r"\ScaleFigureSentence{}}", r"\label{fig:scale-latency}", r"\end{figure}"])
    trace["scale_figure"] = ["timing_records", "scale_stats"]
    return out, trace


# ------------------------------------------------------------------ figure (A12.1)
def figure(d: dict[str, Any], seed: int) -> tuple[str, str]:
    """(pgfplots .tex, .csv). All observations as a jittered strip, p95 joined by a line, medians, the
    budget line and the exceedance count above each size. Jitter is seeded, so the file is reproducible."""
    rows = scale_rows(d)
    budget = float(d["manifest"]["deadline_s"])
    rng = random.Random(seed)
    csv = ["size,N,block,t_assess_s,completed,match"]
    strip = []
    for r in sorted(d["timing"], key=lambda r: (r["N"], r["block"])):
        csv.append(f"{r['size']},{r['N']},{r['block']},{'' if r['t_assess_s'] is None else repr(r['t_assess_s'])},"
                   f"{r['completed']},{r['match']}")
        if r["t_assess_s"] is not None:
            strip.append(f"{r['N'] * 10 ** rng.uniform(-0.035, 0.035):.4f} {r['t_assess_s']:.6f}")
    ys = [r["t_assess_s"] for r in d["timing"] if r["t_assess_s"]]
    ymin, ymax = min(ys + [budget]) / 2, max(ys + [budget]) * 4
    xs = [r["N"] for r in rows]
    tikz = [f"% generator: {GENERATOR} (figures/scale_latency.tex); lock_root: {d['lock']['lock_root']}; "
            f"commit: {d['lock']['git_commit']}",
            r"\begin{tikzpicture}",
            r"\begin{axis}[width=\columnwidth, height=0.72\columnwidth, xmode=log, ymode=log,",
            f"  xmin={xs[0] / 2:g}, xmax={xs[-1] * 2:g}, ymin={ymin:.6g}, ymax={ymax:.6g},",
            r"  xlabel={Decision-basis records $N$}, ylabel={$T_{\mathrm{assess}}$ (s)},",
            r"  xtick={" + ",".join(str(x) for x in xs) + "}, xticklabels={" + ",".join(f"{{{num(x)}}}" for x in xs) + "},",
            r"  tick label style={font=\scriptsize}, label style={font=\small},",
            r"  legend style={font=\scriptsize, at={(0.03,0.80)}, anchor=north west, draw=none, fill=none},",
            r"  legend cell align=left]",
            r"\addplot[only marks, mark=*, mark size=0.8pt, black!30] table {",
            *strip, "};", r"\addlegendentry{observations}",
            r"\addplot[thick, mark=square*, mark size=1.6pt, black] coordinates {"
            + " ".join(f"({r['N']},{r['p95_s']:.6f})" for r in rows if r["p95_s"]) + "};", r"\addlegendentry{p95}",
            r"\addplot[only marks, mark=o, mark size=1.8pt, black!70] coordinates {"
            + " ".join(f"({r['N']},{r['median_s']:.6f})" for r in rows if r["median_s"]) + "};",
            r"\addlegendentry{median}",
            f"\\addplot[dashed, black!60, domain={xs[0] / 2:g}:{xs[-1] * 2:g}] {{{budget:g}}};",
            r"\addlegendentry{gateway budget}",
            *[f"\\node[font=\\scriptsize, anchor=south] at (axis cs:{r['N']},{budget * 1.3:g}) "
              f"{{{r['exceedances']}/{r['observations']}}};" for r in rows],
            r"\end{axis}", r"\end{tikzpicture}"]
    return "\n".join(tikz) + "\n", "\n".join(csv) + "\n"


# ------------------------------------------------------------------ manuscript
BLOCK = r"% BEGIN GENERATED:{n}\n.*?% END GENERATED:{n}"


def fill(text: str, generated: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """(filled text, replaced blocks, inserted blocks)."""
    replaced, inserted = [], []
    for n in BLOCKS:
        body = f"% BEGIN GENERATED:{n}\n{generated[n]}\n% END GENERATED:{n}"
        pat = re.compile(BLOCK.format(n=re.escape(n)), re.S)
        if pat.search(text):
            text = pat.sub(lambda _m: body, text, count=1)
            replaced.append(n)
            continue
        m = re.search(r"% END GENERATED:" + re.escape(ANCHORS[n]) + r"\n", text) if n in ANCHORS else None
        if not m:
            raise ValueError(f"manuscript has neither block {n} nor an anchor to insert it after")
        text = text[: m.end()] + body + "\n" + text[m.end():]
        inserted.append(n)
    if "pgfplots" not in text.split(r"\begin{document}")[0]:
        text = text.replace(r"\usetikzlibrary{", "\\usepackage{pgfplots}\n\\pgfplotsset{compat=1.18}\n\\usetikzlibrary{", 1)
        inserted.append("pgfplots (preamble)")
    return text, replaced, inserted
