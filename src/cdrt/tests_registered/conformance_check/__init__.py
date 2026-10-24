"""conformance-check@1.0 (R-TST-1): was the decision licensed by its own policy-at-event?

SUCCESS iff c(Sigma_r, M_h) >= tau_h and J(Sigma_r, M_h, V_h), with M_h, tau_h and V_h read from the policy
resolved through the decision's binding. INCONCLUSIVE when the policy cannot be resolved or its digest does
not match, when the decision record is not complete and a shortfall would need absence to be established,
or when the scope manifest cannot be resolved. The current profile's validators are never used instead.
"""
from __future__ import annotations

from typing import Any

from ..common import FAIL, INCONCLUSIVE, SUCCESS, frac, licence

ID, VERSION = "conformance-check", "1.0"


def evaluate(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    pol = inputs.get("policy")
    if not pol or not inputs.get("policy_digest_ok"):
        return {"state": INCONCLUSIVE, "measurements": {}, "reasons": ["policy-at-event unresolvable or digest mismatch"]}
    scope = inputs.get("policy_manifest")
    if scope is None:
        return {"state": INCONCLUSIVE, "measurements": {}, "reasons": ["policy scope manifest unresolvable"]}
    m = licence(inputs["assessments"], scope, frac(pol["threshold"]), list(pol["validators"]))
    holds = m["coverage_ok"] and m["corroboration_ok"]
    reasons = []
    if not m["coverage_ok"]:
        reasons.append(f"coverage {m['coverage_numerator']}/{m['coverage_denominator']} below {m['threshold']}")
    if not m["corroboration_ok"]:
        reasons.append(f"{m['missing_validator_targets']} covered target(s) lack a required validator")
    if holds:
        state = SUCCESS
    elif inputs.get("record_status") != "complete":
        state, reasons = INCONCLUSIVE, reasons + ["decision record incomplete: a shortfall cannot be established"]
    else:
        state = FAIL
    m.pop("covered")
    return {"state": state, "measurements": {**m, "policy": f"{pol['id']}@{pol['version']}"}, "reasons": reasons}
