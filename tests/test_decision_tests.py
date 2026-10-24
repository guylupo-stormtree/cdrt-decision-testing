"""Property tests for the registered decision tests (Eqs. 3-6, R-TST-3, R-TST-6)."""
from __future__ import annotations

from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from cdrt.tests_registered import adequacy_check, conformance_check
from cdrt.tests_registered.common import licence

TARGETS = [f"m.py::f{i}" for i in range(8)]
TE = "2026-10-13T12:00:00.000000Z"


def rec(u, v="base-check", t="2026-10-13T11:00:00.000000Z", rid="r"):
    return {"target": u, "validator": v, "record_ids": [rid], "time": t}


records = st.lists(st.tuples(st.sampled_from(TARGETS + ["other.py::g"]), st.sampled_from(["base-check", "independent-check"])),
                   max_size=30)
scopes = st.lists(st.sampled_from(TARGETS), min_size=1, max_size=8, unique=True)
taus = st.tuples(st.integers(0, 20), st.just(20)).map(lambda x: {"numerator": x[0], "denominator": x[1]})


@settings(max_examples=200)
@given(records, scopes, taus, st.booleans())
def test_coverage_and_corroboration(rs, scope, tau, need_independent):
    recs = [rec(u, v) for u, v in rs]
    validators = ["base-check"] + (["independent-check"] if need_independent else [])
    m = licence(recs, scope, Fraction(tau["numerator"], tau["denominator"]), validators)
    base = {u for u, v in rs if v == "base-check"}
    covered = set(scope) & base
    assert m["coverage_numerator"] == len(covered) and m["coverage_denominator"] == len(scope)
    assert m["coverage_ok"] == (Fraction(len(covered), len(scope)) >= Fraction(tau["numerator"], 20))
    ind = {u for u, v in rs if v == "independent-check"}
    assert m["corroboration_ok"] == (not need_independent or covered <= ind)
    # duplicates never raise the numerator
    assert licence(recs + recs, scope, Fraction(0), validators)["coverage_numerator"] == len(covered)
    pol = {"id": "P", "version": 1, "threshold": tau, "validators": validators}
    out = conformance_check.evaluate({"policy": pol, "policy_digest_ok": True, "policy_manifest": scope,
                                      "assessments": recs, "record_status": "complete"}, {})
    assert out["state"] == ("SUCCESS" if m["coverage_ok"] and m["corroboration_ok"] else "FAIL")
    partial = conformance_check.evaluate({"policy": pol, "policy_digest_ok": True, "policy_manifest": scope,
                                          "assessments": recs, "record_status": "partial"}, {})
    assert partial["state"] == ("SUCCESS" if out["state"] == "SUCCESS" else "INCONCLUSIVE")   # absence needs completeness


def test_conformance_never_substitutes_a_policy():
    out = conformance_check.evaluate({"policy": None, "policy_digest_ok": False, "policy_manifest": TARGETS,
                                      "assessments": [rec(u) for u in TARGETS], "record_status": "complete"}, {})
    assert out["state"] == "INCONCLUSIVE"


def _adq(recs, max_age=7200, te=TE, status="complete", validators=("base-check",)):
    params = {"minimum_coverage": {"numerator": 1, "denominator": 2}, "validators": list(validators),
              "max_age_seconds": max_age, "assessment_time": te}
    return adequacy_check.evaluate({"manifest": TARGETS[:4], "assessments": recs, "record_status": status}, params)


@settings(max_examples=200)
@given(st.lists(st.integers(0, 20000), min_size=2, max_size=4), st.integers(0, 20000))
def test_age_condition(ages, max_age):
    from datetime import datetime, timedelta, timezone
    te = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    recs = [rec(TARGETS[i], t=(te - timedelta(seconds=a)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")) for i, a in enumerate(ages)]
    out = _adq(recs, max_age=max_age)
    assert out["state"] == ("SUCCESS" if max(ages) <= max_age else "FAIL")
    assert out["measurements"]["max_age_seconds"] == max(ages)


def test_age_unresolved_and_empty_basis():
    good = [rec(TARGETS[0]), rec(TARGETS[1])]
    assert _adq(good)["state"] == "SUCCESS"
    assert _adq(good + [rec(TARGETS[2], t=None)])["state"] == "INCONCLUSIVE"                    # missing time
    assert _adq(good + [rec(TARGETS[2], t="2026-10-13 11:00:00,000")])["state"] == "INCONCLUSIVE"  # no zone
    assert _adq(good + [rec(TARGETS[2], t="2026-10-14T00:00:00Z")])["state"] == "INCONCLUSIVE"    # future (B4)
    assert _adq(good, te="2026-10-13T10:00:00Z")["state"] == "INCONCLUSIVE"                       # t_e before records (B4)
    empty = _adq([])
    assert empty["state"] == "FAIL" and empty["measurements"]["coverage_numerator"] == 0           # known zero coverage
    assert _adq([], status="partial")["state"] == "INCONCLUSIVE"
    assert _adq(good, validators=("base-check", "independent-check"))["state"] == "FAIL"           # rev-3 shortfall
    m = _adq(good, validators=("base-check", "independent-check"))["measurements"]
    assert m["missing_by_validator"]["independent-check"] == 2 and len(m["missing_first_10"]) == 2
