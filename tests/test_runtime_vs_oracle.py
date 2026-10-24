"""On the frozen development bundle, the runtime and the independent oracle agree on every judgement."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from cdrt import api
from cdrt.records import view
from pwexp.hashing import sha256_file


def oracle(*args):
    from pathlib import Path
    p = subprocess.run([sys.executable, str(Path(__file__).parents[1] / "oracle" / "oracle_check.py"), *map(str, args)],
                       capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


@pytest.mark.parametrize("validators,tau", [(["base-check"], (3, 4)), (["base-check", "independent-check"], (1, 2)),
                                            (["base-check"], (1, 1))])
def test_conformance_and_adequacy_agree(dev_bundle, tmp_path, validators, tau):
    _, bundle = dev_bundle
    s = view.load_snapshot(bundle / "corpus", bundle / "target")
    store = api.manifest_store(bundle / "protocol")
    mq = bundle / "protocol" / "manifests" / "M_q.json"
    params = {"manifest_ref": {"id": "M_q", "sha256": sha256_file(mq)},
              "minimum_coverage": {"numerator": tau[0], "denominator": tau[1]}, "validators": validators,
              "max_age_seconds": 100000, "assessment_time": "2026-10-14T00:00:00Z"}
    oparams = dict(params, manifest={"file": "manifests/M_q.json", "sha256": params["manifest_ref"]["sha256"]})
    (tmp_path / "p.json").write_text(json.dumps(oparams))
    for d in view.list_decisions(s):
        prof = {"profile": "p", "revision": 2, "context_ref": "c", "decision_ref": d, "requirements": [
            {"id": "decision-conformance", "revision": 1, "test": "conformance-check@1.0", "posture_leaf": "release.effectiveness",
             "parameters": {"policy_source": "recorded-decision-policy"}},
            {"id": "decision-adequacy", "revision": 2, "test": "adequacy-check@1.0", "posture_leaf": "release.adequacy",
             "parameters": params}]}
        invs = api.resolve(prof, s, store)
        h, a = (api.evaluate(i, s, store) for i in invs)
        oh, oa = oracle("conformance", bundle, d), oracle("adequacy", bundle, d, tmp_path / "p.json")
        assert h["state"] == oh["state"] and a["state"] == oa["state"], d
        assert f"{h['measurements']['coverage_numerator']}/{h['measurements']['coverage_denominator']}" == oh["coverage"]
        assert f"{a['measurements']['coverage_numerator']}/{a['measurements']['coverage_denominator']}" == oa["coverage"]
        if oa["max_age_seconds"] is None:
            assert a["measurements"]["max_age_seconds"] is None
        else:
            assert a["measurements"]["max_age_seconds"] == pytest.approx(oa["max_age_seconds"], abs=0.001)
        assert h["binding"]["h_H"] == view.get_decision(s, d)["binding"]["record_hash"]   # AC4: binding preserved
        card = api.posture(prof, invs, [h, a], "2026-10-14T00:00:00Z")
        assert card["complete"] and card["leaves"]["release.adequacy"]["state"] == a["state"]


def test_strict_decision_fails_conformance_although_green(dev_bundle):
    _, bundle = dev_bundle
    s = view.load_snapshot(bundle / "corpus", bundle / "target")
    store = api.manifest_store(bundle / "protocol")
    prof = {"profile": "p", "revision": 1, "context_ref": "c", "decision_ref": "G-strict-01", "requirements": [
        {"id": "decision-conformance", "revision": 1, "test": "conformance-check@1.0", "posture_leaf": "release.effectiveness",
         "parameters": {"policy_source": "recorded-decision-policy"}}]}
    v = api.evaluate(api.resolve(prof, s, store)[0], s, store)
    assert view.get_decision(s, "G-strict-01")["decision"]["payload"]["verdict"] == "green"
    assert v["state"] == "FAIL" and v["measurements"]["missing_by_validator"]["independent-check"] > 0
