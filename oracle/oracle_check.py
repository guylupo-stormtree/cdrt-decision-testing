"""CDRT oracle (R-ORC-1 … R-ORC-4). Standard library only; imports nothing from cdrt, pwexp or fixtures.

It reads the frozen bundle directly: the Stage 1 run bundles (RepoAudit's dfbscan.log and detect_info.json,
Semgrep's semgrep.json and manifest.json), the decision bundles (context, decision, policy bytes), the scope
manifests and the target source. It applies its own `ast` resolution and its own reading of RepoAudit's
log to decide, for one decision, which targets have an accepted assessment by each validator:

  base-check(u)         a RepoAudit basis run carried a None INTO u from another function (the analyser was
                        asked about u with the value returned by a callee, or with a parameter that a caller's
                        flow fact names as an argument at a call of u), and no RepoAudit finding involves u
  independent-check(u)  a Semgrep basis run scanned u's file and no Semgrep result lies inside u

From those it computes coverage (Eq. 3, exact fractions), corroboration (Eq. 4), age (Eq. 6) and the
expected conformance H and adequacy A states. A target counts as covered (W in Eq. 3) when it has an
accepted assessment by the control, base-check; the other listed validators corroborate the covered
targets (Eq. 4). From those the oracle derives the
expected conformance H and adequacy A states. Observation times: RepoAudit log times, interpreted with the
bundle's declared log_utc_offset (CAPTURE.json); a Semgrep assessment takes its run's recorded start.

  python oracle/oracle_check.py conformance BUNDLE DECISION
  python oracle/oracle_check.py adequacy BUNDLE DECISION PARAMS.json
  python oracle/oracle_check.py select BUNDLE                 the selection rule R-CAP-5 (R-ORC-4; main only)
  python oracle/oracle_check.py batch BUNDLE REQUESTS.json    [{kind: conformance|adequacy, decision, params}]
"""
from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path

ENTRY = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+) - [A-Z]+ - ", re.M)
TARGET = re.compile(r"Now I will give you a target function with the source point [`'](.*?)[`'] at line \d+:"
                    r"\s*```\w*\s*\n(.*?)```", re.S)
DEF = re.compile(r"^\s*(?:\d+\.\s*)?(?:async\s+)?def\s+(\w+)", re.M)
VALUE = re.compile(r"\(\((.*?), (/[^,]*?), (-?\d+), (-?\d+)\), ValueLabel\.(\w+)\)")
SUCCESS, FAIL, INCONCLUSIVE = "SUCCESS", "FAIL", "INCONCLUSIVE"


# ------------------------------------------------------------------ target
class Target:
    def __init__(self, root: Path):
        self.spans: dict[str, tuple[str, int, int]] = {}
        self.names: dict[str, list[str]] = {}
        self.params: dict[str, set[str]] = {}
        self.calls: dict[tuple[str, int], set[str]] = {}
        for p in sorted(Path(root).rglob("*.py")):
            rel = p.relative_to(root).as_posix()
            for n in ast.walk(ast.parse(p.read_text(errors="replace"))):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fid = f"{rel}::{n.name}"
                    self.spans[fid] = (rel, n.lineno, n.end_lineno or n.lineno)
                    self.names.setdefault(n.name, []).append(fid)
                    a = n.args
                    self.params[fid] = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
                elif isinstance(n, ast.Call):
                    f = n.func
                    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                    for line in range(n.lineno, (n.end_lineno or n.lineno) + 1):
                        if name:
                            self.calls.setdefault((rel, line), set()).add(name)

    def unique(self, name: str | None) -> str | None:
        c = self.names.get(name or "", [])
        return c[0] if len(c) == 1 else None

    def at(self, rel: str, line: int) -> str | None:
        best = None
        for fid, (f, a, b) in self.spans.items():
            if f == rel and a <= line <= b and (best is None or b - a < best[1]):
                best = (fid, b - a)
        return best[0] if best else None


def _rel(path: str, root: str) -> str:
    root = root.rstrip("/")
    return path[len(root) + 1:] if root and path.startswith(root + "/") else path


