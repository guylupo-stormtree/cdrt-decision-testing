"""Plain-language narration of the experiment, for a non-technical audience and a video recording.

Every lab prints a short story when it starts and when it ends, and saves it as story.md in its attempt folder;
results/labs[-dev]/STORY.md collects the whole experiment. Every number is read from the run's own records,
the frozen bundle or a named public source (PyPI download statistics, with the date); nothing is invented, and
a value that is not available is said to be unavailable. During the capture each run gets one plain line.
"""
from __future__ import annotations

import json
import re
import textwrap
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import paths

WIDTH = 96
TITLES = {0: "Getting ready", 1: "A first look (pilot)", 2: "The real audit runs", 3: "Freezing the evidence",
          4: "The reveal: same green, different checks", 5: "Today's requirement", 6: "Locking the experiment",
          7: "CDRT tests the decisions", 8: "How fast is it?", 9: "Writing the results into the paper"}


# ------------------------------------------------------------------ output
def block(n: int, phase: str, sentences: list[str], dev: bool) -> str:
    head = f" ▶ Lab {n} · {TITLES.get(n, '')}" + (" · DEVELOPMENT DATA (rehearsal)" if dev else "") + \
        ("" if phase == "start" else " · what happened")
    lines = ["═" * WIDTH, head, "─" * WIDTH]
    for s in sentences:
        lines += textwrap.wrap(s, WIDTH - 2, initial_indent="  ", subsequent_indent="  ") + [""]
    lines[-1:] = ["═" * WIDTH]
    return "\n".join(lines)


def save(text: str, attempt_dir: Path, dev: bool) -> None:
    plain = re.sub(r"[═─▶]", "", text).strip()
    with (attempt_dir / "story.md").open("a") as f:
        f.write(plain + "\n\n")
    with (paths.labs_dir(dev) / "STORY.md").open("a") as f:
        f.write(f"<!-- {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} -->\n{plain}\n\n")


def tell(n: int, phase: str, sentences: list[str], dev: bool, attempt_dir: Path, out: Callable[[str], None]) -> None:
    text = block(n, phase, sentences, dev)
    out("\n" + text + "\n")
    save(text, attempt_dir, dev)


# ------------------------------------------------------------------ facts
def downloads(package: str) -> str:
    """Last month's PyPI downloads, from pypistats.org, with the date; or a plain 'not available'."""
    try:
        with urllib.request.urlopen(f"https://pypistats.org/api/packages/{package}/recent", timeout=10) as r:
            n = json.loads(r.read())["data"]["last_month"]
        day = datetime.now(timezone.utc).strftime("%d %B %Y")
        return f"about {n / 1e6:,.0f} million downloads in the last month (pypistats.org, {day})"
    except Exception:  # noqa: BLE001  the story says so; it never guesses
        return "its download count could not be retrieved just now"


def _json(p: Path) -> Any:
    return json.loads(p.read_text())


def _decl() -> dict[str, Any]:
    from . import capture
    try:
        return capture.declaration()
    except Exception:  # noqa: BLE001
        return {}


