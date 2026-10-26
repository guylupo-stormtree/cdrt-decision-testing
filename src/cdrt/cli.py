"""Command line: one command per lab.

  cdrt lab status [--dev]          every lab: · locked  ▶ ready  ✓ passed  ✗ failed
  cdrt lab show N [--dev]          the lab's purpose and its last card
  cdrt lab run N[-M] [--dev]       run lab N, or labs N to M in order (each refuses unless the previous one
                                   passed and its hand-off verifies). Labs 1-2 ask for the API key once at the
                                   start, check it with one minimal call, and keep it in memory only
  cdrt capture campaign-runs N     after the pilot, before Lab 2: set the campaign size (Lab 2 locks it)
  cdrt capture reset --label TEXT  archive the capture's working files so Lab 0 starts clean (before any campaign)
  cdrt manifests approve --by NAME approve the scope manifests Lab 0 drafted (after reviewing them)
  cdrt lab watch [--dev] [--once]  one live status line (run it in a second terminal while a lab runs)
  cdrt lab story [--dev]           the plain-language story of the whole experiment so far (STORY.md)
  cdrt lab view N NAME [--dev]     path of a review page of lab N's last attempt (e.g. 4 pathways)
  cdrt verify-lock [--dev]         recompute every locked component and compare (R-LOCK-2)
  cdrt pilot scale [--dev] [--blocks N] [--warmups N]
                                   pilot timing before the lock, into results/pilot/ (R-SCL-9)

--dev runs the offline labs (3 onwards) on the ProofWeave development fixtures; never a result.
"""
from __future__ import annotations

import argparse
import shutil
import sys

from . import paths
from .labs import LABS, VIEWS, book
from .labs.framework import FAIL, OK, LabError

MARK = {"passed": OK, "failed": FAIL, "ready": "▶", "locked": "·", "not in dev mode": " "}


def _p(m: str = "") -> None:
    print(m, flush=True)


def cmd_status(a) -> int:
    b = book(a.dev)
    _p(f"CDRT labs{' [DEVELOPMENT]' if a.dev else ''}")
    for lab in LABS:
        st = b.status(lab.n)
        extra = "" if lab.run else f"  (built in {lab.built_in})"
        _p(f"  {MARK.get(st, '?')} Lab {lab.n}  {lab.name:32} {st}{extra}")
    return 0


def cmd_show(a) -> int:
    b = book(a.dev)
    lab = b.labs[a.n]
    _p(f"Lab {lab.n} · {lab.name}\n  {lab.purpose}\n  status: {b.status(lab.n)}")
    s = b.state().get(str(a.n))
    if s:
        _p("")
        _p((paths.root() / s["handoff"]).with_name("card.txt").read_text().rstrip())
    return 0


def _range(spec: str) -> list[int]:
    a, _, b = str(spec).partition("-")
    return list(range(int(a), int(b or a) + 1))


def _key_for(labs: list[int], dev: bool) -> dict[str, str] | None:
    """Labs that run RepoAudit need the model key: asked for once, here, and checked with one minimal call.
    It lives in this process's memory for the run and is handed to pwexp on standard input only."""
    from .labs import LABS
    if dev or not any(l.needs_model for l in LABS if l.n in labs):
        return {}
    import getpass
    from . import capture
    cfg = capture.declaration()
    bad = capture.problems(cfg)
    if bad:
        _p(f"{FAIL} capture/capture.yaml: " + "; ".join(bad))
        return None
    prov, model = cfg["model"]["provider"], cfg["model"]["model"]
    key = getpass.getpass(f"API key for {prov}:{model} (kept in memory for this run only): ").strip()
    ok, detail = capture.model_check(prov, model, key)
    _p(f"{OK if ok else FAIL} key check: {detail}")
    return {"key": key} if ok else None


def cmd_run(a) -> int:
    b = book(a.dev)
    labs = _range(a.n)
    secrets = _key_for(labs, a.dev)
    if secrets is None:
        return 1
    try:
        for n in labs:
            res = b.run(n, progress=lambda m: _p(f"  {m}"), secrets=secrets)
            _p("")
            _p(res.summary["_card"])
            if not res.passed:
                return 1
        return 0
    except LabError as e:
        _p(f"{FAIL} {e}")
        return 1
    finally:
        secrets.clear()


