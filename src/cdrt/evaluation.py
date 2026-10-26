"""Pure evaluation of one invocation over one record view: inputs → approved test → verdict. No admission."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from pwexp.hashing import sha256_bytes

from .executor import execute
from .records.assessments import assessments
from .records.manifests import ManifestStore
from .records.view import DecisionView, Snapshot, retrieve
from .resolver import Invocation
from .tests_registered.common import parse_utc


def inputs_for(inv: Invocation, s: Snapshot, manifests: ManifestStore, dv: DecisionView | None = None) -> dict[str, Any]:
    """Everything a registered test may declare as input, read through ProofWeave's Query API. `dv` is the
    cycle's shared retrieval of the decision (R-TST-5); without it the decision is retrieved here."""
    dv = dv if dv is not None and dv.decision_id == inv.decision_id else retrieve(s, inv.decision_id)
    d = dv.decision
    out: dict[str, Any] = {"record_status": d["status"], "policy": None, "policy_digest_ok": False,
                           "policy_manifest": None, "manifest": None, "assessments": []}
    if d["status"] == "unavailable":
        return out
    if not dv.binding_ok:                                 # R-REC-4, inside the timed path (retrieve)
        out["record_status"] = "partial"
    pol = d.get("policy")
    text = s.query.policy_text(pol["id"]) if pol else "unavailable"
    if pol and isinstance(text, bytes):
        digest = d["binding"]["payload"]["policy_digest"]
        out["policy_digest_ok"] = sha256_bytes(text) == digest == pol["payload"].get("sha256")
        out["policy"] = json.loads(text)
        out["policy_manifest"] = manifests.resolve(out["policy"].get("manifest"))[0]
    out["manifest"] = manifests.resolve(inv.params.get("manifest_ref"))[0]
    out["assessments"] = assessments(s, inv.decision_id, dv)["records"]
    return out


def decision_inputs(s: Snapshot, did: str, manifests: ManifestStore, dv: DecisionView | None = None) -> dict[str, Any]:
    """One decision as a composing test sees it: its conformance inputs plus verdict, intent and origin."""
    dv = dv if dv is not None and dv.decision_id == did else retrieve(s, did)
    probe = Invocation({}, "", None, {}, did)
    out = inputs_for(probe, s, manifests, dv)
    payload = ((dv.decision.get("decision") or {}).get("payload") or {})
    intent = ((dv.decision.get("intent") or {}).get("payload") or {})
    return {**out, "decision_id": did, "verdict": payload.get("verdict"), "synthetic": bool((dv.decision.get("binding") or {}).get("synthetic")),
            "intent": {k: intent.get(k) for k in ("repo", "commit", "bug_type")}}


def composition_inputs(inv: Invocation, s: Snapshot, manifests: ManifestStore, dv: DecisionView | None = None) -> dict[str, Any]:
    return {"decisions": [decision_inputs(s, d, manifests, dv) for d in inv.decision_ids],
            "manifest": manifests.resolve(inv.params.get("manifest_ref"))[0], "current": inv.decision_id}


def evaluate(inv: Invocation, s: Snapshot, manifests: ManifestStore, dv: DecisionView | None = None) -> dict[str, Any]:
    # the fixed output contract (main-14 Table 2): state, execution status, requirement and revision,
    # measurements, evidence references, reasons, validity limit; the binding B travels with it
    base = {"binding": inv.binding, "test": inv.test, "requirement": {"id": inv.binding["q"], "revision": inv.binding["v_q"]},
            "allow_synthetic": s.allow_synthetic, "valid_until": None, "evidence_refs": []}
    if inv.entry is None:
        return {**base, "execution_status": "lookup-failed", "state": None, "measurements": {},
                "reasons": [inv.lookup_error or "test not registered"]}
    inputs = composition_inputs(inv, s, manifests, dv) if inv.decision_ids else inputs_for(inv, s, manifests, dv)
    status, out = execute(inv.entry, {**inputs, "allow_synthetic": s.allow_synthetic},
                          {**inv.params, "allow_synthetic": s.allow_synthetic})
    if status != "ok":
        return {**base, "execution_status": status, "state": None, "measurements": {},
                "reasons": [f"execution {status}"] + ([out["error"]] if out and "error" in out else [])}
    valid_until = None
    te, age = parse_utc(inv.params.get("assessment_time")), out["measurements"].get("max_age_seconds")
    if te is not None and age is not None and "max_age_seconds" in inv.params:
        valid_until = (te + timedelta(seconds=float(inv.params["max_age_seconds"]) - float(age))).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ")
    refs = sorted({i for ids in (out["measurements"].get("support") or {}).values() for i in ids})
    return {**base, "execution_status": "ok", "state": out["state"], "measurements": out["measurements"],
            "reasons": out["reasons"], "valid_until": valid_until, "evidence_refs": refs}
