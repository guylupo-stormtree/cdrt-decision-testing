"""Report generation (requirements A13, A12.1; R-REP-1 … R-REP-5).

Every value is read from the locked campaign's own outputs: the functional records and acceptance of Lab 7,
the timing records, statistics and run manifest of Lab 8, the fixture parameters and the frozen bundle.
`generate()` returns the five generated blocks of the manuscript, the figure files and a trace of where each
value came from. RQ2 is reported as one number (D-015): T_max, the slowest update of the whole campaign, read
against the budget. Wording follows R-REP-5 as amended: "within the budget" only when T_max is at most the
budget, any exceedance is stated with its count, never "real-time". The abstract and introduction carry the
same number through ScaleAbstractText and ScaleIntroText. Development data are marked as such in every
generated sentence and caption.

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
BLOCKS = ("results_macros", "fixture_macros", "functional_table", "pathway_figure", "scale_table", "scale_figure",
          "coverage_table", "coverage_figure")
# main-15 reads these from generated/*.tex (see FILES); older manuscripts hold them inline between markers
ANCHORS = {"fixture_macros": "results_macros", "pathway_figure": "functional_table",
           "scale_figure": "scale_table", "coverage_table": "pathway_figure", "coverage_figure": "coverage_table"}   # inserted after these if absent
from ..harness.functional import CONDITIONS  # noqa: E402  (the four main-14 acceptance conditions)


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
           "protocol": next(f for f in (root / h["bundle"] / "protocol" / n for n in ("cdrt-protocol.yaml", "protocol.yaml"))
                            if f.exists())}   # the frozen capture protocol keeps its name (real: cdrt-protocol.yaml)
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
    d["pathways"] = pathways(root / h["bundle"], d["bundle"]["corpus_sha256"])
    return d


def pathways(bundle: Path, corpus_sha256: str) -> dict[str, Any]:
    """Which functions of the auditor's scope M_h each green decision's RepoAudit run reached, i.e. carried a
    None into (accepted base-check), read from the frozen corpus through the record view."""
    from ..records import view
    from ..records.assessments import BASE, assessments
    s = view.load_snapshot(bundle / "corpus", bundle / "target", corpus_sha256)
    scope = json.loads((bundle / "protocol" / "manifests" / "M_h.json").read_text())["functions"]
    rows = []
    order = ("G-main-", "G-strict-", "G-pipe-")       # main decisions together (same policy), then the others
    plan = [x["decision_id"] for x in json.loads((bundle / "stage1" / "plan.json").read_text())["decisions"]]
    for did in sorted(plan, key=lambda x: (next((i for i, p in enumerate(order) if x.startswith(p)), 3), x)):
        if view.get_decision(s, did)["decision"]["payload"]["verdict"] != "green":
            continue
        got = {r["target"] for r in assessments(s, did)["records"] if r["validator"] == BASE}
        rows.append({"decision": did, "reached": sorted(set(scope) & got)})
    return {"scope": scope, "rows": rows}


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
    from ..harness.scale import headline
    acc = d["acceptance"]
    by = {r["id"]: r for r in d["functional"]}
    rows = scale_rows(d)
    budget = float(d["manifest"]["deadline_s"])
    mark = "Development data, not a result. " if dev else ""
    lock = f"lock \\texttt{{{d['lock']['lock_root'][:12]}}}"
    before, after = (by.get(k, {}).get("observed") or {} for k in ("before", "after"))
    word = {"SUCCESS": r"\Pass{}", "FAIL": r"\Fail{}", "INCONCLUSIVE": r"\Unknown{}"}
    w_ = lambda s: word.get(s, tex(s))  # noqa: E731

    # RQ1: the before/after transition, the four conditions, the delayed result, replay, the observation
    f = (f"Before the change, conformance returned {w_(before.get('H'))} and adequacy {w_(before.get('A'))}, and the "
         f"gateway read {tex(before.get('gateway'))}. After \\texttt{{independent-check}} was required, conformance "
         f"returned {w_(after.get('H'))} and adequacy {w_(after.get('A'))}, and the gateway read {tex(after.get('gateway'))}.")
    conds = acc["acceptance"]
    if acc["A_comp"]:
        f += (f" All four acceptance conditions held in all {acc['runs']} runs, so $A_{{\\mathrm{{comp}}}}$ is true: "
              "the verdicts matched the oracle, the second module needed only registration and a profile edit, the "
              "gateway moved from proceed through no green to hold and rejected the delayed success, and no control "
              "was re-executed.")
    else:
        failing = "; ".join(f"{k} ({CONDITIONS[k].lower()}) failed on {listing([tex(x) for x in v['failing']])}"
                            for k, v in conds.items() if not v["passes"])
        f += f" $A_{{\\mathrm{{comp}}}}$ is false: {failing}."
        if before.get("A") == "FAIL" and before.get("gateway") == "hold":
            f += (" These expectations assumed that the captured decisions together met the requirement before the "
                  "change; they did not, so the gateway held throughout and there was no adequate result to withdraw "
                  "or to arrive late.")
            if all(by.get(k, {}).get("oracle_agrees") for k in ("before", "after")):
                f += (" In both cases CDRT's verdicts agreed with the independent oracle; what differed were the "
                      "scenario's expected values.")
    f += " Replay from the same locked inputs agreed." if acc["replay_agrees"] else \
        " Replay from the same locked inputs did not agree; the mismatch is kept in the records."
    cov = composition(d)
    f = cov["sentence"] + " " + f
    obs = (by.get("observation") or {}).get("observed") or {}
    if obs:
        f += (" Every judgement of the individual decisions agreed with the oracle."
              if all(v["oracle_agrees"] for v in obs.values()) else
              " Some judgements of the individual decisions differed from the oracle and are reported.")
    functional = f"{mark}The functional protocol ran on the sealed corpus under {lock}. {f}"

    # RQ2: one number, where it occurred, the change across sizes, exceedances and semantic checks
    h = headline(d["scale"]["stats"], budget)
    sizes = listing([num(r["N"]) for r in rows])
    total, over = num(h["total"]), h["over"]
    w = f"{secs(h['worst_s'])}\\,s" if h["worst_s"] is not None else "an unknown time"
    trend = (f"The slowest update grew from {secs(rows[0]['slowest_s'])}\\,s at {num(rows[0]['N'])} records to "
             f"{secs(rows[-1]['slowest_s'])}\\,s at {num(rows[-1]['N'])} records."
             if rows[0]["slowest_s"] is not None and rows[-1]["slowest_s"] is not None else "")
    semantic = ("Every cycle returned the expected verdicts and the active requirement revision."
                if not h["mismatches"] else
                f"{h['mismatches']} cycles returned an incorrect or outdated posture and are not valid completions.")
    if h["within"]:
        s = (f"{mark}Across {total} timed updates at {sizes} decision-basis records, the slowest took {w}, at "
             f"{num(h['worst_N'])} records. {trend} {semantic} Every update reached the gateway within the "
             f"{budget:g}\\,s budget for the measured workload.")
        timing = f"the slowest of {total} timed updates took {w}, within that budget"
    else:
        s = (f"{mark}Across {total} timed updates at {sizes} decision-basis records, the slowest took {w}, at "
             f"{num(h['worst_N'])} records. {trend} {semantic} {over} of {total} updates exceeded the "
             f"{budget:g}\\,s budget.")
        timing = f"the slowest of {total} timed updates took {w}, and {over} exceeded that budget"
    extra = [f"{sum(r[k] for r in rows)} {k}" for k in ("late", "timeouts") if sum(r[k] for r in rows)]
    if extra:
        s += " Recorded and kept: " + listing(extra) + "."
    held = after.get("H") == "SUCCESS" and after.get("A") == "FAIL" and after.get("gateway") == "hold"
    lead = (f"{cov['narrow']} of {cov['green']} green RepoAudit decisions were each too narrow on their own, but "
            f"together they covered {cov['covered']} of the {cov['scope']} release functions and the gateway could proceed; "
            if cov["composed_ok"] and cov["narrow"] else
            f"the green RepoAudit decisions together covered {cov['covered']} of the {cov['scope']} release functions; ")
    held_before = before.get("A") == "FAIL" and before.get("gateway") == "hold"
    if held and held_before:      # the captured decisions never met the requirement: TAIP held from the start
        functional_short = (f"The {cov['eligible']} eligible green RepoAudit decisions together covered {cov['covered']} "
                            f"of the {cov['scope']} release functions, below the {cov['tau']} requirement, so TAIP held "
                            "the gateway; when independent validation became required, conformance stayed successful, "
                            "adequacy still failed and the gateway stayed on hold")
    elif held:
        functional_short = (lead[0].upper() + lead[1:] + "when independent validation became required, conformance "
                            "stayed successful, adequacy failed and TAIP moved the gateway to hold")
    else:
        functional_short = "The functional transition did not match its expectation"
    abstract = f"{mark}{functional_short}; {timing}."
    intro = f"{mark}{functional_short[0].upper()}{functional_short[1:]}, and {timing}."
    state = "development data, not a result" if dev else f"measured (campaign {tex(d['lock']['campaign_id'])})"
    conclusion = (f"{mark}On the measured workload, $A_{{\\mathrm{{comp}}}}$ is {'true' if acc['A_comp'] else 'false'}, "
                  f"and the slowest of {total} updates, at up to {num(rows[-1]['N'])} basis records, took {w}, "
                  f"{'within' if h['within'] else 'beyond'} the {budget:g}\\,s budget.")
    return {"ResultState": state, "FunctionalResultText": functional, "ScaleResultText": s,
            "ConclusionResultText": conclusion, "ScaleFigureSentence": tex(d["scale"]["sentence"]),  # caption carries the dev mark
            # main-17's abstract reads "completes in \\ScaleAbstractText seconds for \\ScaleLargestN records": the
            # slowest update in seconds (control space at the end, so the following word keeps its space) and the
            # largest actual decision-basis size
            "ScaleAbstractText": (secs(h["worst_s"]) if h["worst_s"] is not None else "an unknown number of")
            + (" (development data, not a result)" if dev else "") + "\\ ",
            "ScaleLargestN": num(rows[-1]["N"]),
            "ScaleIntroText": intro, "ScaleWorstCase": w,
            "PathwaySentence": pathway_sentence(d["pathways"], dev), "CoverageSentence": mark + cov["sentence"]}


# ------------------------------------------------------------------ code availability: one repository
def _https(url: str) -> str:
    url = url.strip()
    if url.startswith("git@"):
        host, _, path = url[4:].partition(":")
        url = f"https://{host}/{path}"
    return url[:-4] if url.endswith(".git") else url


def availability(d: dict[str, Any], repoaudit_commit: str, tag: str) -> str:
    """One repository for the reviewer: it holds everything, and its fetch-dependencies.sh fetches ProofWeave and
    RepoAudit at the pinned versions (and not RepoAudit's own large benchmark submodules). URLs come from the repositories' own git configuration."""
    from .. import lock, paths
    cdrt = _https(lock.git("remote", "get-url", "origin") or "<CDRT repository URL>")
    pw = _https(lock.git("config", "-f", ".gitmodules", "--get", "submodule.vendor/proofweave-decision-assurance.url") or "")
    ra = _https(lock.git("config", "-f", ".gitmodules", "--get", "submodule.vendor/RepoAudit.url", cwd=paths.pwexp_checkout()) or "")
    pw_tag = d["lock"]["components"]["pwexp"].get("tag") or d["lock"]["components"]["pwexp"]["commit"][:12]
    ref = f"tag \\texttt{{{tex(tag)}}}" if tag else f"commit \\texttt{{{tex(d['lock']['git_commit'][:12])}}}"
    return (f"Everything needed to inspect and repeat the experiment is in one repository, \\url{{{cdrt}}} ({ref}). "
            f"After \\texttt{{git clone}}, its script \\texttt{{fetch-dependencies.sh}} fetches the two pinned dependencies, ProofWeave "
            f"(\\url{{{pw}}}, tag \\texttt{{{tex(pw_tag)}}}) and RepoAudit (\\url{{{ra}}}, commit "
            f"\\texttt{{{tex(repoaudit_commit[:7])}}}). The repository holds the capture declaration and protocol, the sealed "
            f"corpus, the fixtures, the oracle, the lock file and every raw record. The assessment and timing phases can be "
            f"repeated offline, without RepoAudit, a language model or an API key, with \\texttt{{cdrt lab run 3-9}}; the "
            f"capture phase (\\texttt{{cdrt lab run 0-2}}) additionally needs access to the declared model.")


# ------------------------------------------------------------------ blocks
def header(name: str, d: dict[str, Any], inputs: list[str], root: Path) -> str:
    rel = lambda p: Path(p).resolve().relative_to(root).as_posix() if Path(p).resolve().is_relative_to(root) else str(p)  # noqa: E731
    return "\n".join([f"% generator: {GENERATOR} ({name})",
                      "% inputs: " + "; ".join(f"{rel(d['src'][i])} {sha256_file(d['src'][i])[:12]}" for i in inputs),
                      f"% lock_root: {d['lock']['lock_root']}  campaign: {d['lock']['campaign_id']}",
                      f"% commit: {d['lock']['git_commit']}"
                      + ("  (working tree dirty at lock)" if d["lock"].get("working_tree_dirty") else "")])


def composition(d: dict[str, Any]) -> dict[str, Any]:
    """The composed-coverage result in numbers and one plain sentence, from the functional records."""
    by = {r["id"]: r for r in d["functional"]}
    m = (((by.get("before") or {}).get("verdicts") or {}).get("release.adequacy") or {}).get("measurements") or {}
    obs = (by.get("observation") or {}).get("observed") or {}
    main = d["params"]["selection"]["main"]
    tau = Fraction(d["params"]["tau_q"]["numerator"], d["params"]["tau_q"]["denominator"])
    tau_rel = Fraction(d["params"]["tau_rel"]["numerator"], d["params"]["tau_rel"]["denominator"])
    covered, scope = m.get("coverage_numerator", 0), m.get("coverage_denominator", 0)
    ok = bool(scope) and Fraction(covered, scope) >= tau
    narrow = sum(1 for v in obs.values() if v.get("narrow"))
    alone_ok = sum(1 for v in obs.values() if v.get("A_alone") == "SUCCESS")
    main_alone = (obs.get(main) or {}).get("coverage_alone", "")
    s = (f"On its own, the main decision covered {main_alone} of the release functions"
         f"{' (below' if (obs.get(main) or {}).get('A_alone') != 'SUCCESS' else ' (meeting'} the {share(tau)} requirement); "
         f"{alone_ok} of the {len(obs)} green decisions met the requirement alone, and {narrow} were green but narrow, "
         f"each reaching less than {share(tau_rel)} of the {m.get('observed_estate_size', 0)} functions observed across "
         f"all eligible decisions. Together the {len(m.get('eligible') or [])} eligible decisions covered {covered} of "
         f"{scope} release functions, {'meeting' if ok else 'below'} the requirement"
         + (f"; {len(m.get('excluded') or {})} decision(s) were excluded" if m.get("excluded") else "")
         + (f"; {len(m.get('drift') or [])} observed function(s) were missing from the release manifest" if m.get("drift") else "")
         + ".")
    return {"sentence": s, "covered": covered, "scope": scope, "composed_ok": ok, "narrow": narrow,
            "green": len(obs), "alone_ok": alone_ok, "estate": m.get("observed_estate_size", 0),
            "eligible": len(m.get("eligible") or []), "tau": share(tau)}


def blocks(d: dict[str, Any], dev: bool, root: Path, repoaudit_commit: str, tag: str = "",
           folder: str = "generated") -> tuple[dict[str, str], dict[str, Any]]:
    t = texts(d, dev)
    p, proto, rows = d["params"], d["protocol"], scale_rows(d)
    trace: dict[str, Any] = {}

    sha = d["bundle"]["corpus_sha256"]
    t["CodeAvailabilityText"] = availability(d, repoaudit_commit, tag)
    res = {**t, "CorpusHash": "\\allowbreak ".join(sha[i:i + 16] for i in range(0, len(sha), 16)), "PWVersion": d["lock"]["components"]["pwexp"]["tag"],
           "RepoAuditCommit": repoaudit_commit[:7], "ModelId": tex(proto["acquisition"]["models"][0]["model"]),
           "TargetRepo": tex(f"{proto['target']['repository']}@{proto['target']['commit']}")}
    for k in t:
        trace[k] = ["functional_records", "acceptance"] if "Functional" in k or "Conclusion" in k or k == "ResultState" \
            else ["timing_records", "scale_stats", "run_manifest"]
    trace["ConclusionResultText"] = ["acceptance", "scale_stats"]
    trace["PathwaySentence"] = ["bundle"]
    trace["CodeAvailabilityText"] = ["lock", "git remotes and submodules"]
    trace.update(CorpusHash=["bundle"], PWVersion=["lock"], RepoAuditCommit=["lock (pwexp checkout)"],
                 ModelId=["protocol"], TargetRepo=["protocol"])
    out = {"results_macros": "\n".join([header("results_macros", d, ["functional_records", "acceptance", "scale_stats",
                                                                        "bundle", "protocol"], root),
                                        *[macro(k, v) for k, v in res.items()]])}

    pol = d["policy_main"]
    fix = {"FixMh": num(p["M_h_size"]), "FixMq": num(p["M_q_size"]),
           "FixTauH": share(Fraction(int(pol["threshold"]["numerator"]), int(pol["threshold"]["denominator"]))),
           "FixTauQ": share(Fraction(p["tau_q"]["numerator"], p["tau_q"]["denominator"])),
           "FixAgeMax": f"{num(p['max_age_seconds'])}\\,s", "FixAssessTime": f"\\texttt{{{tex(p['t_e'])}}}",
           "FixSizes": listing([num(r["N"]) for r in rows]), "FixBasisMain": num(p["n0"]),
           "FixCoverageMain": tex(p["c_obs_count"]), "FixRunCount": num(p["captured"]),
           "FixGreenCount": num(len(p["green"])),
           "FixTauRel": share(Fraction(p["tau_rel"]["numerator"], p["tau_rel"]["denominator"])),
           "FixEstateObserved": num(composition(d)["estate"]),
           "FixComposedCoverage": f"{composition(d)['covered']}/{composition(d)['scope']}"}
    trace.update({k: ["parameters"] for k in fix}, FixTauH=["policy_main"],
                 FixEstateObserved=["functional_records"], FixComposedCoverage=["functional_records"])
    out["fixture_macros"] = "\n".join([header("fixture_macros", d, ["parameters", "policy_main"], root),
                                       *[macro(k, v) for k, v in fix.items()]])

    # Table 4 (main-14): before and after the requirement change, expected and observed
    by = {r["id"]: r for r in d["functional"]}
    word = {"SUCCESS": r"\Pass{}", "FAIL": r"\Fail{}", "INCONCLUSIVE": r"\Unknown{}"}
    cell = lambda o: f"{word.get(o.get('H'), tex(o.get('H')))} / {word.get(o.get('A'), tex(o.get('A')))} / " \
                     f"{tex(str(o.get('gateway', '')).capitalize())}"  # noqa: E731
    acc = d["acceptance"]
    lines = [header("functional_table", d, ["functional_records", "acceptance"], root),
             r"\begin{table*}[pos=t]", r"\centering\small",
             r"\caption{Before-and-after decision testing" + (" (development data, not a result)" if dev else "") +
             f". Expected values were predeclared; observed values come from the locked functional run (lock "
             f"\\texttt{{{d['lock']['lock_root'][:12]}}}). $A_{{\\mathrm{{comp}}}}$ is "
             f"{'true' if acc['A_comp'] else 'false'}; replay {'agreed' if acc['replay_agrees'] else 'did not agree'}.}}",
             r"\label{tab:functional-results}", r"\label{tab:functional-protocol}",
             r"\begin{tabularx}{\textwidth}{@{}L{.31\textwidth}L{.13\textwidth}L{.13\textwidth}L{.13\textwidth}Y@{}}",
             r"\toprule",
             r"Requirement state & Expected conformance & Expected adequacy & Expected gateway & "
             r"Observed conformance / adequacy / gateway \\", r"\midrule"]
    for key, label in (("before", r"Before: \texttt{base-check}"), ("after", r"After: adds \texttt{independent-check}")):
        r = by.get(key) or {}
        e, o = r.get("expected") or {}, r.get("observed") or {}
        lines.append(f"{label} & {word.get(e.get('H'), '')} & {word.get(e.get('A'), '')} & "
                     f"{tex(str(e.get('gateway', '')).capitalize())} & {cell(o) if o else 'Not executed'} \\\\")
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table*}"]
    out["functional_table"] = "\n".join(lines)
    trace["functional_table"] = ["functional_records", "acceptance"]

    out["pathway_figure"] = "\n".join([
        header("pathway_figure", d, ["bundle"], root), r"\begin{figure*}[pos=t]", r"\centering",
        f"\\input{{{folder}/figures/pathways.tex}}",
        r"\caption{Same green, different paths" + (" (development data, not a result)" if dev else "") +
        r". Each row is one green decision captured from RepoAudit, with the same model, target and question; each "
        r"column is a function in the auditor's scope $M_h$, ordered by how many runs reached it. A dark cell means "
        r"the run carried a \texttt{None} into that function, which is what an accepted \texttt{base-check} requires. "
        r"The verdicts are identical; the checking behind them is not. \PathwaySentence{}}",
        r"\label{fig:pathways}", r"\end{figure*}"])
    trace["pathway_figure"] = ["bundle"]

    budget = float(d["manifest"]["deadline_s"])
    lines = [header("scale_table", d, ["timing_records", "scale_stats", "run_manifest", "parameters"], root),
             r"\begin{table}[pos=tbp]", r"\centering\small",
             r"\caption{Requirement-change-to-posture latency per decision-basis size" +
             (" (development data, not a result)" if dev else "") +
             f": {rows[0]['observations']} timed updates each. $N$ basis records in all, $k$ copies of each green decision's run; the slowest "
             f"update in seconds and the updates over the {budget:g}\\,s budget. The slowest overall is $T_{{\\max}}$.}}",
             r"\label{tab:scale-results}",
             r"\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}rrrr@{}}", r"\toprule",
             r"Records $N$ & Copies $k$ & Slowest update (s) & Over budget \\", r"\midrule"]
    for r in rows:
        lines.append(f"{num(r['N'])} & {num(r['k'])} & {secs(r['slowest_s'])} & {r['exceedances']}/{r['observations']} \\\\")
    lines += [r"\bottomrule", r"\end{tabular*}", r"\end{table}"]
    out["scale_table"] = "\n".join(lines)
    trace["scale_table"] = ["scale_stats", "parameters"]

    out["scale_figure"] = "\n".join([
        header("scale_figure", d, ["timing_records", "scale_stats"], root), r"\begin{figure}[pos=tbp]", r"\centering",
        f"\\input{{{folder}/figures/scale_latency.tex}}",
        r"\caption{Requirement-change-to-posture latency at four decision-basis sizes (\FixSizes{} records), "
        f"{rows[0]['observations']} observations each on a single warm host"
        + (" (development data, not a result)" if dev else "") +
        r". Each dot is one update; the line joins the slowest update at each size; the dashed line is the 5\,s "
        r"gateway budget, with the number of updates over it above each size. "
        r"\ScaleFigureSentence{}}", r"\label{fig:scale-latency}", r"\end{figure}"])
    trace["scale_figure"] = ["timing_records", "scale_stats"]

    out["coverage_table"], out["coverage_figure"] = coverage_blocks(d, dev, root, folder)
    trace["coverage_table"] = trace["coverage_figure"] = ["functional_records", "scale_stats", "parameters"]
    out["experiment_record"] = record_block(d, dev, root, repoaudit_commit, tag)
    trace["experiment_record"] = ["bundle", "protocol", "parameters", "run_manifest", "lock"]
    return out, trace


# ------------------------------------------------------------------ the experiment record subsection (main-15)
FILES = {"cdrt-macros.tex": ("results_macros", "fixture_macros"), "cdrt-record.tex": ("experiment_record",),
         "cdrt-functional-table.tex": ("functional_table",), "cdrt-pathway-figure.tex": ("pathway_figure",),
         "cdrt-coverage-table.tex": ("coverage_table",), "cdrt-coverage-figure.tex": ("coverage_figure",),
         "cdrt-scale-table.tex": ("scale_table",), "cdrt-scale-figure.tex": ("scale_figure",)}


def coverage_blocks(d: dict[str, Any], dev: bool, root: Path, folder: str) -> tuple[str, str]:
    """Table: every green decision on its own, then composed, in capture order. Figure: composed coverage per
    admission against the requirement, with the gateway reading and each decision's own reach."""
    from ..harness.scale import headline
    by = {r["id"]: r for r in d["functional"]}
    obs = (by.get("observation") or {}).get("observed") or {}
    tl = (by.get("timeline") or {}).get("observed") or []
    p = d["params"]
    tau = Fraction(p["tau_q"]["numerator"], p["tau_q"]["denominator"])
    word = {"SUCCESS": r"\Pass{}", "FAIL": r"\Fail{}", "INCONCLUSIVE": r"\Unknown{}"}
    gw = lambda g: tex(str(g or "").capitalize())  # noqa: E731
    h = headline(d["scale"]["stats"], float(d["manifest"]["deadline_s"]))
    dmark = " (development data, not a result)" if dev else ""
    lines = [header("coverage_table", d, ["functional_records", "scale_stats", "parameters"], root),
             r"\begin{table*}[pos=t]", r"\centering\small",
             r"\caption{Green decisions on their own and composed" + dmark + r". Rows follow capture order. "
             r"\emph{Alone}: the decision's own coverage of the release manifest $M_q$ and the gateway reading if it relied "
             r"on this decision only; \emph{share}: its part of the estate observed across all eligible decisions, "
             r"with decisions below \FixTauRel{} marked narrow; \emph{composed}: coverage of $M_q$ by all decisions "
             r"admitted so far. Requirement: \FixTauQ{} of \FixMq{} functions.}",
             r"\label{tab:coverage}",
             r"\begin{tabularx}{\textwidth}{@{}lccccccY@{}}", r"\toprule",
             r"Decision & Green & Conformant & Alone & Share & Gateway alone & Composed & Gateway composed \\", r"\midrule"]
    for row in tl:
        dd = row["admitted"]
        o = obs.get(dd) or {}
        share_ = (o.get("rho") or "--") + (" (narrow)" if o.get("narrow") else "")
        lines.append(f"\\texttt{{{tex(dd)}}} & yes & {word.get(o.get('H'), '--')} & {tex(o.get('coverage_alone', '--'))} & "
                     f"{tex(share_)} & {gw(o.get('gateway_alone'))} & {tex(row['covered'])} & {gw(row['gateway'])} \\\\")
    last = tl[-1] if tl else {}
    lines += [r"\midrule",
              f"All eligible & & & & & & {tex(last.get('covered', '--'))} & {gw(last.get('gateway'))}; slowest composed "
              f"update {secs(h['worst_s'])}\\,s \\\\" if h["worst_s"] is not None else
              f"All eligible & & & & & & {tex(last.get('covered', '--'))} & {gw(last.get('gateway'))} \\\\",
              r"\bottomrule", r"\end{tabularx}", r"\end{table*}"]
    table = "\n".join(lines)
    fig = "\n".join([header("coverage_figure", d, ["functional_records", "parameters"], root),
                      r"\begin{figure}[pos=tbp]", r"\centering", f"\\input{{{folder}/figures/coverage.tex}}",
                      r"\caption{Composed coverage as green decisions are admitted in capture order" + dmark + r". Bars: "
                      r"release functions each decision covered on its own; solid line: release functions covered by all "
                      r"decisions admitted so far; dashed line: the size of the observed estate; dotted line: the "
                      r"requirement (\FixTauQ{} of \FixMq{}). The gateway reading after each admission is printed above. "
                      r"\CoverageSentence{}}", r"\label{fig:coverage}", r"\end{figure}"])
    return table, fig


def coverage_figure(d: dict[str, Any], dev: bool = False) -> str:
    """pgfplots: per admission, the decision's own release coverage (bars), the composed coverage and the observed
    estate (lines), the requirement line and the gateway reading."""
    by = {r["id"]: r for r in d["functional"]}
    obs = (by.get("observation") or {}).get("observed") or {}
    tl = (by.get("timeline") or {}).get("observed") or []
    p = d["params"]
    n_q = p["M_q_size"]
    need = float(Fraction(p["tau_q"]["numerator"], p["tau_q"]["denominator"]) * n_q)
    xs = list(range(1, len(tl) + 1))
    alone = [int(str((obs.get(r["admitted"]) or {}).get("coverage_alone", "0/1")).split("/")[0]) for r in tl]
    comp = [int(r["covered"].split("/")[0]) for r in tl]
    est = [int(r["observed_estate"] or 0) for r in tl]
    ymax = max([n_q] + est) + 2
    out = [f"% generator: {GENERATOR} (figures/coverage.tex); lock_root: {d['lock']['lock_root']}; commit: {d['lock']['git_commit']}",
           r"\begin{tikzpicture}",
           r"\begin{axis}[width=\columnwidth, height=0.62\columnwidth, ymin=0, ymax=" + str(ymax) + ",",
           f"  xmin=0.4, xmax={len(tl) + 0.6:g}, xtick={{{','.join(map(str, xs))}}},",
           "  xticklabels={" + ",".join("{\\texttt{" + tex(r["admitted"]) + "}}" for r in tl) + "},",
           r"  xticklabel style={font=\scriptsize, rotate=30, anchor=north east}, ylabel={Functions},",
           r"  tick label style={font=\scriptsize}, label style={font=\small},",
           r"  legend style={font=\scriptsize, at={(0.5,-0.36)}, anchor=north, draw=none, fill=none, legend columns=2,",
           r"    /tikz/every even column/.append style={column sep=6pt}}, legend cell align=left]",
           r"\addplot[ybar, bar width=7pt, fill=black!15, draw=black!40, area legend] coordinates {" + " ".join(f"({x},{a})" for x, a in zip(xs, alone)) + "};",
           r"\addlegendentry{covered alone}",
           r"\addplot[thick, mark=*, mark size=1.5pt, black] coordinates {" + " ".join(f"({x},{c})" for x, c in zip(xs, comp)) + "};",
           r"\addlegendentry{composed}",
           r"\addplot[dashed, black!60, mark=none] coordinates {" + " ".join(f"({x},{e})" for x, e in zip(xs, est)) + "};",
           r"\addlegendentry{observed estate}",
           f"\\addplot[dotted, thick, black!70, domain=0.4:{len(tl) + 0.6:g}] {{{need:g}}};",
           r"\addlegendentry{requirement}",
           *[f"\\node[font=\\tiny, anchor=south] at (axis cs:{x},{max(c, a) + 0.3:g}) {{{tex(str(r['gateway']))}}};"
             for x, c, a, r in zip(xs, comp, alone, tl)]]
    if dev:
        out.append(r"\node[font=\scriptsize\itshape, text=black!55, anchor=south east] at (rel axis cs:0.98,0.02) {" + DEV_MARK + "};")
    out += [r"\end{axis}", r"\end{tikzpicture}"]
    return "\n".join(out) + "\n"


def hashed(h: str, n: int = 16) -> str:
    """A long hex digest in \\texttt with break points, so it never overflows a column."""
    return r"\texttt{" + r"\allowbreak ".join(h[i:i + n] for i in range(0, len(h), n)) + "}"


def record_block(d: dict[str, Any], dev: bool, root: Path, repoaudit_commit: str, tag: str) -> str:
    """The generated "Experiment record" subsection: what was run, with every version and hash."""
    proto, p, lk, man = d["protocol"], d["params"], d["lock"], d["manifest"]
    acq, model = proto.get("acquisition") or {}, (proto.get("acquisition") or {}).get("models", [{}])[0]
    pw = lk["components"]["pwexp"]
    hw = man.get("hardware") or {}
    rows = [
        ("Target repository", f"\\texttt{{{tex(proto['target']['repository'])}}} at commit "
                              f"\\texttt{{{tex(proto['target']['commit'])}}} ({tex(proto['target'].get('language', ''))}, "
                              f"{tex(proto['target'].get('bug_type', ''))})"),
        ("Control", f"RepoAudit at commit \\texttt{{{tex(repoaudit_commit[:12])}}}, model \\texttt{{{tex(model.get('model', ''))}}}, "
                    f"temperature {acq.get('temperature')}, call depth {acq.get('call_depth')}"),
        ("Independent validator", f"Semgrep {tex(str((proto.get('semgrep') or {}).get('version', '')))}; "
                                  f"{int(acq.get('semgrep_runs') or 0)} standalone scan(s), in no decision's basis"),
        ("Captured decisions", f"{num(p['captured'])} RepoAudit runs under P1, {num(len(p['green']))} green; main decision "
                               f"\\texttt{{{tex(p['selection']['main'])}}}"),
        ("Decision ledger", f"ProofWeave \\texttt{{{tex(pw.get('tag') or '')}}} (commit \\texttt{{{tex(pw['commit'][:12])}}})"),
        ("Sealed corpus (SHA-256)", hashed(d["bundle"]["corpus_sha256"])),
        ("Protocol lock", f"root {hashed(lk['lock_root'])}; campaign \\texttt{{{tex(lk['campaign_id'])}}}"
                          + (f"; tag \\texttt{{{tex(tag)}}}" if tag else "")),
        ("Experiment code", f"cdrt-decision-testing at commit \\texttt{{{tex(lk['git_commit'][:12])}}}"
                            + (" (working tree modified at lock)" if lk.get("working_tree_dirty") else "")
                            + f"; fixtures {hashed(lk['components']['fixtures'][:32])}"),
        ("Timing host", tex(f"{hw.get('cpu') or hw.get('machine', '')}, {hw.get('cpus')} CPUs, {hw.get('memory', '')}; "
                            f"{man.get('os', '')}; Python {man.get('python', '')}")),
    ]
    lines = [header("experiment_record", d, ["bundle", "protocol", "parameters", "run_manifest"], root),
             r"\subsection{Experiment record}", r"\label{sec:experiment-record}", "",
             ("Development data, not a result. " if dev else "") +
             r"This subsection is generated from the locked campaign. Table~\ref{tab:experiment-record} identifies the "
             r"target, the control and its configuration, the captured decisions, the decision ledger, the sealed corpus, "
             r"the protocol lock, the experiment code and the timing host. Every result in Section~\ref{sec:results} is "
             r"generated from records that carry this lock root.", "",
             r"\begin{table}[pos=tbp]", r"\centering\small",
             r"\caption{Experiment record" + (" (development data, not a result)" if dev else "") +
             f", campaign \\texttt{{{tex(lk['campaign_id'])}}}.}}", r"\label{tab:experiment-record}",
             r"\begin{tabularx}{\columnwidth}{@{}L{.3\columnwidth}Y@{}}", r"\toprule", r"Item & Value \\", r"\midrule",
             *[f"{k} & {v} \\\\" for k, v in rows],
             r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    return "\n".join(lines)


def files(gen: dict[str, str]) -> dict[str, str]:
    """The generated/ folder main-15 reads with \\input: one file per place in the manuscript."""
    return {name: "".join(f"% BEGIN GENERATED:{b}\n{gen[b]}\n% END GENERATED:{b}\n" for b in blocks_)
            for name, blocks_ in FILES.items()}


# ------------------------------------------------------------------ figure: same green, different paths
GROUP = {"G-main": "main", "G-strict": "strict", "G-pipe": "pipeline"}


def pathway_sentence(pw: dict[str, Any], dev: bool) -> str:
    rows, n = pw["rows"], len(pw["scope"])
    counts = [len(r["reached"]) for r in rows]
    paths = len({tuple(r["reached"]) for r in rows})
    mark = "Development data, not a result. " if dev else ""
    if not rows:
        return mark + "No green decision was captured."
    reach = f"between {min(counts)} and {max(counts)}" if min(counts) != max(counts) else f"each {counts[0]}"
    return (f"{mark}The {len(rows)} green decisions of one model on the same code reached {reach} of the {n} "
            f"functions in the auditor's scope, by {paths} different path{'s' if paths != 1 else ''}.")


DEV_MARK = r"Development data, not a result"


def pathway_figure(d: dict[str, Any], selection: dict[str, str], dev: bool = False) -> str:
    """TikZ: one row per green decision, one cell per scope function (dark: RepoAudit carried a None into it),
    columns ordered by how many runs reached the function; reached / |M_h| at the right of each row."""
    pw = d["pathways"]
    scope = sorted(pw["scope"], key=lambda u: (-sum(u in r["reached"] for r in pw["rows"]), u))
    n, width, ch, gap = len(scope), 10.5, 0.42, 0.62
    cw = width / max(n, 1)
    chosen = {v: k for k, v in selection.items()}
    out = [f"% generator: {GENERATOR} (figures/pathways.tex); lock_root: {d['lock']['lock_root']}; "
           f"commit: {d['lock']['git_commit']}",
           r"\begin{tikzpicture}[x=1cm,y=1cm,font=\sffamily\scriptsize]"]
    if n <= 24:
        for j, u in enumerate(scope):
            out.append(f"\\node[anchor=south west,rotate=40,inner sep=1pt] at ({(j + 0.3) * cw:.3f},0.12) "
                       f"{{\\texttt{{{tex(u.split('::')[-1])}}}}};")
    else:
        out.append(f"\\node[anchor=south] at ({width / 2:.3f},0.12) "
                   r"{functions of $M_h$, ordered by how many runs reached them};")
    for i, r in enumerate(pw["rows"]):
        y = -(i + 1) * gap
        did = r["decision"]
        group = GROUP.get(did.rsplit("-", 1)[0], did)
        role = " (selected)" if did in chosen else ""
        out.append(f"\\node[anchor=east,align=right] at (-0.15,{y + ch / 2:.3f}) "
                   f"{{\\texttt{{{tex(did)}}}\\\\{group}{role} $\\cdot$ \\textbf{{green}}}};")
        for j, u in enumerate(scope):
            fill = "black!78" if u in r["reached"] else "black!8"
            out.append(f"\\fill[{fill}] ({j * cw + 0.02:.3f},{y:.3f}) rectangle ++({cw - 0.04:.3f},{ch:.3f});")
        out.append(f"\\node[anchor=west] at ({width + 0.15:.3f},{y + ch / 2:.3f}) {{{len(r['reached'])}/{n}}};")
    union = set().union(*(set(r["reached"]) for r in pw["rows"])) if pw["rows"] else set()
    y = -(len(pw["rows"]) + 1) * gap - 0.15
    out.append(f"\\draw[black!40] (0,{y + ch + 0.08:.3f}) -- ({width:.3f},{y + ch + 0.08:.3f});")
    out.append(f"\\node[anchor=east,align=right] at (-0.15,{y + ch / 2:.3f}) {{all green together}};")
    for j, u in enumerate(scope):
        fill = "black!78" if u in union else "black!8"
        out.append(f"\\fill[{fill}] ({j * cw + 0.02:.3f},{y:.3f}) rectangle ++({cw - 0.04:.3f},{ch:.3f});")
    out.append(f"\\node[anchor=west] at ({width + 0.15:.3f},{y + ch / 2:.3f}) {{{len(union)}/{n}}};")
    yl = -(len(pw["rows"]) + 2) * gap - 0.25
    out += [f"\\fill[black!78] (0,{yl:.3f}) rectangle ++(0.3,0.25);",
            f"\\node[anchor=west] at (0.35,{yl + 0.12:.3f}) "
            r"{RepoAudit carried a \texttt{None} into the function (accepted \texttt{base-check})};",
            f"\\fill[black!8] (0,{yl - 0.4:.3f}) rectangle ++(0.3,0.25);",
            f"\\node[anchor=west] at (0.35,{yl - 0.28:.3f}) {{not reached}};"]
    if dev:   # the mark travels with the figure, also when it is copied out of the paper
        out.append(f"\\node[anchor=east,font=\\sffamily\\scriptsize\\itshape,text=black!55] at ({width + 0.6:.3f},{yl - 0.28:.3f}) "
                   f"{{{DEV_MARK}}};")
    out.append(r"\end{tikzpicture}")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ figure (A12.1)
def figure(d: dict[str, Any], seed: int, dev: bool = False) -> tuple[str, str]:
    """(pgfplots .tex, .csv). All observations as a jittered strip, the slowest update per size joined by a
    line, the budget line and the exceedance count above each size. Jitter is seeded, so the file is reproducible."""
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
            + " ".join(f"({r['N']},{r['slowest_s']:.6f})" for r in rows if r["slowest_s"]) + "};",
            r"\addlegendentry{slowest update}",
            f"\\addplot[dashed, black!60, domain={xs[0] / 2:g}:{xs[-1] * 2:g}] {{{budget:g}}};",
            r"\addlegendentry{gateway budget}",
            *[f"\\node[font=\\scriptsize, anchor=south] at (axis cs:{r['N']},{budget * 1.3:g}) "
              f"{{{r['exceedances']}/{r['observations']}}};" for r in rows],
            *([r"\node[font=\scriptsize\itshape, text=black!55, anchor=south east] at (rel axis cs:0.98,0.02) {"
               + DEV_MARK + "};"] if dev else []),
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
