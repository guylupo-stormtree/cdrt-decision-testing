"""Registry approval and digests (R-REG-1/2); executor failure modes (R-EXE-1)."""
from __future__ import annotations

import sys
from dataclasses import replace

import pytest

from cdrt.executor import execute
from cdrt.registry import Entry, LookupFailure, Registry

PROGRAMS = {
    "crash": "def evaluate(i, p):\n    raise RuntimeError('boom')\n",
    "slow": "import time\ndef evaluate(i, p):\n    time.sleep(30)\n",
    "malformed": "def evaluate(i, p):\n    return {'state': 'GREEN'}\n",
    "hungry": "def evaluate(i, p):\n    x = bytearray(2 * 1024 ** 3)\n    return {'state': 'SUCCESS', 'measurements': {}, 'reasons': []}\n",
    "peek": "def evaluate(i, p):\n    return {'state': 'SUCCESS', 'measurements': {'keys': sorted(i)}, 'reasons': []}\n",
}


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    for name, code in PROGRAMS.items():
        (tmp_path / f"cdrt_fake_{name}.py").write_text(code)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr("cdrt.executor.code_digest", lambda files: "d")
    return lambda name, **kw: Entry("t", "1", f"cdrt_fake_{name}", ("x",), "d", ("a",), limits=kw or {"wall_seconds": 5})


def test_registered_entries_are_approved_and_match():
    r = Registry()
    assert {e["ref"] for e in r.describe()} == {"conformance-check@1.0", "adequacy-check@1.0", "coverage-composition@1.0"} and not r.rejected
    with pytest.raises(LookupFailure):
        r.lookup("conformance-check@2.0")


def test_digest_mismatch_and_unapproved(tmp_path):
    import yaml
    from cdrt.registry import ENTRIES
    doc = yaml.safe_load(ENTRIES.read_text())
    doc["entries"][0]["code_digest"] = "0" * 64
    doc["entries"][1]["approved"] = False
    p = tmp_path / "e.yaml"
    p.write_text(yaml.safe_dump(doc))
    r = Registry(p)
    with pytest.raises(LookupFailure, match="digest"):
        r.lookup("conformance-check@1.0")
    with pytest.raises(LookupFailure, match="not approved"):
        r.lookup("adequacy-check@1.0")
    e = Registry().lookup("conformance-check@1.0")
    assert execute(replace(e, code_digest="1" * 64), {}, {})[0] == "digest-mismatch"   # re-checked per invocation


def test_execution_failures_never_give_a_state(fake):
    assert execute(fake("crash"), {}, {})[0] == "crash"
    assert execute(fake("slow", wall_seconds=0.5), {}, {})[0] == "timeout"
    assert execute(fake("malformed"), {}, {})[0] == "malformed"
    assert execute(fake("hungry", wall_seconds=10, memory_mb=512), {}, {})[0] == "crash"
    status, out = execute(fake("peek"), {"a": 1, "secret": 2}, {})
    assert status == "ok" and out["measurements"]["keys"] == ["a"]            # projection to declared inputs
