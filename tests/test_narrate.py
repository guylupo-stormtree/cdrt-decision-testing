"""The plain-language story: built from the run's own records, saved per lab and for the whole run."""
from __future__ import annotations

from pathlib import Path

from cdrt import narrate
from cdrt.cli import watch_line
from cdrt.labs import book

REPO = Path(__file__).parents[1]
QUIET = lambda m: None  # noqa: E731


def test_one_plain_line_per_audit_run():
    c = narrate.Commentator()
    lines = ["Decision 3/50  G-main-03 · policy P1@1 · basis gpt-pw-m1/run003", "  gpt-pw-m1/run003: GREEN · 75.0 s",
             "  decision G-main-03: green", "Decision 4/50  G-main-04 · policy P1@1 · basis gpt-pw-m1/run004",
             "  gpt-pw-m1/run004: not GREEN · 9.5 s", "  decision G-main-04: not_green", "Semgrep 1/1"]
    out = [x for x in map(c, lines) if x]
    assert out[0] == "  ► Run 3 of 50: GREEN, RepoAudit found no bugs (1 min 15 s). GREEN so far: 1 of 1."
    assert out[1].startswith("  ► Run 4 of 50: NOT GREEN") and out[1].endswith("GREEN so far: 1 of 2.")
    assert "Semgrep" in out[2] and len(out) == 3


def test_every_lab_tells_its_story_and_saves_it(dev_bundle, cdrt_root):
    b, _ = dev_bundle
    (cdrt_root / "protocol").symlink_to(REPO / "protocol")
    told = []
    b.run(5, progress=told.append)
    text = "\n".join(told)
    assert "Lab 5 · Today's requirement · DEVELOPMENT DATA" in text and "what happened" in text
    assert "Today's release requirement: at least 80% of the" in text
    story = (cdrt_root / "results" / "labs-dev" / "STORY.md").read_text()
    for n in (3, 4, 5):
        assert f"Lab {n} ·" in story
    assert "Green Verdict Ambiguity" in story
    att = sorted((cdrt_root / "results" / "labs-dev" / "lab5").glob("attempt*"))[-1]
    assert "what happened" in (att / "story.md").read_text()


def test_failure_is_told_plainly_and_needs_no_network(cdrt_root):
    told = []
    res = book(dev=False).run(0, progress=told.append)          # no capture.yaml here: Lab 0 fails
    assert not res.passed and "This step did not complete" in "\n".join(told)
    assert "downloads" not in "\n".join(told)


def test_watch_line(dev_bundle):
    assert watch_line(True) == "No lab is running."


def test_commentator_counts_runs_kept_from_before_a_pause():
    c = narrate.Commentator()
    assert "kept from before the pause" in c("Decision 1/50  G-main-04: kept from before the pause (not_green)")
    assert "GREEN so far: 1 of 2" in c("Decision 2/50  G-main-19: green (completed after the pause)")


def test_every_lab_keeps_its_screen_output(dev_bundle):
    from cdrt import paths
    att = max((paths.labs_dir(True) / "lab4").glob("attempt*"), key=lambda p: int(p.name[7:]))
    screen = (att / "screen.txt").read_text()
    assert "Lab 4" in screen and (att / "card.txt").read_text().strip() in screen