def cmd_approve(a) -> int:
    from . import capture
    try:
        rec = capture.approve(a.by)
    except capture.CaptureError as e:
        _p(f"{FAIL} {e}")
        return 1
    _p(f"{OK} manifests approved by {rec['approved_by']}: M_h {rec['sizes']['M_h']}, M_q {rec['sizes']['M_q']} functions. "
       "Now run Lab 0 again: cdrt lab run 0")
    return 0


def cmd_view(a) -> int:
    b = book(a.dev)
    if a.name not in VIEWS.get(a.n, ()):
        _p(f"{FAIL} Lab {a.n} has views: {', '.join(VIEWS.get(a.n, ())) or 'none'}")
        return 1
    s = b.state().get(str(a.n))
    if not s:
        _p(f"{FAIL} Lab {a.n} has not run yet")
        return 1
    page = (paths.root() / s["handoff"]).parent / "views" / f"{a.name}.html"
    _p(str(page))
    return 0


def watch_line(dev: bool) -> str:
    """Which lab is running, how far the audit is, GREEN so far, and when RepoAudit was last active."""
    import json
    import time
    from . import capture
    now = time.time()
    running = [d for d in paths.labs_dir(dev).glob("lab*/attempt*") if not (d / "handoff.json").exists()]
    if not running:
        return "No lab is running."
    att = max(running, key=lambda d: d.stat().st_mtime)
    n = int(att.parent.name[3:])
    out = f"Lab {n} running for {_dur(now - att.stat().st_mtime)}"
    cycles = sorted((paths.records_root(dev) / "cycles").glob("*/cycle.json"), key=lambda p: p.stat().st_mtime)
    if n in (1, 2) and cycles and cycles[-1].stat().st_mtime >= att.stat().st_mtime:
        cyc = cycles[-1].parent
        mode = json.loads(cycles[-1].read_text()).get("mode", "")
        try:
            total = capture.declaration()["runs"]["pilot" if mode == "pilot" else "campaign"]
        except Exception:  # noqa: BLE001
            total = "?"
        done = [json.loads(p.read_text()) for p in cyc.glob("stage1/attempt*/decisions/*/decision.json")]
        greens = sum(d.get("verdict") == "green" for d in done)
        out += f" · run {min(len(done) + 1, total) if isinstance(total, int) else len(done) + 1} of {total}" \
               f" · done {len(done)}, GREEN {greens}"
        logs = list((paths.pwexp_checkout() / "vendor" / "RepoAudit" / "log" / "dfbscan").rglob("dfbscan.log"))
        if logs:
            newest = max(logs, key=lambda p: p.stat().st_mtime)
            if newest.stat().st_mtime >= att.stat().st_mtime:   # the run under way: its model calls so far
                with newest.open("rb") as fh:
                    out += f" · model calls {sum(l.count(b' is running') for l in fh):,}"
            out += f" · last active {_dur(now - newest.stat().st_mtime)} ago"
    return out


def _dur(s: float) -> str:
    s = int(max(s, 0))
    return f"{s // 3600} h {s % 3600 // 60} min" if s >= 3600 else f"{s // 60} min {s % 60} s" if s >= 60 else f"{s} s"


def cmd_watch(a) -> int:
    import time
    if a.once:
        _p(watch_line(a.dev))
        return 0
    try:
        while True:
            width = shutil.get_terminal_size((100, 20)).columns - 1   # one line, never wrapped
            print("\r\033[K" + watch_line(a.dev)[:width], end="", flush=True)
            time.sleep(5)
    except KeyboardInterrupt:
        _p()
        return 0


def cmd_story(a) -> int:
    f = paths.labs_dir(a.dev) / "STORY.md"
    _p(f.read_text() if f.exists() else "No story yet: no lab has run.")
    return 0


def cmd_capture(a) -> int:
    from . import capture
    try:
        if a.what == "campaign-runs":
            old = capture.set_campaign_runs(a.n)
            _p(f"{OK} campaign runs {old} → {a.n} in capture/capture.yaml; Lab 2 locks this number before its first run")
        else:
            dst = capture.reset(a.label)
            _p(f"{OK} archived to {dst.relative_to(paths.root())}; run `cdrt lab run 0` to start clean")
        return 0
    except capture.CaptureError as e:
        _p(f"{FAIL} {e}")
        return 1


