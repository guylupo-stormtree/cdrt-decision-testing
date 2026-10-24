"""The ten labs of the CDRT experiment (see README.md)."""
from __future__ import annotations

from . import lab3_corpus, lab4_review
from .framework import Lab, LabBook

LABS = [
    Lab(0, "Set up and declare", "Check the environment, fetch the target, draft and approve M_h and M_q, "
        "write the policies and the decision schedule.", False, None, "B7"),
    Lab(1, "Pilot capture", "A few G-main RepoAudit runs and one Semgrep run; declare tau_h (R-CAP-4); take "
        "the capture lock.", True, None, "B7"),
    Lab(2, "Capture", "Run the locked schedule of decisions; each context sealed before its runs.", True, None, "B7"),
    Lab(3, "Build the corpus", "pwexp Stage 2 with decision binding; the record view re-verifies the corpus.",
        False, lab3_corpus.run, "B2", dev_first=True),
    Lab(4, "Review ProofWeave and freeze", "Review decisions and pathways; select the main, strict and pipeline "
        "decisions; freeze the bundle.", False, lab4_review.run, "B2"),
    Lab(5, "Build fixtures", "Thresholds, profiles rev 1-3b, derived variants, scale planes; built twice to "
        "identical bytes.", False, None, "B4"),
    Lab(6, "Lock", "Hash the bundle, fixtures, oracle, profiles, runtime and configuration; tag.", False, None, "B4"),
    Lab(7, "Functional run (RQ1)", "Main sequence, cases F1-F9, interleavings, boundary checks, isolation, "
        "replay; A_comp.", False, None, "B4"),
    Lab(8, "Scale run (RQ2)", "400 timed cycles over four basis sizes against the 5 s budget; p95.", False, None, "B5"),
    Lab(9, "Report", "Generated blocks and the scale figure for the manuscript; the RQ1 and RQ2 answers.",
        False, None, "B6"),
]
VIEWS = {4: ("decisions", "pathways")}


def book(dev: bool) -> LabBook:
    return LabBook(LABS, dev)
