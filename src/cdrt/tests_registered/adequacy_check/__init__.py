"""adequacy-check@1.0 (R-TST-2): is the decision, on its recorded basis, enough for requirement q now?

SUCCESS iff c(Sigma_r, M_q) >= tau_q, J(Sigma_r, M_q, V_q) and a(Sigma_r, t_e) <= Delta_q (Eq. 6).
Age a = t_e minus the oldest observation time among the records supporting covered targets. Missing or
malformed times, or a time after t_e, leave age unresolved (INCONCLUSIVE). A valid empty basis has known
zero coverage. A definite failure of any condition gives FAIL; otherwise any unresolved one INCONCLUSIVE.
"""
from __future__ import annotations

from typing import Any

from ..common import FAIL, INCONCLUSIVE, SUCCESS, frac, licence, parse_utc

ID, VERSION = "adequacy-check", "1.0"


def evaluate(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    scope = inputs.get("manifest")
    if scope is None:
        return {"state": INCONCLUSIVE, "measurements": {}, "reasons": ["requirement manifest unresolvable"]}
    validators = list(params["validators"])
    m = licence(inputs["assessments"], scope, frac(params["minimum_coverage"]), validators)
    te = parse_utc(params.get("assessment_time"))
    covered = set(m.pop("covered"))
    times = [r.get("time") for r in inputs["assessments"]
             if r["target"] in covered and r["validator"] in validators]
    parsed = [parse_utc(t) for t in times]
    reasons = []
    if te is None or any(t is None for t in parsed) or any(t > te for t in parsed):
        age_ok, m["max_age_seconds"] = None, None
        reasons.append("age unresolved: missing, malformed or future observation time, or no assessment time")
    else:
        age = max(((te - t).total_seconds() for t in parsed), default=0.0)
        m["max_age_seconds"] = round(age, 3)
        age_ok = age <= float(params["max_age_seconds"])
        if not age_ok:
            reasons.append(f"oldest supporting record is {age:.0f} s old, above {params['max_age_seconds']} s")
    if not m["coverage_ok"]:
        reasons.append(f"coverage {m['coverage_numerator']}/{m['coverage_denominator']} below {m['threshold']}")
    if not m["corroboration_ok"]:
        reasons.append(f"{m['missing_validator_targets']} covered target(s) lack a required validator")
    shortfall = not m["coverage_ok"] or not m["corroboration_ok"]     # needs absence: only a complete basis shows it
    if age_ok is False:                                                # an old record is a known fact
        state = FAIL
    elif shortfall:
        state = FAIL if inputs.get("record_status") == "complete" else INCONCLUSIVE
        if state == INCONCLUSIVE:
            reasons.append("decision record incomplete: a shortfall cannot be established")
    elif age_ok is None:
        state = INCONCLUSIVE
    else:
        state = SUCCESS
    m["age_ok"] = age_ok
    return {"state": state, "measurements": m, "reasons": reasons}