def cmd_verify_lock(a) -> int:
    from . import lock
    ok, problems, doc = lock.verify(a.dev)
    if ok:
        _p(f"{OK} lock {doc['lock_root'][:12]} verifies (campaign {doc['campaign_id']})")
        return 0
    _p(f"{FAIL} lock does not verify: " + "; ".join(problems))
    return 1


def cmd_pilot_scale(a) -> int:
    """R-SCL-9: pilot timing before the lock, into results/pilot/; never a result."""
    from datetime import datetime, timezone

    import yaml

    from . import lock
    from .harness import scale
    fx = lock.fixtures_dir(a.dev)
    if not (fx / "parameters.json").exists():
        _p(f"{FAIL} no fixtures in {fx}; run Lab 5 first")
        return 1
    when = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cfg = yaml.safe_load((paths.root() / "protocol" / "run_config.yaml").read_text())["scale"]
    stamp = {"lock_root": None, "campaign_id": f"pilot-{when}", "pilot": True,
             "pwexp_commit": lock.pwexp_commit()["commit"]}
    res = scale.run(fx, paths.bundle_dir(a.dev), cfg, stamp, lambda m: _p(f"  {m}"), blocks=a.blocks, warmups=a.warmups)
    out = paths.root() / "results" / "pilot" / f"scale-{when}{'-dev' if a.dev else ''}"
    scale.write(out, res, "PILOT" + (" DEVELOPMENT" if a.dev else ""))
    _p(f"PILOT (never a result) · {out}")
    for v in res["stats"].values():
        _p(f"  N = {v['N']:>7,}  slowest {v['slowest_s']:.3f} s  {v['exceedances']}/{v['observations']} over")
    _p(f"  {res['sentence']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cdrt", description="Composable CDRT experiment, run lab by lab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lab = sub.add_parser("lab", help="run and inspect the labs")
    ls = lab.add_subparsers(dest="action", required=True)
    for name, fn, args in (("status", cmd_status, ()), ("show", cmd_show, ("n",)), ("run", cmd_run, ("n",)),
                           ("view", cmd_view, ("n", "name"))):
        p = ls.add_parser(name)
        for x in args:
            p.add_argument(x, type=(str if name == "run" else int) if x == "n" else str,
                           help="a lab number, or a range such as 1-2 or 3-9" if name == "run" and x == "n" else None)
        p.add_argument("--dev", action="store_true", help="development mode (fixtures; never a result)")
        p.set_defaults(fn=fn)
    w = ls.add_parser("watch", help="one live status line; run it in a second terminal")
    w.add_argument("--dev", action="store_true")
    w.add_argument("--once", action="store_true", help="print the line once and stop")
    w.set_defaults(fn=cmd_watch)
    st = ls.add_parser("story", help="the plain-language story so far")
    st.add_argument("--dev", action="store_true")
    st.set_defaults(fn=cmd_story)
    cp = sub.add_parser("capture", help="before the campaign: set its size, or start the capture again").add_subparsers(
        dest="what", required=True)
    cr = cp.add_parser("campaign-runs", help="set runs.campaign (after the pilot, before Lab 2)")
    cr.add_argument("n", type=int)
    cr.set_defaults(fn=cmd_capture)
    rs = cp.add_parser("reset", help="archive target, manifests, protocols and pilot records (before any campaign)")
    rs.add_argument("--label", required=True, help="why, e.g. 'scope narrowed to the parser'")
    rs.set_defaults(fn=cmd_capture)
    mf = sub.add_parser("manifests", help="approve the reviewed scope manifests drafted by Lab 0")
    mf.add_argument("action", choices=["approve"])
    mf.add_argument("--by", required=True, help="the person approving them")
    mf.set_defaults(fn=cmd_approve)
    vl = sub.add_parser("verify-lock", help="recompute every locked component (R-LOCK-2)")
    vl.add_argument("--dev", action="store_true", help="the development lock")
    vl.set_defaults(fn=cmd_verify_lock)
    pi = sub.add_parser("pilot", help="pilot timing before the lock (R-SCL-9; results/pilot/, never a result)")
    ps = pi.add_subparsers(dest="what", required=True).add_parser("scale")
    ps.add_argument("--dev", action="store_true", help="the development fixtures")
    ps.add_argument("--blocks", type=int, default=None, help="blocks (default: run_config.yaml)")
    ps.add_argument("--warmups", type=int, default=None, help="warm-ups per size (default: run_config.yaml)")
    ps.set_defaults(fn=cmd_pilot_scale)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