def _utc(stamp: str, offset: str) -> datetime | None:
    try:
        naive = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f")
        sign = 1 if offset[0] == "+" else -1
        h, m = offset[1:].split(":")
        return (naive - sign * timedelta(hours=int(h), minutes=int(m))).replace(tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


def _iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


# ------------------------------------------------------------------ evidence per run
def repoaudit_accepted(run: Path, target: Target, offset: str) -> dict[str, datetime | None]:
    """{target: earliest time RepoAudit carried a None into it} for targets with no finding involving them."""
    man = json.loads((run / "manifest.json").read_text())
    cmd = man.get("cmd") or []
    root = cmd[cmd.index("--project-path") + 1] if "--project-path" in cmd else ""
    text = (run / "dfbscan.log").read_text(errors="replace") if (run / "dfbscan.log").exists() else ""
    starts = [(m.start(), m.group(1)) for m in ENTRY.finditer(text)] + [(len(text), "")]
    into: dict[str, datetime | None] = {}
    by_param: dict[str, datetime | None] = {}
    passed: set[tuple[str, str]] = set()

    def note(d: dict, fid: str, t: datetime | None) -> None:
        if fid not in d or (t and (d[fid] is None or t < d[fid])):
            d[fid] = t

    for (a, stamp), (z, _) in zip(starts, starts[1:]):
        entry = text[a:z]
        head = entry.split("\n", 1)[0]
        t = _utc(stamp, offset)
        if "Output of intra-procedural data-flow analyzer" in head:
            for _, path, line, _, label in VALUE.findall(entry):
                if label == "ARG":
                    rel = _rel(path, root)
                    caller = target.at(rel, int(line))
                    for name in target.calls.get((rel, int(line)), ()):
                        callee = target.unique(name)
                        if caller and callee and callee != caller:
                            passed.add((caller, callee))
        elif " - Prompt:" in head and "does the following data-flow propagation path" not in entry:
            found = TARGET.findall(entry)
            if not found:
                continue
            src, code = found[-1]
            d = DEF.search(code)
            fid = target.unique(d.group(1)) if d else None
            if not fid:
                continue
            try:
                expr = ast.parse(src.strip().strip("`"), mode="eval").body
            except SyntaxError:
                continue
            if isinstance(expr, ast.Call):
                f = expr.func
                callee = target.unique(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None)
                if callee and callee != fid:
                    note(into, fid, t)
            elif isinstance(expr, ast.Name) and expr.id in target.params.get(fid, set()):
                note(by_param, fid, t)
    for caller, callee in passed:
        if callee in by_param:
            note(into, callee, by_param[callee])
    bad = set()
    if (run / "detect_info.json").exists():
        for rep in (json.loads((run / "detect_info.json").read_text() or "{}") or {}).values():
            files, names = (rep.get("relevant_functions") or [[], []])[:2]
            bad |= {f"{_rel(f, root)}::{n}" for f, n in zip(files, names)}
    return {u: t for u, t in into.items() if u not in bad}


def semgrep_accepted(run: Path, target: Target) -> dict[str, datetime | None]:
    man = json.loads((run / "manifest.json").read_text())
    root = (man.get("cmd") or [""])[-1]
    doc = json.loads((run / "semgrep.json").read_text() or "{}")
    scanned = {_rel(p, root) for p in doc.get("paths", {}).get("scanned", [])}
    bad = {target.at(_rel(r.get("path", ""), root), (r.get("start") or {}).get("line", -1)) for r in doc.get("results", [])}
    t = _iso(man.get("start"))
    return {u: t for u, (f, _, _) in target.spans.items() if f in scanned and u not in bad}


# ------------------------------------------------------------------ bundle and decisions
class Bundle:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.s1 = self.path / "stage1"
        self.target = Target(self.path / "target")
        self.offset = json.loads((self.path / "CAPTURE.json").read_text())["log_utc_offset"]

    def decisions(self) -> list[str]:
        """Decision ids in run order (the Stage 1 schedule)."""
        plan = json.loads((self.s1 / "plan.json").read_text())
        return [d["decision_id"] for d in plan["decisions"]]

    def decision(self, did: str) -> dict:
        d = self.s1 / "decisions" / did
        man = json.loads((d / "manifest.json").read_text())
        for name, h in man["files"].items():
            if _sha256(d / name) != h:
                raise ValueError(f"{did}/{name} does not match its bundle manifest")
        ctx = json.loads((d / "decision_context.json").read_text())
        return {"context": ctx, "decision": json.loads((d / "decision.json").read_text()),
                "policy": json.loads((d / ctx["policy_ref"]["file"]).read_bytes()),
                "policy_ok": _sha256(d / ctx["policy_ref"]["file"]) == ctx["policy_ref"]["sha256"]}

    def manifest(self, ref: dict) -> list[str] | None:
        f = self.path / "protocol" / ref["file"]
        if not f.is_file() or _sha256(f) != ref["sha256"]:
            return None
        return json.loads(f.read_text())["functions"]

    def assessments(self, did: str) -> dict[str, dict[str, datetime | None]]:
        """{validator: {target: time}} accepted in the decision's basis runs."""
        out: dict[str, dict[str, datetime | None]] = {"base-check": {}, "independent-check": {}}
        for run in self.decision(did)["context"]["basis_runs"]:
            if run.startswith("semgrep/"):
                got, v = semgrep_accepted(self.s1 / "semgrep" / run.split("/", 1)[1], self.target), "independent-check"
            else:
                got, v = repoaudit_accepted(self.s1 / "repoaudit" / run, self.target, self.offset), "base-check"
            for u, t in got.items():
                if u not in out[v] or (t and (out[v][u] is None or t < out[v][u])):
                    out[v][u] = t
        return out


def _sha256(p: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _frac(x: dict) -> Fraction:
    return Fraction(int(x["numerator"]), int(x["denominator"]))


def licence(acc: dict, scope: list[str], tau: Fraction, validators: list[str]) -> dict:
    """Coverage (W = targets with an accepted base-check) and corroboration (Eqs. 3-5)."""
    covered = sorted(u for u in scope if u in acc.get("base-check", {}))
    c = Fraction(len(covered), len(scope)) if scope else Fraction(0)
    missing = {u: [v for v in validators if u not in acc.get(v, {})] for u in covered}
    missing = {u: m for u, m in missing.items() if m}
    return {"coverage": f"{len(covered)}/{len(scope)}", "covered": covered, "coverage_ok": c >= tau,
            "corroboration_ok": not missing, "missing_validators": missing}


def conformance(bundle: Bundle, did: str) -> dict:
    d = bundle.decision(did)
    pol = d["policy"]
    if not d["policy_ok"]:
        return {"state": INCONCLUSIVE, "reason": "policy-at-event does not match its digest"}
    scope = bundle.manifest(pol["manifest"])
    if scope is None:
        return {"state": INCONCLUSIVE, "reason": "policy manifest unresolvable"}
    r = licence(bundle.assessments(did), scope, _frac(pol["threshold"]), pol["validators"])
    r["state"] = SUCCESS if r["coverage_ok"] and r["corroboration_ok"] else FAIL
    return r


def adequacy(bundle: Bundle, did: str, params: dict) -> dict:
    """params: manifest {file, sha256}, minimum_coverage {numerator, denominator}, validators, max_age_seconds,
    assessment_time (ISO UTC)."""
    scope = bundle.manifest(params["manifest"])
    if scope is None:
        return {"state": INCONCLUSIVE, "reason": "manifest unresolvable"}
    acc = bundle.assessments(did)
    r = licence(acc, scope, _frac(params["minimum_coverage"]), params["validators"])
    te = _iso(params.get("assessment_time"))
    times = [acc[v][u] for u in r["covered"] for v in params["validators"] if u in acc.get(v, {})]  # q's own validators
    if te is None or any(t is None for t in times) or any(t > te for t in times):
        age_state, r["max_age_seconds"] = None, None        # missing time, or a record after t_e: unresolved
    else:
        age = max(((te - t).total_seconds() for t in times), default=0.0)
        r["max_age_seconds"] = age
        age_state = age <= params["max_age_seconds"]
    r["age_ok"] = age_state
    if not r["coverage_ok"] or not r["corroboration_ok"] or age_state is False:
        r["state"] = FAIL
    elif age_state is None:
        r["state"] = INCONCLUSIVE
    else:
        r["state"] = SUCCESS
    return r


def select(bundle: Bundle) -> dict:
    """R-CAP-5 as narrowed by main-14: the main decision is the first GREEN G-main decision (run order) that the
    oracle judges conformant under its policy. Every G-main decision is listed with its verdict and H."""
    out = {"main": None, "main_candidates": {}}
    for did in bundle.decisions():
        if not did.startswith("G-main-"):
            continue
        green = bundle.decision(did)["decision"]["verdict"] == "green"
        h = conformance(bundle, did)["state"] if green else None
        out["main_candidates"][did] = {"green": green, "H": h}
        if green and h == SUCCESS and out["main"] is None:
            out["main"] = did
    return out


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_jsonable(v) for v in x]
    return x.isoformat() if isinstance(x, datetime) else x


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    b = Bundle(Path(argv[1]))
    if argv[0] == "conformance":
        out = conformance(b, argv[2])
    elif argv[0] == "adequacy":
        out = adequacy(b, argv[2], json.loads(Path(argv[3]).read_text()))
    elif argv[0] == "select":
        out = select(b)
    elif argv[0] == "batch":
        out = [conformance(b, q["decision"]) if q["kind"] == "conformance" else adequacy(b, q["decision"], q["params"])
               for q in json.loads(Path(argv[2]).read_text())]
    else:
        print(__doc__)
        return 2
    print(json.dumps(_jsonable(out), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
