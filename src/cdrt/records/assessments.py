"""Assessment records: the decision basis as the decision tests see it (manuscript Sec. 3.5).

For one decision, every authentic record of its basis runs is read (R-TST-5: no shortcuts) and turned into
assessment records {target, validator, run, record_ids, time}, one per (run, target, validator):

  base-check         the RepoAudit run carried a None INTO the target from another function (ProofWeave
                     pathway step), the step's records are all in the basis, and no RepoAudit finding of
                     that run involves the target
  independent-check  the Semgrep run scanned the target's file and none of its findings lies in the target

Observation time = the ProofWeave record `time` (R-TST-2): for base-check, the earliest analysis-unit record
behind the step, read in the declared log time offset; for independent-check, the Semgrep run's verdict
record (the run start). A missing or unreadable time is kept as None, never guessed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .view import DecisionView, Snapshot, get_decision

BASE, INDEPENDENT = "base-check", "independent-check"


def utc_time(stamp: str | None, offset: str | None) -> str | None:
    """ISO UTC for a ProofWeave record time; None when it cannot be read unambiguously."""
    if not stamp:
        return None
    try:
        t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if t.tzinfo:
            return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        pass
    if not offset:
        return None
    try:
        naive = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f")
        sign = 1 if offset[0] == "+" else -1
        h, m = offset[1:].split(":")
        t = naive - sign * timedelta(hours=int(h), minutes=int(m))
        return t.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (ValueError, IndexError):
        return None


def _findings(s: Snapshot, run: str) -> set[str]:
    out = set()
    for e in s.store.out_edges(f"run:{run}", "reported"):
        out |= {x["dst"].removeprefix("fn:") for x in s.store.out_edges(e["dst"], "involves") if x["dst"].startswith("fn:")}
    return out


def assessments(s: Snapshot, decision_id: str, dv: DecisionView | None = None) -> dict[str, Any]:
    """`dv`: the cycle's shared retrieval of this decision (otherwise retrieved here)."""
    d = dv.decision if dv else get_decision(s, decision_id)
    if d["status"] == "unavailable":
        return {"status": "unavailable", "records": []}
    basis = list(dv.basis) if dv else s.query.basis(decision_id)["records"]
    by_hash = {r["record_hash"]: r for r in basis}
    runs = d["binding"]["payload"]["basis_runs"]
    by_run: dict[str, list[dict[str, Any]]] = {}       # one pass over the basis (R-SCL-10: linear in N)
    for r in basis:
        by_run.setdefault(r["run"], []).append(r)
    out: list[dict[str, Any]] = []
    for run in runs:
        recs = by_run.get(run, [])
        if any(r["event_type"] == "semgrep.scan" for r in recs) or run.startswith("semgrep/"):
            verdict = next((r for r in recs if r["event_type"] == "harness.run_verdict"), None)
            t = utc_time(verdict["time"], s.log_utc_offset) if verdict else None
            files = {f for r in recs if r["event_type"] == "semgrep.scan" for f in r["payload"].get("scanned", [])}
            bad = _findings(s, run)
            for n in s.store.nodes().values():
                a = n["attrs"]
                if n["kind"] == "function" and a.get("resolved") and a.get("file") in files:
                    u = f"{a['file']}::{a['name']}"
                    if u not in bad:
                        ids = sorted(r["id"] for r in recs if r["event_type"] in ("semgrep.scan", "harness.run_verdict"))
                        out.append({"target": u, "validator": INDEPENDENT, "run": run, "record_ids": ids, "time": t})
            continue
        bad = _findings(s, run)
        best: dict[str, dict[str, Any]] = {}
        for (a, b), step in s.query.pathway(run).items():
            if not all(h in by_hash for h in step["refs"]):
                continue                                  # a step resting on records outside the basis never counts
            u = b.removeprefix("fn:")
            if u in bad:
                continue
            units = [by_hash[h] for h in step["refs"] if by_hash[h]["event_type"] == "repoaudit.analysis_unit"]
            times = [utc_time(x["time"], s.log_utc_offset) for x in units]
            t = None if (not times or any(x is None for x in times)) else min(times)
            ids = sorted(by_hash[h]["id"] for h in step["refs"])
            cur = best.get(u)
            if cur is None or (t is not None and (cur["time"] is None or t < cur["time"])):
                best[u] = {"target": u, "validator": BASE, "run": run, "record_ids": ids, "time": t}
        out.extend(best[u] for u in sorted(best))
    return {"status": d["status"], "records": out}
