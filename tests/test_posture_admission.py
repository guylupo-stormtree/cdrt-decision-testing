"""Admission (Eq. 8), withdrawal on activation, history, aggregation (R-POS-1 … R-POS-4; B5-B10)."""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from cdrt.posture import Consumer, aggregate
from cdrt.resolver import B_FIELDS


def B(q="decision-adequacy", d="release.adequacy", v_q=2, **kw):
    b = {k: f"{k}-value" for k in B_FIELDS}
    b.update(q=q, d=d, v_q=v_q, **kw)
    return b


def V(b, state="SUCCESS", valid_until=None, status="ok"):
    return {"binding": b, "state": state, "execution_status": status, "measurements": {}, "reasons": [],
            "valid_until": valid_until}


def consumer(rev=2):
    c = Consumer()
    h = B(q="decision-conformance", d="release.effectiveness", v_q=1)
    c.activate({"profile": "p", "revision": rev}, {"release.effectiveness": h, "release.adequacy": B(v_q=rev)})
    return c, h


@given(st.sampled_from(B_FIELDS), st.text(min_size=1, max_size=5))
def test_any_binding_field_mutation_is_rejected(field, junk):
    c, _ = consumer()
    good = B()
    bad = dict(good, **{field: f"{good[field]}~{junk}"})
    ok, why = c.admit(V(bad), "2026-10-13T12:00:00Z")
    assert not ok and c.leaves["release.adequacy"]["state"] is None and c.history[-1]["reason"].startswith("rejected")
    assert c.admit(V(good), "2026-10-13T12:00:00Z")[0]


def test_activation_withdraws_only_affected_leaves_and_late_verdicts_are_history():
    c, h = consumer(rev=2)
    old = B(v_q=2)
    assert c.admit(V(h), "t")[0] and c.admit(V(old), "t")[0]
    assert c.card()["aggregate"] == "SUCCESS"
    c.activate({"profile": "p", "revision": 3}, {"release.effectiveness": h, "release.adequacy": B(v_q=3)})
    card = c.card()
    assert card["leaves"]["release.effectiveness"]["state"] == "SUCCESS"            # H kept
    assert card["leaves"]["release.adequacy"]["state"] is None                       # A withdrawn before any new verdict
    assert card["aggregate"] == "INCONCLUSIVE" and not card["complete"]
    assert not c.admit(V(old), "t")[0]                                              # I2: late rev-2 verdict rejected
    assert c.admit(V(B(v_q=3), "FAIL"), "t")[0]
    assert not c.admit(V(old), "t")[0]                                              # I1: after the new one, still rejected
    card = c.card()
    assert card["aggregate"] == "FAIL" and card["complete"]
    assert sum(1 for x in card["history"] if x["reason"].startswith("rejected")) == 2


def test_misrouted_invalid_and_expired():
    c, _ = consumer()
    assert not c.admit(V(B(d="release.other")), "t")[0]                              # B5
    assert not c.admit(V(B(), state=None, status="crash"), "t")[0]
    assert not c.admit(V(B(), valid_until="2026-10-13T11:00:00Z"), "2026-10-13T12:00:00Z")[0]
    assert c.admit(V(B(), valid_until="2026-10-13T13:00:00Z"), "2026-10-13T12:00:00Z")[0]


def test_all_mandatory_aggregation():
    L = lambda *s: {str(i): {"state": x} for i, x in enumerate(s)}  # noqa: E731
    assert aggregate(L("SUCCESS", "FAIL", None)) == "FAIL"
    assert aggregate(L("SUCCESS", "INCONCLUSIVE")) == "INCONCLUSIVE"
    assert aggregate(L("SUCCESS", None)) == "INCONCLUSIVE"
    assert aggregate(L("SUCCESS", "SUCCESS")) == "SUCCESS"
    assert aggregate({}) == "INCONCLUSIVE"


def test_monitor_reruns_only_affected_leaves(dev_bundle):
    from cdrt import api
    from cdrt.monitor import reassess
    from cdrt.records import view
    _, bundle = dev_bundle
    s = view.load_snapshot(bundle / "corpus", bundle / "target")
    store = api.manifest_store(bundle / "protocol")
    from pwexp.hashing import sha256_file
    mq = {"id": "M_q", "sha256": sha256_file(bundle / "protocol" / "manifests" / "M_q.json")}
    conf = {"id": "decision-conformance", "revision": 1, "test": "conformance-check@1.0",
            "posture_leaf": "release.effectiveness", "parameters": {"policy_source": "recorded-decision-policy"}}
    adq = lambda rev, vs: {"id": "decision-adequacy", "revision": rev, "test": "adequacy-check@1.0",  # noqa: E731
                           "posture_leaf": "release.adequacy", "parameters": {
                               "manifest_ref": mq, "minimum_coverage": {"numerator": 3, "denominator": 4},
                               "validators": vs, "max_age_seconds": 100000, "assessment_time": "2026-10-14T00:00:00Z"}}
    base = {"profile": "release", "context_ref": "c", "decision_ref": "G-main-01"}
    c, cards = Consumer(), []
    r1 = reassess(c, {**base, "revision": 1, "requirements": [conf]}, s, store, cards.append)
    r2 = reassess(c, {**base, "revision": 2, "requirements": [conf, adq(1, ["base-check"])]}, s, store, cards.append)
    assert r2["affected"] == ["release.adequacy"] and r2["card"]["aggregate"] == "SUCCESS"
    r3 = reassess(c, {**base, "revision": 3, "requirements": [conf, adq(2, ["base-check", "independent-check"])]},
                  s, store, cards.append)
    assert r1["card"]["aggregate"] == "SUCCESS"
    assert r3["affected"] == ["release.adequacy"]                                   # H not re-run
    assert cards[-2]["leaves"]["release.adequacy"]["state"] is None                 # published withdrawn first
    assert r3["card"]["leaves"]["release.effectiveness"]["state"] == "SUCCESS"
    assert r3["card"]["leaves"]["release.adequacy"]["state"] == "FAIL" and r3["card"]["aggregate"] == "FAIL"
