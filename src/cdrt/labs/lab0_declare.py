"""Lab 0: set up and declare (requirements A5.1, A5.2; D-005).

Checks the declaration (capture/capture.yaml) and the environment (pwexp setup: RepoAudit's environment at its
pinned commit, Semgrep 1.181.0), fetches the target at its commit, drafts the two scope manifests from our own
parse of the target and stops until a person has reviewed and approved them (`cdrt manifests approve --by NAME`).
Then writes the policy and the pilot protocol. Needs network access, no API key.
"""
from __future__ import annotations

from .. import capture
from .framework import Check, LabContext, LabResult, rel


def run(ctx: LabContext) -> LabResult:
    cfg = capture.declaration()
    bad = capture.problems(cfg)
    checks = [Check("capture/capture.yaml complete and valid", not bad, "; ".join(bad))]
    if bad:
        return LabResult(checks, {})
    ctx.progress("environment: pwexp setup (RepoAudit at its pinned commit, Semgrep 1.181.0)")
    rc, out = capture.pwexp(capture.capture_dir() / "records", capture.capture_dir() / "capture.yaml", "setup",
                            progress=ctx.progress)
    checks.append(Check("RepoAudit pinned and unmodified; Semgrep installed", rc == 0, out.strip().splitlines()[-1] if out.strip() else ""))
    t = cfg["target"]
    try:
        target = capture.fetch_target(t["repository"], t["commit"], ctx.progress)
    except capture.CaptureError as e:
        return LabResult(checks + [Check("target fetched at its commit", False, str(e))], {})
    lic = capture.licence(target)
    py = sum(1 for _ in target.rglob("*.py"))
    checks += [Check("target fetched at its commit", True, f"{t['commit'][:12]}, {py} Python files"),
               Check("licence file present (check it allows redistributing a snapshot and logs)", bool(lic), lic or "none found")]
    d = capture.draft_manifests(target, cfg["target"].get("exclude") or [])
    lo, hi = cfg["target"].get("expected_functions") or [0, 10 ** 9]
    checks.append(Check("functions that can receive a None within the declared range (A5.1)",
                        lo <= len(d["M_q"]) <= hi, f"M_h {len(d['M_h'])}, M_q {len(d['M_q'])}, declared {lo}-{hi}"))
    drafts = capture.write_drafts(d, cfg)
    ok, why = capture.approval_status()
    if ok:   # approved earlier: the approved manifests must still be the drafts' functions, or a person's edit of them
        checks.append(Check("manifests reviewed and approved by a person", True, why))
    else:
        checks.append(Check("manifests reviewed and approved by a person", False,
                            f"{why}. Review (and edit if needed) {rel(drafts)}/M_h.json and M_q.json, then run "
                            "`cdrt manifests approve --by \"Your Name\"` and run Lab 0 again"))
        return LabResult(checks, {"drafts": drafts}, {"M_h (draft)": len(d["M_h"]), "M_q (draft)": len(d["M_q"])})
    proto = capture.write_protocol(cfg, capture.capture_dir() / "pilot", int(cfg["runs"]["pilot"]), 0, None)
    snap = capture.snapshot_sha256(target)
    summary = {"target": f"{t['repository']} @ {t['commit'][:12]}", "licence": lic, "model": f"{cfg['model']['provider']}:{cfg['model']['model']}",
               "runs": f"pilot {cfg['runs']['pilot']}, campaign {cfg['runs']['campaign']}, standalone Semgrep {cfg['runs']['semgrep_standalone']}",
               "snapshot_sha256": snap}
    return LabResult(checks, {"target": target, "manifests": capture.manifest_dir(), "pilot_protocol": proto}, summary,
                     handoff={"target": rel(target), "snapshot_sha256": snap, "pilot_protocol": rel(proto)},
                     next_hint="cdrt lab run 1-2   (asks for the API key once, checks it, then pilot and capture)")