def _h(handoff: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    return ((handoff or {}).get("handoff") or {}).get(key, default)


# ------------------------------------------------------------------ start of each lab
def start(n: int, dev: bool) -> list[str]:
    d = _decl()
    t = (d.get("target") or {})
    name = t.get("pypi") or (t.get("repository") or "the target").rstrip("/").split("/")[-1]
    model = f"{(d.get('model') or {}).get('model', 'the declared model')}"
    runs = (d.get("runs") or {})
    return {
        0: [f"We are about to download {name}, a real, widely used open-source library"
            + (f": {downloads(t['pypi'])}" if t.get("pypi") and not dev else "") + ".",
            (f"We audit one part of it: {t['scope']}. " if t.get("scope") else "") +
            "We will scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a value that "
            "may be empty (in Python, None) and crashing. First we mark, with our own independent analysis, the "
            "places in the code where such an empty value can be handed from one function to another. That is the "
            "area a careful audit has to look at."],
        1: [f"RepoAudit now audits the library {runs.get('pilot', 'a few')} times, as a first look, using the AI model "
            f"{model}. Each run ends with a verdict: GREEN means no bug found.",
            "From these first runs we fix the auditor's own policy, the standard it was held to at the time, before "
            "the real audit starts. Once fixed, it cannot be changed."],
        2: ["First we lock the audit's rules: the policy from the first look and the number of runs. From now on "
            "they cannot be changed.",
            f"Now the real audit: RepoAudit runs {runs.get('campaign', 'many')} times on exactly the same code, with "
            "the same model and the same question. Before every run we seal what was asked and which policy applies. "
            "Every result is kept, good or bad.",
            "Watch the verdicts. What each GREEN actually checked stays hidden for now."],
        3: ["We hand every decision to ProofWeave, our evidence ledger. It binds together what was asked, which policy "
            "applied, what RepoAudit decided, and exactly what it examined, and seals it so that nothing can be "
            "changed afterwards."],
        4: ["Now we look inside the GREEN verdicts: for each run, which of the places that needed checking did "
            "RepoAudit actually follow?"],
        5: ["We set out today's release requirement, written down before any test is run, and prepare the test "
            "fixtures from the frozen evidence."],
        6: ["We lock the whole experiment: every file, every rule and every piece of code gets a fingerprint. From "
            "here on nothing can be adjusted to fit the results; any change would be detected."],
        7: ["CDRT now tests the recorded decisions without running the auditor again. First it asks: did each decision "
            "follow the policy of its time? Then: is the evidence enough for today's requirement? Then the requirement "
            "changes, and we watch the gateway react."],
        8: ["How fast does this work? We make the evidence much larger, up to about a hundred thousand records, and "
            "time how long a requirement change takes to reach the gateway, 400 times over, against a 5-second limit."],
        9: ["Finally the results are written into the paper's tables and figures, straight from the locked records."],
    }.get(n, [])


# ------------------------------------------------------------------ end of each lab
def finish(n: int, dev: bool, passed: bool, handoff: dict[str, Any], why: str) -> list[str]:
    s = handoff.get("summary") or {}
    if n == 0 and not passed and "M_q (draft)" in s:
        return [f"Our own analysis, independent of the AI auditor, has drafted the list of places to check: "
                f"{s['M_q (draft)']} places where an empty value can be handed between functions, "
                f"{s['M_h (draft)']} of them in the auditor's own area of responsibility.",
                "Before anything runs, a person reviews and approves this list. Then this step is run again."]
    if not passed:
        return [f"This step did not complete. In plain words: {why}. Nothing is lost: the attempt is recorded, and "
                "the step can be run again once the cause is fixed."]
    try:
        out = FINISH[n](handoff, dev)
    except Exception as e:  # noqa: BLE001  never let the story break the experiment
        out = [f"This step completed. (The plain-language summary could not be assembled: {type(e).__name__}.)"]
    return [x for x in out if x] + ["This step passed all its checks."]


def _f0(h, dev):
    s = h["summary"]
    d = _decl()
    lists = {}
    from . import capture
    for name in ("M_h", "M_q"):
        f = capture.manifest_dir() / f"{name}.json"
        if f.exists():
            lists[name] = len(_json(f)["functions"])
    return [f"The library is downloaded at exactly the published version we declared ({s.get('target', '')}); its "
            f"licence allows us to publish it with the results ({s.get('licence', 'licence recorded')}).",
            f"Our own analysis, independent of the AI auditor, found {lists.get('M_q', 'several')} places where an "
            f"empty value can be handed between functions; {lists.get('M_h', 'some')} of them form the auditor's own "
            "area of responsibility. A person reviewed and approved these lists before anything ran.",
            f"The AI model will be {(d.get('model') or {}).get('model', 'the declared one')}."]


def _f1(h, dev):
    s = h["summary"]
    rows = [x.strip() for x in str(s.get("pilot decisions", "")).split(",") if x.strip()]
    greens = sum(" GREEN " in f" {r} " for r in rows)
    cov = [r.split()[-1] for r in rows]
    return [f"All {len(rows)} first runs are in: {greens} said GREEN, no bugs found.",
            f"But they did not check the same amount: of the auditor's area they covered {', '.join(cov)}.",
            f"From these runs the auditor's policy is now fixed: a run must cover at least {s.get('tau_h', 'the declared share')} "
            "of its area. This policy, and the number of runs, are locked in at the start of the real audit.",
            (f"Each run asked the AI model {s['model calls per run']} questions and took {s['minutes per run']} minutes."
             if s.get("model calls per run") else "")]


def _f2(h, dev):
    s = h["summary"]
    m = re.match(r"(\d+)/(\d+)", str(s.get("RepoAudit", "")))
    said = f"in {m.group(1)} of {m.group(2)} runs" if m else "in its runs"
    return [f"The real audit is complete: RepoAudit said GREEN {said}. Every run, "
            "with what was asked and the policy in force, is kept.",
            "So far it looks like a clean bill of health. Next we look at what those GREENs actually rest on."]


def _f3(h, dev):
    s = h["summary"]
    return [f"All decisions are now in the evidence ledger: {s.get('records', 'all')} records, each traceable to "
            "RepoAudit's own log, bound to its question, its decision and its policy, and sealed.",
            f"Decisions: {s.get('decisions', '')}."]


def _f4(h, dev):
    from .records import view
    from .records.assessments import BASE, assessments
    b = paths.root() / _h(h, "bundle")
    snap = view.load_snapshot(b / "corpus", b / "target")
    mq = set(_json(b / "protocol" / "manifests" / "M_q.json")["functions"])
    green = _h(h, "green") or []
    reached = {d: {r["target"] for r in assessments(snap, d)["records"] if r["validator"] == BASE} & mq for d in green}
    counts = sorted(len(v) for v in reached.values())
    paths_ = len({frozenset(v) for v in reached.values()})
    union = set().union(*reached.values()) if reached else set()
    return [f"Here is the problem. All {len(green)} runs said GREEN. But behind the same answer, they checked "
            f"between {counts[0] if counts else 0} and {counts[-1] if counts else 0} of the {len(mq)} places that "
            f"needed checking, along {paths_} different paths.",
            "Same tool, same code, same question, same model: a different audit every time. The verdict alone "
            "cannot tell a gateway which kind it got. We call this the Green Verdict Ambiguity.",
            f"Together, though, the runs reached {len(union)} of the {len(mq)} places. Keep that number in mind.",
            f"One run is chosen by a rule fixed in advance to be tested in detail: {(_h(h, 'selection') or {}).get('main', '')}."]


def _f5(h, dev):
    p = _json(paths.root() / _h(h, "parameters"))
    tq = p["tau_q"]
    pct = round(100 * tq["numerator"] / tq["denominator"])
    need = -(-p["M_q_size"] * tq["numerator"] // tq["denominator"])
    return [f"Today's release requirement: at least {pct}% of the {p['M_q_size']} places must have been checked, "
            f"that is {need} or more.",
            f"The chosen run, on its own, checked {p['c_obs_count']}.",
            "The requirement was written down before any of the evidence was examined."]


def _f6(h, dev):
    return [f"The experiment is locked. Its fingerprint begins {str(_h(h, 'lock_root', ''))[:12]}. Every result from "
            "now on carries this fingerprint, so anyone can check that nothing was changed."]


def _f7(h, dev):
    recs = [json.loads(l) for l in (paths.root() / _h(h, "functional_records")).read_text().splitlines() if l.strip()]
    by = {r["id"]: r for r in recs}
    obs = (by.get("observation") or {}).get("observed") or {}
    main = (_h(h, "selection") or {}).get("main")
    alone = (obs.get(main) or {})
    comp = (by.get("observation") or {}).get("composed") or {}
    before, after = (by.get("before") or {}).get("observed") or {}, (by.get("after") or {}).get("observed") or {}
    delayed = (by.get("delayed") or {}).get("observed") or {}
    narrow = sum(1 for v in obs.values() if v.get("narrow"))
    word = lambda g: str(g or "").upper()  # noqa: E731
    out = [f"First question, did each decision follow the policy of its time? "
           f"{sum(1 for v in obs.values() if v.get('H') == 'SUCCESS')} of {len(obs)}: yes.",
           f"Second question, is the evidence enough for today? The chosen run alone checked {alone.get('coverage_alone', '?')}: "
           f"the gateway would say {word(alone.get('gateway_alone'))}. {narrow} of the {len(obs)} GREEN runs were each too "
           "narrow on their own.",
           f"CDRT then combines the qualified runs: together they checked {comp.get('covered', '?')}, and the gateway says "
           f"{word(before.get('gateway'))}. The decision rests on independently tested, combined evidence, not on one "
           "GREEN verdict.",
           f"Now the requirement changes: an independent second check is also required, which no run had. The past "
           f"decisions still followed their own policy, but they are no longer enough: the gateway says "
           f"{word(after.get('gateway'))}.",
           ("A late, outdated 'yes' from before the change arrives afterwards and is refused, so it cannot switch the "
            "gateway back to proceed." if not delayed.get("old_admitted") else "A late, outdated result was not refused."),
           "Throughout, the AI auditor was never run again."]
    return out


def _f8(h, dev):
    s = h["summary"]
    m = re.search(r"([\d.]+) s at N = ([\d,]+)", str(s.get("slowest update (T_max)", "")))
    if m:
        return [f"Even with {m.group(2)} records of evidence, the slowest of all 400 updates reached the gateway in "
                f"{m.group(1)} seconds, inside the 5-second limit." if float(m.group(1)) <= 5 else
                f"With {m.group(2)} records the slowest update took {m.group(1)} seconds, beyond the 5-second limit.",
                str(s.get("result", ""))]
    return [str(s.get("result", "The timing result is recorded."))]


def _f9(h, dev):
    return ["The paper's numbers, tables and figures are now generated directly from the locked records"
            + (" (development data, for rehearsal only)." if dev else "."),
            "Anyone can download the single public repository and repeat every step after the audit without the AI "
            "model."]


FINISH = {0: _f0, 1: _f1, 2: _f2, 3: _f3, 4: _f4, 5: _f5, 6: _f6, 7: _f7, 8: _f8, 9: _f9}


# ------------------------------------------------------------------ live line per audit run (Labs 1-2)
class Commentator:
    """Turns pwexp's progress lines into one plain line per audit run, e.g.
    'Run 12 of 50: GREEN, RepoAudit found no bugs (5 min 12 s). GREEN so far: 12 of 12.'"""

    def __init__(self) -> None:
        self.k = self.total = self.greens = self.done = 0
        self.secs: float | None = None

    def __call__(self, raw: str) -> str | None:
        if m := re.search(r"Decision (\d+)/(\d+)\s+G-", raw):
            self.k, self.total, self.secs = int(m.group(1)), int(m.group(2)), None
        elif m := re.search(r"run\d+: (?:GREEN|not GREEN) · ([\d.]+) s", raw):
            self.secs = float(m.group(1))
        elif m := re.search(r"decision G-\S+: (green|not_green)\b", raw):
            green = m.group(1) == "green"
            self.done += 1
            self.greens += green
            took = f" ({int(self.secs // 60)} min {int(self.secs % 60)} s)" if self.secs is not None else ""
            return (f"  ► Run {self.k or self.done}{f' of {self.total}' if self.total else ''}: "
                    + ("GREEN, RepoAudit found no bugs" if green else "NOT GREEN, RepoAudit reported a problem or did not finish")
                    + f"{took}. GREEN so far: {self.greens} of {self.done}.")
        elif m := re.search(r"^Semgrep (\d+)/(\d+)", raw.strip()):
            return (f"  ► Independent check {m.group(1)} of {m.group(2)}: Semgrep, a conventional rule-based scanner "
                    "that uses no AI, scans the same code.")
        return None
