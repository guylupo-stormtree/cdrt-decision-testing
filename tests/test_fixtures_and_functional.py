"""Fixture build (R-FIX-*), lock (R-LOCK-1/2), control isolation (R-ISO-1) and the functional protocol (A10)
on the development bundle. Development data: these check the machinery, not the experiment's result."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).parents[1]
QUIET = lambda m: None  # noqa: E731


@pytest.fixture()
def lab5(dev_bundle, cdrt_root):
    b, _ = dev_bundle
    cfg = yaml.safe_load((REPO / "protocol" / "run_config.yaml").read_text())
    cfg["scale"]["target_sizes"] = [100, 1000]            # small planes: the large ones are Lab 8's concern
    (cdrt_root / "protocol").mkdir()
    (cdrt_root / "protocol" / "run_config.yaml").write_text(yaml.safe_dump(cfg))
    res = b.run(5, progress=QUIET)
    assert res.passed, res.summary.get("_card")
    return b


def test_fixture_parameters_follow_the_declared_rules(lab5, cdrt_root):
    from fractions import Fraction
    p = json.loads((cdrt_root / "fixtures" / "out-dev" / "parameters.json").read_text())
    c = Fraction(p["c_obs"])
    assert Fraction(p["tau_q"]["numerator"], 20) <= c < Fraction(p["tau_q"]["numerator"] + 1, 20)
    assert p["captured"] == 5 and len(p["green"]) == 5 and p["selection"]["main"] in p["green"]
    assert [pl["basis_count"] for pl in p["planes"].values()] == p["actual_sizes"]
    assert all(n >= t for n, t in zip(p["actual_sizes"], p["scale_target_sizes"]))
    profiles = sorted(x.name for x in (cdrt_root / "fixtures" / "out-dev" / "profiles").iterdir())
    assert profiles == ["rev1.yaml", "rev2.yaml", "rev3.yaml"]
    assert not (cdrt_root / "fixtures" / "out-dev" / "derived").exists()


def test_control_guard_counts_and_restores():
    import pwexp.stages.stage1_acquire as stage1
    from cdrt.control_guard import disabled_control
    real = stage1.run
    with disabled_control() as g:
        with pytest.raises(RuntimeError, match="control isolation"):
            stage1.run()
        assert g.calls == ["run"]
    assert stage1.run is real


def test_lock_detects_a_changed_component(lab5, cdrt_root):
    from cdrt import lock
    for name in ("src", "uv.lock"):
        (cdrt_root / name).symlink_to(REPO / name)
    doc = lock.write(True, "dev-test")
    assert lock.verify(True)[0] and doc["lock_root"]
    f = cdrt_root / "fixtures" / "out-dev" / "parameters.json"
    f.write_text(f.read_text() + " ")
    ok, problems, _ = lock.verify(True)
    assert not ok and problems == ["fixtures changed since the lock"]


def test_functional_protocol_runs_completely_and_replays(lab5, cdrt_root, tmp_path):
    from cdrt.harness import functional
    h = lab5.handoff(5)["handoff"]
    stamp = {"lock_root": "L", "campaign_id": "dev-test", "git_commit": "G", "pwexp_commit": "P"}
    work = tmp_path / "work"
    work.mkdir()
    env = functional.load_env(cdrt_root / h["bundle"], cdrt_root / h["fixtures"], work, stamp, h["green"])
    out = functional.run_protocol(env, 2, QUIET)
    recs, acc = out["records"], out["acceptance"]["acceptance"]
    assert not out["missing"] and all(r["executed"] for r in recs)
    assert all(r["lock_root"] == "L" and "binding" in r for r in recs)
    assert out["digests"][0] == out["digests"][1]
    by = {r["id"]: r for r in recs}
    assert [by[s]["match"] for s in ("step1", "step2", "step3", "before", "after", "delayed")] == [True] * 6
    assert by["before"]["observed"] == {"H": "SUCCESS", "A": "SUCCESS", "gateway": "proceed"}
    assert by["after"]["observed"] == {"H": "SUCCESS", "A": "FAIL", "gateway": "hold"}
    assert all(acc[k]["passes"] for k in ("C1", "C2", "C3", "C4")), acc
    assert out["acceptance"]["A_comp"] and out["acceptance"]["replay_agrees"]
    assert by["isolation"]["observed"]["guard_calls"] == 0
    assert not by["delayed"]["observed"]["old_admitted"] and by["delayed"]["observed"]["posture_unchanged"]
    assert set(by["observation"]["observed"]) == set(h["green"]) and by["observation"]["match"]


def test_headline_is_the_slowest_update_against_the_budget():
    from cdrt.harness.scale import headline, sentence
    row = lambda n, slow, over=0, timeouts=0: {"N": n, "observations": 100, "slowest_s": slow, "exceedances": over,  # noqa: E731
                                               "timeouts": timeouts}
    ok = {"100": row(129, 0.03), "100000": row(100018, 3.38)}
    h = headline(ok, 5.0)
    assert h["worst_s"] == 3.38 and h["worst_N"] == 100018 and h["within"] and h["total"] == 200
    assert sentence(ok, 5.0) == "Every one of the 200 timed updates reached the gateway within the 5 s budget; the slowest took 3.38 s."
    late = {"100": row(129, 0.03), "100000": row(100018, 7.1, over=3)}
    assert not headline(late, 5.0)["within"] and sentence(late, 5.0).startswith("3 of 200 timed updates exceeded")
    lost = {"100": row(129, 0.03), "100000": row(100018, 4.0, over=1, timeouts=1)}
    assert headline(lost, 5.0)["worst_s"] is None and not headline(lost, 5.0)["within"]


def test_scale_cycles_keep_meaning_and_are_all_recorded(lab5, cdrt_root):
    from cdrt.harness import scale
    (cdrt_root / "uv.lock").symlink_to(REPO / "uv.lock")             # hashed into the run manifest
    h = lab5.handoff(5)["handoff"]
    cfg = yaml.safe_load((cdrt_root / "protocol" / "run_config.yaml").read_text())["scale"]
    res = scale.run(cdrt_root / h["fixtures"], cdrt_root / h["bundle"], cfg, {"lock_root": "L"}, QUIET, blocks=2, warmups=1)
    assert res["expected_cycles"] == len(res["records"]) == 4
    assert all(r["match"] and r["completed"] and r["lock_root"] == "L" for r in res["records"])
    assert all(r["shared_view"]["tests"] == ["conformance-check@1.0", "adequacy-check@1.0"] for r in res["records"])
    assert res["guard_calls"] == 0 and res["stats"]["100"]["observations"] == 2
    assert "real-time" not in res["sentence"]
