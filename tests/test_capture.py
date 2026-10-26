"""Capture support for Labs 0-2: declaration checks, manifest drafting, approval, protocol, pilot rule, keys."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

from cdrt import capture

REPO = Path(__file__).parents[1]
FIXTURE = REPO / "vendor" / "proofweave-decision-assurance" / "targets" / "fixture-guarded-users"
SHA = "0" * 40


def decl(**over):
    d = yaml.safe_load((REPO / "capture" / "capture.yaml").read_text())
    d["target"].update(repository="https://example.org/r.git", commit=SHA)
    d["model"].update(provider="openai", model="gpt-x")
    d["runs"]["campaign"] = 12
    for k, v in over.items():
        d[k] = v
    return d


def test_declaration_template_is_incomplete_and_a_filled_one_is_valid():
    tpl = yaml.safe_load((REPO / "capture" / "capture.yaml").read_text())
    assert capture.problems(tpl) == []                          # the committed declaration is complete
    tpl["target"].update(repository="TODO", commit="TODO")
    tpl["model"].update(provider="TODO", model="TODO")
    tpl["runs"]["campaign"] = "TODO"
    bad = " ".join(capture.problems(tpl))
    assert "target.repository" in bad and "model.provider" in bad and "runs.campaign" in bad
    assert capture.problems(decl()) == []
    assert any("SHA" in p for p in capture.problems(decl(target={"repository": "u", "commit": "abc"})))
    assert any("NPD" in p for p in capture.problems(decl(bug_type="UAF")))


def test_manifest_draft_follows_the_none_rule():
    d = capture.draft_manifests(FIXTURE, [])
    fn = lambda xs: {x.split("::")[1] for x in xs}  # noqa: E731
    assert {"find_user", "resolve_manager", "latest_login"} <= fn(d["sources"])
    assert fn(d["M_h"]) == {"display_name", "load_profile", "resolve_manager", "manager_email", "escalation_chain",
                            "login_summary"}                       # the six functions that receive a None
    assert set(d["M_h"]) <= set(d["M_q"])
    assert capture.draft_manifests(FIXTURE, ["report.py"])["M_h"] and \
        not any(x.startswith("report.py") for x in capture.draft_manifests(FIXTURE, ["report.py"])["M_q"])


def test_tau_h_rule():
    f = Fraction
    tau, need = capture.tau_h_rule([f(6, 6), f(4, 6), f(3, 6), f(4, 6), f(3, 6)], 5)
    assert need == 4 and tau == f(1, 2)                       # 4th best is 3/6 -> 10/20
    assert capture.tau_h_rule([f(1, 1), f(1, 1), f(1, 1)], 5) == (None, 4)
    assert capture.tau_h_rule([f(2, 3)] * 5, 5)[0] == f(13, 20)


@pytest.fixture()
def root(tmp_path, monkeypatch):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "proofweave-decision-assurance").symlink_to(REPO / "vendor" / "proofweave-decision-assurance")
    (tmp_path / "capture").mkdir()
    monkeypatch.setenv("CDRT_ROOT", str(tmp_path))
    return tmp_path


def test_fetch_approve_and_protocol(root):
    repo = root / "src-repo"
    shutil.copytree(FIXTURE, repo)
    (repo / "LICENSE").write_text("MIT License\n")
    run = lambda *c: subprocess.run(list(c), cwd=repo, check=True, capture_output=True)  # noqa: E731
    run("git", "init", "-q")
    run("git", "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    run("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    cfg = decl(target={"repository": str(repo), "commit": sha, "expected_functions": [1, 50], "exclude": []})
    t = capture.fetch_target(str(repo), sha, lambda m: None)
    assert not (t / ".git").exists() and capture.licence(t).startswith("LICENSE: MIT")
    d = capture.draft_manifests(t, [])
    capture.write_drafts(d, cfg)
    assert capture.approval_status()[0] is False
    (capture.manifest_dir() / "drafts" / "M_q.json").write_text(json.dumps({"functions": []}))
    with pytest.raises(capture.CaptureError, match="subset"):  # M_h must stay inside M_q
        capture.approve("Reviewer")
    capture.write_drafts(d, cfg)
    rec = capture.approve("Reviewer")
    assert capture.approval_status()[0] and rec["sizes"]["M_h"] == len(d["M_h"])
    (capture.manifest_dir() / "M_h.json").write_text("{}")
    assert not capture.approval_status()[0]                   # an edit after approval needs a new approval
    capture.approve("Reviewer")
    f = capture.write_protocol(cfg, capture.capture_dir() / "pilot", 5, 0, None)
    p = subprocess.run([sys.executable, "-m", "pwexp.cli", "--protocol", str(f), "protocol", "check"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr              # pwexp accepts the generated decision protocol
    pol = json.loads((capture.capture_dir() / "pilot" / "policies" / "P1@1.json").read_text())
    assert pol["threshold"] == {"numerator": 0, "denominator": 1} and "PILOT ONLY" in pol["note"]
    final = capture.write_protocol(cfg, capture.capture_dir(), 12, 1, Fraction(1, 2))
    proto = yaml.safe_load(final.read_text())
    assert proto["decisions"]["groups"][0]["count"] == 12 and proto["acquisition"]["semgrep_runs"] == 1
    assert proto["acquisition"]["models"] == [{"provider": "openai", "model": "gpt-x"}]
    assert "key" not in final.read_text().lower().replace("keys", "")


def test_key_prompt_checks_and_never_stores(root, monkeypatch, capsys):
    from cdrt import cli
    (root / "capture" / "capture.yaml").write_text(yaml.safe_dump(decl()))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "sk-test-secret-1234")
    seen = {}
    monkeypatch.setattr(capture, "model_check", lambda p, m, k: (seen.update(k=k) or (k == "sk-test-secret-1234", "ok")))
    s = cli._key_for([1, 2], dev=False)
    assert s == {"key": "sk-test-secret-1234"} and seen["k"] == "sk-test-secret-1234"
    assert "sk-test-secret" not in capsys.readouterr().out
    assert cli._key_for([3, 4], dev=False) == {}                # offline labs never ask
    monkeypatch.setattr(capture, "model_check", lambda p, m, k: (False, "HTTP 401"))
    assert cli._key_for([1], dev=False) is None
    assert cli._range("1-2") == [1, 2] and cli._range("3") == [3]
