"""Lab gating and hand-off integrity; record view integrity findings (R-REC-1, R-REC-4, R-REC-6)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cdrt.labs import book
from cdrt.labs.framework import LabError
from cdrt.records import view

QUIET = lambda m: None  # noqa: E731


@pytest.fixture()
def lab3(cdrt_root):
    b = book(dev=True)
    res = b.run(3, progress=QUIET)
    assert res.passed, res.summary.get("_card")
    return b


def test_gating_and_dev_start(cdrt_root):
    b = book(dev=True)
    assert b.status(0) == "not in dev mode" and b.status(3) == "ready" and b.status(4) == "locked"
    with pytest.raises(LabError):
        b.run(4, progress=QUIET)
    with pytest.raises(LabError):
        b.run(1, progress=QUIET)
    assert book(dev=False).status(0) == "ready"
    with pytest.raises(LabError, match="not built yet"):
        book(dev=False).run(0, progress=QUIET)


def test_lab3_hands_a_verified_corpus_to_lab4(lab3, cdrt_root):
    h = lab3.handoff(3)["handoff"]
    assert set(h["decisions"]) == {"G-main-01", "G-main-02", "G-main-03", "G-pipe-01", "G-strict-01"}
    assert lab3.verify_handoff(3)[0]
    res = lab3.run(4, progress=QUIET)
    assert not res.passed                                          # selection needs the oracle (B3)
    assert [c.ok for c in res.checks] == [True, True, True, None]
    assert (cdrt_root / "capture" / "bundle-dev" / "BUNDLE.json").exists()
    assert lab3.status(4) == "failed" and lab3.status(5) == "locked"


def test_changed_output_blocks_the_next_lab(lab3, cdrt_root):
    corpus = cdrt_root / lab3.handoff(3)["outputs"]["corpus"]["path"]
    (corpus / "graph.dot").write_text("tampered")
    ok, why = lab3.verify_handoff(3)
    assert not ok and "changed" in why
    with pytest.raises(LabError):
        lab3.run(4, progress=QUIET)


def test_rerun_invalidates_later_labs_and_keeps_history(lab3):
    lab3.run(4, progress=QUIET)
    lab3.run(3, progress=QUIET)
    assert "4" not in lab3.state() and lab3.status(4) == "ready"   # old Lab 4 result dropped; must run again
    events = [r["event"] for r in lab3.log.records()]
    assert events == ["lab_passed", "lab_failed", "lab_passed"] and not lab3.log.verify()


def test_record_view_integrity_findings(lab3, cdrt_root, tmp_path):
    h = lab3.handoff(3)["handoff"]
    corpus, target = cdrt_root / h["corpus"], cdrt_root / h["target"]
    s = view.load_snapshot(corpus, target, h["corpus_sha256"])
    d = view.get_decision(s, "G-main-01")
    basis = s.query.basis("G-main-01")["records"]
    assert view.check_binding(s, d, basis)
    assert not view.check_binding(s, d, basis[:-1])                # a record left out: root no longer matches
    with pytest.raises(view.IntegrityFinding, match="corpus hash"):
        view.load_snapshot(corpus, target, "0" * 64)
    copy = tmp_path / "copy"
    shutil.copytree(corpus, copy)
    lines = (copy / "ledger.jsonl").read_text().splitlines()
    rec = json.loads(lines[3])
    rec["payload"]["altered"] = True                               # one changed basis record (boundary check B2)
    lines[3] = json.dumps(rec, sort_keys=True)
    (copy / "ledger.jsonl").write_text("\n".join(lines) + "\n")
    with pytest.raises(view.IntegrityFinding, match="ledger"):
        view.load_snapshot(copy, target)
