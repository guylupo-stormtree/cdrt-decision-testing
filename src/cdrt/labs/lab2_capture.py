"""Lab 2: capture (requirements R-CAP-1, R-CAP-3, R-CAP-8).

Runs the locked campaign through pwexp Stage 1 in a campaign cycle: every scheduled G-main decision with its
context sealed before its RepoAudit run, plus the standalone Semgrep scan(s), every outcome kept. pwexp refuses
a campaign cycle unless the capture lock is valid and the model equals the locked one. Lab 3 then builds the
corpus. The API key is the one typed and checked at the start of `cdrt lab run 1-2`.
"""
from __future__ import annotations

import json

from .. import capture, paths
from .framework import Check, LabContext, LabResult


def run(ctx: LabContext) -> LabResult:
    cfg = capture.declaration()
    key = ctx.secrets.get("key")
    if not key:
        return LabResult([Check("API key entered and checked at the start of the run", False,
                                "run `cdrt lab run 2` or `cdrt lab run 1-2` (the key is asked for once, then checked)")], {})
    off = capture.host_utc_offset()
    checks = [Check("this host's UTC offset equals the declared log_utc_offset", off == cfg["log_utc_offset"],
                    f"host {off}, declared {cfg['log_utc_offset']}")]
    if not checks[0].ok:
        return LabResult(checks, {})
    records = capture.capture_dir() / "records"
    proto = paths.root() / ctx.inputs["handoff"]["protocol"]
    model = f"{cfg['model']['provider']}:{cfg['model']['model']}"
    try:
        cid = capture.new_cycle(records, proto, "campaign")
    except capture.CaptureError as e:
        return LabResult(checks + [Check("campaign cycle created under the capture lock", False, str(e))], {})
    ctx.progress(f"campaign cycle {cid}: {cfg['runs']['campaign']} RepoAudit runs with {model}, "
                 f"{cfg['runs']['semgrep_standalone']} standalone Semgrep scan(s)")
    rc, _ = capture.pwexp(records, proto, "run-stage", "1", "--cycle", cid, *capture.model_args(cfg), "--key-stdin",
                          key=key, progress=ctx.progress)
    data = json.loads((records / "cycles" / cid / "cycle.json").read_text())
    st = data["stages"]["1"]
    checks += [Check("campaign cycle created under the capture lock", True, cid),
               Check("Stage 1 passed every check (every run and decision kept, contexts sealed first, no key in any output)",
                     rc == 0 and st["status"] == "complete", ", ".join(k for k, v in (st.get("checks") or {}).items() if not v))]
    o = st.get("outcome") or {}
    summary = {"campaign cycle": cid, "RepoAudit": f"{o.get('repoaudit_green')}/{o.get('repoaudit_runs')} GREEN",
               "decisions": json.dumps((o.get("decisions") or {}).get("by_group", {})),
               "Semgrep": f"{o.get('semgrep_green')}/{o.get('semgrep_runs')} GREEN"}
    return LabResult(checks, {"stage1": records / "cycles" / cid / "stage1"}, summary,
                     handoff={"cycle": cid}, next_hint="cdrt lab run 3-9   (offline from here: no key, no RepoAudit)")
