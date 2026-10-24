"""Report generation (R-REP-1, R-REP-2, R-REP-4): block filling, completeness refusal, escaping."""
from __future__ import annotations

import pytest

from cdrt import report

PAPER = r"""\documentclass{article}
\usepackage{tikz}
\usetikzlibrary{arrows.meta}
% BEGIN GENERATED:results_macros
\newcommand{\ResultState}{measurements pending}
% END GENERATED:results_macros
\begin{document}
% BEGIN GENERATED:functional_table
pending table
% END GENERATED:functional_table
% BEGIN GENERATED:scale_table
pending table
% END GENERATED:scale_table
\end{document}
"""


def test_fill_replaces_existing_blocks_and_inserts_missing_ones_after_their_anchor():
    gen = {n: f"% generated {n}" for n in report.BLOCKS}
    text, replaced, inserted = report.fill(PAPER, gen)
    assert replaced == ["results_macros", "functional_table", "scale_table"]
    assert inserted == ["fixture_macros", "pathway_figure", "scale_figure", "pgfplots (preamble)"]
    assert "pending" not in text and text.count("% BEGIN GENERATED:") == 6
    assert text.index("END GENERATED:results_macros") < text.index("BEGIN GENERATED:fixture_macros")
    assert text.index("END GENERATED:scale_table") < text.index("BEGIN GENERATED:scale_figure")
    assert text.index(r"\usepackage{pgfplots}") < text.index(r"\begin{document}")
    again, replaced2, inserted2 = report.fill(text, gen)                 # idempotent once the blocks exist
    assert again == text and inserted2 == [] and len(replaced2) == 6
    assert text.index("END GENERATED:functional_table") < text.index("BEGIN GENERATED:pathway_figure")


def test_fill_refuses_without_an_anchor():
    with pytest.raises(ValueError, match="anchor"):
        report.fill(PAPER.replace("scale_table", "other_table"), {n: "" for n in report.BLOCKS})


def test_completeness_names_every_gap():
    d = {"lock": {"lock_root": "L"}, "acceptance": {"lock_root": "X"},
         "functional": [{"id": "step1", "executed": True, "lock_root": "L"}, {"id": "F1", "executed": False, "lock_root": "L"}],
         "timing": [{"lock_root": "L"}, {"lock_root": "old"}]}
    gaps = report.completeness(d, 400, ["step1", "F1"])
    assert any("F1" in g for g in gaps) and any("2 timed cycles" in g for g in gaps)
    assert any("1 timing records" in g for g in gaps) and any("acceptance" in g for g in gaps)


def test_tex_escaping_and_shares():
    from fractions import Fraction
    assert report.tex("fixture_guarded@x 50% & #1") == r"fixture\_guarded@x 50\% \& \#1"
    assert report.share(Fraction(17, 20)) == r"85\%" and report.share(Fraction(2, 3)) == "2/3"
