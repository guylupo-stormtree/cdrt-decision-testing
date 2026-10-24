"""Command line: one command per lab.

  cdrt lab status [--dev]          every lab: · locked  ▶ ready  ✓ passed  ✗ failed
  cdrt lab show N [--dev]          the lab's purpose and its last card
  cdrt lab run N [--dev]           run lab N (refuses unless lab N-1 passed and its hand-off verifies)
  cdrt lab view N NAME [--dev]     path of a review page of lab N's last attempt (e.g. 4 pathways)

--dev runs the offline labs (3 onwards) on the ProofWeave development fixtures; never a result.
"""
from __future__ import annotations

import argparse
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


def cmd_run(a) -> int:
    b = book(a.dev)
    try:
        res = b.run(a.n, progress=lambda m: _p(f"  {m}"))
    except LabError as e:
        _p(f"{FAIL} {e}")
        return 1
    _p("")
    _p(res.summary["_card"])
    return 0 if res.passed else 1


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cdrt", description="Composable CDRT experiment, run lab by lab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lab = sub.add_parser("lab", help="run and inspect the labs")
    ls = lab.add_subparsers(dest="action", required=True)
    for name, fn, args in (("status", cmd_status, ()), ("show", cmd_show, ("n",)), ("run", cmd_run, ("n",)),
                           ("view", cmd_view, ("n", "name"))):
        p = ls.add_parser(name)
        for x in args:
            p.add_argument(x, type=int if x == "n" else str)
        p.add_argument("--dev", action="store_true", help="development mode (fixtures; never a result)")
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
