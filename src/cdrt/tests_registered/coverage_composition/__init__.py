"""coverage-composition@1.0: is the release covered by the evidence of all eligible decisions together?

An LLM auditor may reach different functions on every run while every run is GREEN. This test answers the
current coverage requirement from the union of what eligible decisions actually checked, instead of from
any single GREEN verdict. Per decision in the declared set:

  eligible   GREEN, complete record and binding, the declared repository, commit and bug type, not synthetic
             (unless allowed), conformant under its own policy-at-event (conformance-check@1.0, reused as
             approved), and every supporting observation readable, not after t_e and within Delta_q
  excluded   otherwise, with the first failing reason

Over the eligible decisions R:
  E(R)       the observed estate: every function some eligible decision carried a None into
  C_acc      |E ∩ M_q| / |M_q| against the profile's tau_q (each function counted once)
  J          every covered function of M_q has each required validator from some eligible decision
  rho(r)     |W_r| / |E|: how much of the estate observed so far decision r reached; below the profile's
             tau_rel the decision is GREEN but narrow
  drift      E \\ M_q: functions the control reaches that the declared release manifest does not list

SUCCESS iff C_acc >= tau_q and J. A shortfall is FAIL only when every decision record in the set is complete
(absence needs completeness), otherwise INCONCLUSIVE. Narrow decisions are reported, never added up.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any

from .. import conformance_check
from ..common import BASE, FAIL, INCONCLUSIVE, SUCCESS, frac, parse_utc

ID, VERSION = "coverage-composition", "1.0"


def _eligibility(d: dict[str, Any], params: dict[str, Any], validators: list[str]) -> tuple[str | None, float | None]:
    """(first exclusion reason or None, age in seconds of the decision's oldest supporting observation)."""
    if d.get("verdict") != "green":
        return "not GREEN", None
    if d.get("record_status") != "complete":
        return "decision record incomplete", None
    if d.get("synthetic") and not params.get("allow_synthetic"):
        return "synthetic record", None
    ctx = params.get("context") or {}
    if any(ctx.get(k) is not None and (d.get("intent") or {}).get(k) != ctx[k] for k in ("repo", "commit", "bug_type")):
        return "different repository, commit or bug type", None
    h = conformance_check.evaluate(d, {})["state"]
    if h != SUCCESS:
        return f"not conformant under its own policy-at-event ({h})", None
    te = parse_utc(params.get("assessment_time"))
    times = [parse_utc(r.get("time")) for r in d["assessments"] if r["validator"] in validators]
    if te is None or any(t is None for t in times):
        return "unreadable observation time", None
    if any(t > te for t in times):
        return "observation after the assessment time", None
    age = max(((te - t).total_seconds() for t in times), default=0.0)
    if age > float(params["max_age_seconds"]):
        return "observations older than the maximum age", age
    return None, age


def evaluate(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    scope = inputs.get("manifest")
    if scope is None:
        return {"state": INCONCLUSIVE, "measurements": {}, "reasons": ["release manifest unresolvable"]}
    scope = sorted(set(scope))
    validators = list(params["validators"])
    eligible, excluded, ages = [], {}, []
    for d in inputs["decisions"]:
        why, age = _eligibility(d, params, validators)
        if why:
            excluded[d["decision_id"]] = why
        else:
            eligible.append(d)
            ages.append(age)
    reached = {d["decision_id"]: {r["target"] for r in d["assessments"] if r["validator"] == BASE} for d in eligible}
    estate = set().union(*reached.values()) if reached else set()
    covered = sorted(estate & set(scope))
    accepted = {(r["target"], r["validator"]) for d in eligible for r in d["assessments"]}
    missing = {u: [v for v in validators if (u, v) not in accepted] for u in covered}
    missing = {u: m for u, m in missing.items() if m}
    tau, tau_rel = frac(params["minimum_coverage"]), frac(params["relative_threshold"])
    c_acc = Fraction(len(covered), len(scope)) if scope else Fraction(0)
    rho = {d: f"{len(w)}/{len(estate)}" for d, w in reached.items()} if estate else {}
    narrow = sorted(d for d, w in reached.items() if estate and Fraction(len(w), len(estate)) < tau_rel)
    cur = inputs.get("current")
    support = {u: sorted({i for d in eligible for r in d["assessments"] if r["target"] == u and r["validator"] in validators
                          for i in r["record_ids"]}) for u in covered}
    m = {"coverage_numerator": len(covered), "coverage_denominator": len(scope), "threshold": f"{tau.numerator}/{tau.denominator}",
         "coverage_ok": c_acc >= tau, "corroboration_ok": not missing, "covered": covered,
         "uncovered": sorted(set(scope) - estate), "observed_estate": sorted(estate), "observed_estate_size": len(estate),
         "drift": sorted(estate - set(scope)), "eligible": [d["decision_id"] for d in eligible], "excluded": excluded,
         "relative_threshold": f"{tau_rel.numerator}/{tau_rel.denominator}", "rho": rho, "narrow": narrow,
         "current": {"decision": cur, "eligible": cur in reached, "rho": rho.get(cur), "narrow": cur in narrow},
         "missing_validator_targets": len(missing),
         "missing_by_validator": {v: sum(1 for x in missing.values() if v in x) for v in validators},
         "missing_first_10": [{"target": u, "validators": x} for u, x in list(missing.items())[:10]],
         "max_age_seconds": round(max(ages), 3) if ages else None, "support": support}
    reasons = []
    if not m["coverage_ok"]:
        reasons.append(f"composed coverage {len(covered)}/{len(scope)} below {m['threshold']}")
    if missing:
        reasons.append(f"{len(missing)} covered function(s) lack a required validator")
    if narrow:
        reasons.append(f"GREEN but narrow (below {m['relative_threshold']} of the observed estate): {', '.join(narrow)}")
    if m["coverage_ok"] and not missing and eligible:
        state = SUCCESS
    elif all(d.get("record_status") == "complete" for d in inputs["decisions"]):
        state = FAIL
    else:
        state = INCONCLUSIVE
        reasons.append("a decision record in the set is incomplete: a shortfall cannot be established")
    return {"state": state, "measurements": m, "reasons": reasons}
