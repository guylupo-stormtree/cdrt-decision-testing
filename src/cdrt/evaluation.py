"""Pure evaluation of one invocation over one record view: inputs → approved test → verdict. No admission."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from pwexp.hashing import sha256_bytes

from .executor import execute
from .records.assessments import assessments
from .records.manifests import ManifestStore
from .records.view import Snapshot, check_binding, get_decision
from .resolver import Invocation
from .tests_registered.common import parse_utc


def inputs_for(inv: Invocation, s: Snapshot, manifests: ManifestStore) -> dict[str, Any]:
    """Everything a registered test may declare as input, read through ProofWeave's Query API."""
    d = get_decision(s, inv.decision_id)
    out: dict[str, Any] = {"record_status": d["status"], "policy": None, "policy_digest_ok": False,
                           "policy_manifest": None, "manifest": None, "assessments": []}
    if d["status"] == "unavailable":
        return out
    basis = s.query.basis(inv.decision_id)["records"]
    if not check_binding(s, d, basis):                    # R-REC-4, inside the timed path
        out["record_status"] = "partial"
    pol = d.get("policy")
    text = s.query.policy_text(pol["id"]) if pol else "unavailable"
    if pol and isinstance(text, bytes):
        digest = d["binding"]["payload"]["policy_digest"]
        out["policy_digest_ok"] = sha256_bytes(text) == digest == pol["payload"].get("sha256")
        out["policy"] = json.loads(text)
        out["policy_manifest"] = manifests.resolve(out["policy"].get("manifest"))[0]
    out["manifest"] = manifests.resolve(inv.params.get("manifest_ref"))[0]
    out["assessments"] = assessments(s, inv.decision_id)["records"]
    return out


def evaluate(inv: Invocation, s: Snapshot, manifests: ManifestStore) -> dict[str, Any]:
    base = {"binding": inv.binding, "test": inv.test, "allow_synthetic": s.allow_synthetic, "valid_until": None}
    if inv.entry is None:
        return {**base, "execution_status": "lookup-failed", "state": None, "measurements": {},
                "reasons": [inv.lookup_error or "test not registered"]}
    status, out = execute(inv.entry, inputs_for(inv, s, manifests), inv.params)
    if status != "ok":
        return {**base, "execution_status": status, "state": None, "measurements": {},
                "reasons": [f"execution {status}"] + ([out["error"]] if out and "error" in out else [])}
    valid_until = None
    te, age = parse_utc(inv.params.get("assessment_time")), out["measurements"].get("max_age_seconds")
    if te is not None and age is not None and "max_age_seconds" in inv.params:
        valid_until = (te + timedelta(seconds=float(inv.params["max_age_seconds"]) - float(age))).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ")
    return {**base, "execution_status": "ok", "state": out["state"], "measurements": out["measurements"],
            "reasons": out["reasons"], "valid_until": valid_until}
