"""Resolver (R-RES-1) and the invocation binding B (Eq. 7, requirements A9).

One invocation per profile requirement (posture leaf), built from explicit declarations only: the resolver
looks up the exact test version, takes the declared parameters as they are, and binds the invocation to the
requirement revision, context, snapshot, manifest, decision binding, record contract, test, parameters,
assessment time, invocation contract and destination leaf. It cannot change versions, weaken thresholds or
add fields.

A requirement may name a decision set (parameter `decision_set`: "all-captured" or a list of decision ids),
for a test that composes evidence across decisions. Its h_H is then the hash of the set's sorted binding
record hashes, so the invocation stays bound to exactly the decisions it judged; Eq. 7 keeps its fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pwexp.hashing import sha256_json

from ..records.manifests import ManifestStore
from ..records.view import Snapshot, get_decision, list_decisions
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
    decision_ids: tuple[str, ...] = ()          # the declared decision set of a composing test

    @property
    def leaf(self) -> str:
        return self.binding["d"]


def _policy(d: dict[str, Any]) -> dict[str, Any] | None:
    return (d.get("policy") or {}).get("payload", {}).get("content") if d["status"] != "unavailable" else None


def decision_set(params: dict[str, Any], s: Snapshot) -> tuple[str, ...]:
    ds = params.get("decision_set")
    if ds == "all-captured":
        return tuple(list_decisions(s))
    return tuple(ds or ())


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
            pol = _policy(dec) or {}
            _, h_M = manifests.resolve(pol.get("manifest"))
        else:
            _, h_M = manifests.resolve(params.get("manifest_ref"))
        ids = decision_set(params, s)
        h = h_H
        if ids:
            hashes = [(get_decision(s, d).get("binding") or {}).get("record_hash") for d in ids]
            h = sha256_json(sorted(x or "" for x in hashes))
        mu, _, v_mu = req["test"].partition("@")
        b = {"q": req["id"], "v_q": req["revision"], "kappa": profile.get("context_ref"), "s": s.id, "h_M": h_M,
             "h_H": h, "v_E": RECORD_CONTRACT, "mu": mu, "v_mu": v_mu, "h_mu": entry.code_digest if entry else None,
             "theta": sha256_json(params), "t_e": params.get("assessment_time"), "v_c": INVOCATION_CONTRACT,
             "d": req["posture_leaf"]}
        out.append(Invocation(b, req["test"], entry, params, decision_id, err, ids))
    return out
