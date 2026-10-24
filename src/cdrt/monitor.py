"""Posture monitoring with explicit triggers (manuscript Sec. 3.4): a requirement change is the trigger.

reassess(): resolve the newly active profile; activate it in the consumer (affected leaves lose support
first) and publish that card; evaluate only the affected leaves; admit each verdict; publish the new card.
Unaffected leaves keep their verdicts and are not re-run (unless `rerun_unaffected`: the scale protocol
times both tests, R-SCL-2). The decision and its basis are retrieved once per cycle and that one immutable
view is shared by the cycle's tests; the result logs the sharing (R-TST-5).
"""
from __future__ import annotations

from typing import Any, Callable

from .evaluation import evaluate
from .posture import Consumer
from .records import view


def reassess(consumer: Consumer, profile: dict[str, Any], s: view.Snapshot, manifests,
             publish: Callable[[dict[str, Any]], None] | None = None,
             hold: Callable[[dict[str, Any]], bool] | None = None, registry=None,
             rerun_unaffected: bool = False) -> dict[str, Any]:
    """`hold(verdict)` may keep a verdict back (delayed-result interleavings); it is then returned, not admitted.
    `registry` is the set of registered tests (default: every approved entry)."""
    from .registry import Registry
    from .resolver import resolve
    t = next((r["parameters"].get("assessment_time") for r in profile["requirements"]
              if (r.get("parameters") or {}).get("assessment_time")), None)
    invs = resolve(profile, s, registry or Registry(), manifests)
    affected = consumer.activate(profile, {i.leaf: i.binding for i in invs})
    if publish:
        publish(consumer.card(t))
    run = [i for i in invs if rerun_unaffected or i.leaf in affected]
    dv = view.retrieve(s, profile["decision_ref"]) if run else None
    held, verdicts = [], []
    for inv in run:
        v = evaluate(inv, s, manifests, dv)
        verdicts.append(v)
        if hold and hold(v):
            held.append(v)
            continue
        consumer.admit(v, t or "")
    card = consumer.card(t)
    if publish:
        publish(card)
    return {"affected": affected, "verdicts": verdicts, "held": held, "card": card,
            "shared_view": {"decision": profile["decision_ref"], "tests": [i.test for i in run]} if dv else None}
