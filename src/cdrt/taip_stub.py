"""TAIP posture stub (main-14 §3.4, §3.6; PROGRESS.md D-017).

A minimal stand-in for TAIP's composite posture aggregation, so that the experiment runs end to end: it is
not the TAIP engine. It receives the CDRT verdicts that admission has accepted for the active requirement
revision and builds a TAIP-shaped posture card over the release-assurance tree of main-14 Figure 4:

  release-assurance (root, all branches mandatory)
  ├── effectiveness    ← conformance-check verdict on leaf release.effectiveness
  ├── adequacy         ← adequacy-check verdict on leaf release.adequacy (when the profile requires it)
  └── sustainability   ← every admitted support still matches the active revision's binding and is unexpired

CDRT's SUCCESS / FAIL / INCONCLUSIVE map to TAIP's pass / fail / inconclusive. A branch with no admitted
verdict is inconclusive, never a pass or a zero. Root: any fail → fail; otherwise any inconclusive →
inconclusive; otherwise pass. Gateway policy (fail-closed release gate): pass → proceed, fail → hold,
inconclusive → no-green.
"""
from __future__ import annotations

from typing import Any

from pwexp.hashing import canonical_json

from .tests_registered.common import FAIL, INCONCLUSIVE, SUCCESS, parse_utc

PASS_, FAIL_, INCONCLUSIVE_ = "pass", "fail", "inconclusive"
BRANCHES = (("effectiveness", "release.effectiveness"), ("adequacy", "release.adequacy"))
GATEWAY = {PASS_: "proceed", FAIL_: "hold", INCONCLUSIVE_: "no-green"}
TO_CDRT = {PASS_: SUCCESS, FAIL_: FAIL, INCONCLUSIVE_: INCONCLUSIVE}


def leaf_state(cdrt_state: str | None) -> str:
    return {SUCCESS: PASS_, FAIL: FAIL_}.get(cdrt_state or "", INCONCLUSIVE_)


def sustainability(expected: dict[str, dict], support: dict[str, dict], t: str | None) -> tuple[str, str]:
    """pass: every required leaf has admitted support bound to the active revision and unexpired at t;
    inconclusive: some leaf has no admitted support yet; fail: some admitted support is stale or expired."""
    now = parse_utc(t) if t else None
    for leaf, b in sorted(expected.items()):
        v = support.get(leaf)
        if v is None:
            continue
        if canonical_json(v["binding"]) != canonical_json(b):
            return FAIL_, f"{leaf}: admitted support is bound to a superseded requirement"
        if v.get("valid_until") and now and parse_utc(v["valid_until"]) < now:
            return FAIL_, f"{leaf}: admitted support expired at {v['valid_until']}"
    pending = sorted(leaf for leaf in expected if leaf not in support)
    if pending:
        return INCONCLUSIVE_, "awaiting admitted support for " + ", ".join(pending)
    return PASS_, "all support bound to the active requirement revision and unexpired"


def posture(profile: dict[str, Any] | None, leaves: dict[str, dict], expected: dict[str, dict],
            support: dict[str, dict], t: str | None) -> dict[str, Any]:
    branches = {}
    for name, leaf in BRANCHES:
        if leaf in expected:
            branches[name] = {"leaf": leaf, "state": leaf_state((leaves.get(leaf) or {}).get("state"))}
    state, why = sustainability(expected, support, t)
    branches["sustainability"] = {"leaf": None, "state": state, "reason": why}
    states = [b["state"] for b in branches.values()]
    root = FAIL_ if FAIL_ in states else INCONCLUSIVE_ if INCONCLUSIVE_ in states or not expected else PASS_
    return {"stub": "cdrt.taip_stub (not the TAIP engine)", "claim": (profile or {}).get("claim"),
            "root": root, "branches": branches, "gateway_decision": GATEWAY[root]}
