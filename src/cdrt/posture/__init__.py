"""Posture consumer: admission (Eq. 8) and support withdrawal (R-POS-1 … R-POS-3); aggregation by TAIP.

Admit(R, q, t) = ValidResult(R) ∧ [B_R = B_expected(q, t)] ∧ Unexpired(R, t). The expected bindings are those
of the active profile revision; the check and the update happen under one lock, against the same revision.
Activating a revision first withdraws the support of every leaf whose expected binding changed, before any
new verdict can be admitted; unaffected leaves keep theirs. A verdict that does not match goes to history
and never becomes current support. The admitted verdicts are then aggregated by the TAIP posture stub
(cdrt.taip_stub, main-14 §3.6): the card carries TAIP's branches, root and gateway decision, and `aggregate`
is TAIP's root in CDRT's vocabulary. Leaf states and reasons stay visible on the card.
"""
from __future__ import annotations

import threading
from typing import Any

from pwexp.hashing import canonical_json, sha256_json

from .. import taip_stub
from ..tests_registered.common import FAIL, INCONCLUSIVE, SUCCESS, parse_utc


def verdict_ref(v: dict[str, Any]) -> str:
    return sha256_json(v)


class Consumer:
    def __init__(self):
        self._lock = threading.Lock()
        self.profile: dict[str, Any] | None = None
        self.expected: dict[str, dict[str, Any]] = {}
        self.leaves: dict[str, dict[str, Any]] = {}
        self.support: dict[str, dict[str, Any]] = {}     # leaf -> the admitted verdict giving current support
        self.history: list[dict[str, Any]] = []
        self.log: list[dict[str, Any]] = []

    def activate(self, profile: dict[str, Any], expected: dict[str, dict[str, Any]]) -> list[str]:
        """Make `profile` the active revision with expected bindings {leaf: B}. Returns the affected leaves."""
        with self._lock:
            affected = sorted(d for d, b in expected.items() if canonical_json(self.expected.get(d)) != canonical_json(b))
            for d in affected:
                old = self.leaves.get(d)
                if old and old.get("verdict_ref"):
                    self.history.append({"verdict_ref": old["verdict_ref"], "leaf": d, "reason": "support withdrawn: "
                                         f"requirement revision {profile['revision']} activated"})
                self.leaves[d] = {"state": None, "verdict_ref": None,
                                  "reason": f"awaiting a verdict for profile revision {profile['revision']}"}
                self.support.pop(d, None)
            for d in [x for x in self.leaves if x not in expected]:
                self.leaves.pop(d)
                self.support.pop(d, None)
            self.profile, self.expected = profile, dict(expected)
            self.log.append({"event": "activate", "revision": profile["revision"], "affected": affected})
            return affected

    def admit(self, verdict: dict[str, Any], t: str) -> tuple[bool, str]:
        with self._lock:
            b, d = verdict.get("binding") or {}, (verdict.get("binding") or {}).get("d")
            ref = verdict_ref(verdict)
            why = ""
            if verdict.get("execution_status") != "ok" or verdict.get("state") not in (SUCCESS, FAIL, INCONCLUSIVE):
                why = "not a valid result"
            elif d not in self.expected:
                why = f"destination {d!r} is not a leaf of the active revision"
            elif canonical_json(b) != canonical_json(self.expected[d]):
                diff = sorted(k for k in set(b) | set(self.expected[d]) if b.get(k) != self.expected[d].get(k))
                why = "binding differs from the expected one in " + ", ".join(diff)
            elif verdict.get("valid_until") and parse_utc(t) and parse_utc(verdict["valid_until"]) < parse_utc(t):
                why = "expired"
            if why:
                self.history.append({"verdict_ref": ref, "leaf": d, "state": verdict.get("state"), "reason": "rejected: " + why})
                self.log.append({"event": "reject", "leaf": d, "verdict_ref": ref, "reason": why})
                return False, why
            old = self.leaves.get(d) or {}
            if old.get("verdict_ref"):
                self.history.append({"verdict_ref": old["verdict_ref"], "leaf": d, "reason": "superseded"})
            self.leaves[d] = {"state": verdict["state"], "verdict_ref": ref, "reason": "; ".join(verdict.get("reasons") or [])}
            self.support[d] = verdict
            self.log.append({"event": "admit", "leaf": d, "verdict_ref": ref, "state": verdict["state"]})
            return True, ""

    def card(self, assessment_time: str | None = None) -> dict[str, Any]:
        with self._lock:
            leaves = {d: dict(v) for d, v in sorted(self.leaves.items())}
            taip = taip_stub.posture(self.profile, leaves, self.expected, self.support, assessment_time)
            return {"profile_id": (self.profile or {}).get("profile"), "profile_revision": (self.profile or {}).get("revision"),
                    "assessment_time": assessment_time, "leaves": leaves, "aggregate": taip_stub.TO_CDRT[taip["root"]],
                    "taip": taip, "gateway_decision": taip["gateway_decision"],
                    "unresolved": sorted(d for d, l in leaves.items() if l["state"] not in (SUCCESS, FAIL)),
                    "complete": all(l["verdict_ref"] for l in leaves.values()), "history": list(self.history)}
