"""Lab 6: lock (requirements A7, R-LOCK-1 … R-LOCK-5).

Writes protocol.lock.json over the frozen bundle, the fixtures, the oracle, the profiles, the runtime
(src/cdrt, registered tests and harness included), the run configuration, uv.lock and the resolved pwexp
commit, and verifies it at once. Labs 7-9 verify it again before they start.

The reported lock (not dev) needs a clean working tree: the lock commit is tagged cdrt-protocol-v<N> and
the campaign is listed in results/CAMPAIGNS.md (R-LOCK-5). In dev mode the lock lives in results/labs-dev/,
the tree may be dirty (this is recorded) and nothing is tagged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import lock, paths
from .framework import Check, LabContext, LabResult, rel


def _tag() -> tuple[bool, str]:
    n = len([t for t in lock.git("tag", "--list", "cdrt-protocol-v*").splitlines() if t]) + 1
    name = f"cdrt-protocol-v{n}"
    lock.git("tag", "-a", name, "-m", f"CDRT protocol lock {n}")
    return bool(lock.git("rev-parse", "--verify", f"refs/tags/{name}")), name


def run(ctx: LabContext) -> LabResult:
    dirty = lock.git("status", "--porcelain", "--untracked-files=no") != ""
    attempt = int(ctx.attempt_dir.name.removeprefix("attempt"))
    campaign = f"{'dev' if ctx.dev else 'campaign'}-{attempt:03d}"
    if not ctx.dev and dirty:
        return LabResult([Check("working tree is clean before the lock", False, "commit or discard changes first")], {})
    doc = lock.write(ctx.dev, campaign)
    f = lock.lock_file(ctx.dev)
    ok, problems, _ = lock.verify(ctx.dev)
    first, why = lock.oracle_committed_first()
    excluded = not any("workbench" in k for k in doc["components"]) and \
        not (paths.root() / "src" / "cdrt" / "workbench").exists()
    checks = [
        Check("verify-lock passes (every component recomputed)", ok, "; ".join(problems)),
        Check("workbench/ is excluded from the lock", excluded),
        Check("oracle expectations were committed before the decision tests (R-ORC-1)", first, why),
    ]
    tag = "not tagged (development)"
    if not ctx.dev and all(c.ok for c in checks):
        tagged, name = _tag()
        checks.append(Check("lock commit tagged", tagged, name))
        tag = name
        with (paths.root() / "results" / "CAMPAIGNS.md").open("a") as fh:
            fh.write(f"| {campaign} | {doc['lock_root']} | {name} | "
                     f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')} | first run of this lock |\n")
    summary = {"lock_root": doc["lock_root"], "campaign_id": campaign, "git_commit": doc["git_commit"][:12] +
               (" (working tree dirty)" if dirty else ""), "pwexp": f"{doc['components']['pwexp']['tag']} "
               f"{doc['components']['pwexp']['commit'][:12]}", "tag": tag}
    return LabResult(checks, {"lock": f}, summary,
                     handoff={"lock": rel(f), "lock_root": doc["lock_root"], "campaign_id": campaign,
                              "git_commit": doc["git_commit"], "pwexp_commit": doc["components"]["pwexp"]["commit"],
                              **{k: ctx.inputs["handoff"][k] for k in ("fixtures", "bundle", "selection", "green", "parameters")}},
                     next_hint=f"cdrt lab run 7{' --dev' if ctx.dev else ''}")
