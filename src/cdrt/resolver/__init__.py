"""Resolver (R-RES-1) and the invocation binding B (Eq. 7, requirements A9).

One invocation per profile requirement (posture leaf), built from explicit declarations only: the resolver
looks up the exact test version, takes the declared parameters as they are, and binds the invocation to the
requirement revision, context, snapshot, manifest, decision binding, record contract, test, parameters,
assessment time, invocation contract and destination leaf. It cannot change versions, weaken thresholds or
add fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pwexp.hashing import sha256_json

from ..records.manifests import ManifestStore
from ..records.view import Snapshot, get_decision
from ..registry import Entry, LookupFailure, Registry

RECORD_CONTRACT = "pw-v0.2.0"
INVOCATION_CONTRACT = "cdrt-invocation/1"
B_FIELDS = ("q", "v_q", "kappa", "s", "h_M", "h_H", "v_E", "mu", "v_mu", "h_mu", "theta", "t_e", "v_c", "d")


@dataclass(frozen=True)
class Invocation:
    binding: dict[str, Any]
    test: str
    entry: Entry | None
    params: dict[str, Any]
    decision_id: str
    lookup_error: str | None = None

    @property
    def leaf(self) -> str:
        return self.binding["d"]


def _policy(s: Snapshot, decision_id: str) -> dict[str, Any] | None:
    d = get_decision(s, decision_id)
    return (d.get("policy") or {}).get("payload", {}).get("content") if d["status"] != "unavailable" else None


def resolve(profile: dict[str, Any], s: Snapshot, registry: Registry, manifests: ManifestStore) -> list[Invocation]:
    decision_id = profile["decision_ref"]
    dec = get_decision(s, decision_id)
    h_H = dec["binding"]["record_hash"] if dec.get("binding") else None
    out = []
    for req in profile["requirements"]:
        params = dict(req.get("parameters") or {})
        try:
            entry, err = registry.lookup(req["test"]), None
        except LookupFailure as e:
            entry, err = None, str(e)
        if req["test"].startswith("conformance-check@"):
            pol = _policy(s, decision_id) or {}
            _, h_M = manifests.resolve(pol.get("manifest"))
        else:
            _, h_M = manifests.resolve(params.get("manifest_ref"))
        mu, _, v_mu = req["test"].partition("@")
        b = {"q": req["id"], "v_q": req["revision"], "kappa": profile.get("context_ref"), "s": s.id, "h_M": h_M,
             "h_H": h_H, "v_E": RECORD_CONTRACT, "mu": mu, "v_mu": v_mu, "h_mu": entry.code_digest if entry else None,
             "theta": sha256_json(params), "t_e": params.get("assessment_time"), "v_c": INVOCATION_CONTRACT,
             "d": req["posture_leaf"]}
        out.append(Invocation(b, req["test"], entry, params, decision_id, err))
    return out
