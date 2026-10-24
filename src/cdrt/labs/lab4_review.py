"""Lab 4: review ProofWeave and freeze (R-CAP-5, R-CAP-6, R-CAP-7, R-ORC-4).

Reads the corpus handed over by Lab 3 through the record view, writes the review pages (decisions,
pathways) and copies the decision views, then freezes everything later labs and the oracle need into
capture/bundle[-dev]/: the corpus, the Stage 1 attempt (run and decision bundles), the target snapshot and
the capture protocol files. The bundle is made read-only and identified by its own manifest hash.

The selection of the main, strict and pipeline decisions needs the CDRT oracle's conformance judgement
(R-CAP-5, R-ORC-4); it is added with the oracle in build step B3.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from pwexp.hashing import manifest_hash, tree_manifest

from .. import paths
from ..records import view
from ..views import review
from .framework import Check, LabContext, LabResult, rel


def _read_only(root: Path) -> None:
    for p in sorted(root.rglob("*"), reverse=True) + [root]:
        mode = p.stat().st_mode
        p.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _writable(root: Path) -> None:
    if not root.exists():
        return
    for p in [root] + sorted(root.rglob("*")):
        p.chmod(p.stat().st_mode | stat.S_IWUSR)


def _protocol_files(proto_file: Path) -> list[Path]:
    import yaml
    proto = yaml.safe_load(proto_file.read_text())
    files = [proto_file]
    for block in ("policies", "manifests"):
        files += [proto_file.parent / v["file"] for v in (proto.get(block) or {}).values()]
    return files


def select(bundle: Path, s: view.Snapshot) -> tuple[dict, dict | None, str]:
    """R-CAP-5 by the runtime (resolver → executor → conformance-check) and by the oracle (separate process)."""
    from .. import api
    plan = json.loads((bundle / "stage1" / "plan.json").read_text())
    store = api.manifest_store(bundle / "protocol")
    out = {"main": None, "strict": None, "pipeline": None, "main_candidates": {}}
    for d in [x["decision_id"] for x in plan["decisions"]]:
        rec = view.get_decision(s, d)["decision"]["payload"]
        green = rec["verdict"] == "green"
        if d.startswith("G-main-"):
            h = None
            if green:
                prof = {"profile": "selection", "revision": 1, "context_ref": "selection", "decision_ref": d,
                        "requirements": [{"id": "decision-conformance", "revision": 1, "test": "conformance-check@1.0",
                                          "posture_leaf": "release.effectiveness",
                                          "parameters": {"policy_source": "recorded-decision-policy"}}]}
                h = api.evaluate(api.resolve(prof, s, store)[0], s, store)["state"]
            out["main_candidates"][d] = {"green": green, "H": h}
            if green and h == "SUCCESS" and out["main"] is None:
                out["main"] = d
        elif d.startswith("G-strict-") and green and out["strict"] is None:
            out["strict"] = d
        elif d.startswith("G-pipe-") and green and all(rec["per_run"].values()) and out["pipeline"] is None:
            out["pipeline"] = d
    p = subprocess.run([sys.executable, str(paths.root() / "oracle" / "oracle_check.py"), "select", str(bundle)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return out, None, f"oracle failed: {p.stderr.strip()[-300:]}"
    return out, json.loads(p.stdout), ""


def run(ctx: LabContext) -> LabResult:
    h = ctx.inputs["handoff"]
    root = paths.root()
    corpus, target, s1 = root / h["corpus"], root / h["target"], root / h["stage1"]
    proto_file = root / h["protocol"]
    snap = view.load_snapshot(corpus, target, h["corpus_sha256"])
    mark = "DEVELOPMENT: built from fixture runs, not experiment data" if ctx.dev else \
        f"Corpus {snap.corpus_sha256}"
    pages = ctx.attempt_dir / "views"
    pages.mkdir()
    review.decisions_page(snap, pages / "decisions.html", mark)
    review.pathways_page(snap, pages / "pathways.html", proto_file.parent, mark)
    shutil.copytree(corpus / "decisions", pages / "decision-graphs")
    ctx.progress(f"review pages: {rel(pages)}")

    bundle = paths.bundle_dir(ctx.dev)
    if bundle.exists():
        if not ctx.dev:
            return LabResult([Check("no frozen bundle exists yet", False, f"{rel(bundle)} is already frozen")], {})
        _writable(bundle)
        shutil.rmtree(bundle)
    shutil.copytree(corpus, bundle / "corpus")
    shutil.copytree(s1, bundle / "stage1")
    shutil.copytree(target, bundle / "target")
    for f in _protocol_files(proto_file):
        dst = bundle / "protocol" / f.relative_to(proto_file.parent)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    import yaml
    cap = (yaml.safe_load(proto_file.read_text()).get("capture") or {})
    (bundle / "CAPTURE.json").write_text(json.dumps({"log_utc_offset": cap.get("log_utc_offset"),
                                                    "cycle": h["cycle"], "development": ctx.dev}, indent=2) + "\n")
    files = tree_manifest(bundle)
    doc = {"corpus_sha256": snap.corpus_sha256, "ledger_head": list(snap.ledger_head), "cycle": h["cycle"],
           "files": files, "bundle_sha256": manifest_hash(files), "development": ctx.dev}
    (bundle / "BUNDLE.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    _read_only(bundle)
    frozen = view.load_snapshot(bundle / "corpus", bundle / "target", h["corpus_sha256"])
    runtime, oracle_sel, problem = select(bundle, frozen)
    (ctx.attempt_dir / "selection.json").write_text(json.dumps({"runtime": runtime, "oracle": oracle_sel},
                                                              indent=2, sort_keys=True) + "\n")
    ctx.progress(f"selection: main {runtime['main']} · strict {runtime['strict']} · pipeline {runtime['pipeline']}")
    agree = oracle_sel is not None and all(runtime[k] == oracle_sel.get(k) for k in ("main", "strict", "pipeline")) and \
        {d: c["H"] for d, c in runtime["main_candidates"].items()} == \
        {d: c["H"] for d, c in (oracle_sel or {}).get("main_candidates", {}).items()}
    checks = [
        Check("review pages written (decisions, pathways, decision graphs)", (pages / "pathways.html").exists()),
        Check("frozen corpus re-verifies with the same corpus hash", frozen.corpus_sha256 == h["corpus_sha256"]),
        Check("frozen bundle is read-only", not any(os.access(p, os.W_OK) for p in bundle.rglob("*") if p.is_file())),
        Check("main, strict and pipeline decisions selected by the declared rule",
              all(runtime[k] for k in ("main", "strict", "pipeline")),
              "" if all(runtime[k] for k in ("main", "strict", "pipeline")) else "capture failed: no qualifying " +
              ", ".join(k for k in ("main", "strict", "pipeline") if not runtime[k]) + " decision (R-CAP-5)"),
        Check("the independent oracle makes the same selection and the same conformance judgements", agree,
              problem or ("" if agree else "runtime and oracle differ (see selection.json)")),
    ]
    f9 = {d: c["H"] for d, c in runtime["main_candidates"].items() if d != runtime["main"] and c["green"]}
    summary = {"bundle_sha256": doc["bundle_sha256"], "review": rel(pages / "pathways.html"),
               "selected": f"main {runtime['main']} · strict {runtime['strict']} · pipeline {runtime['pipeline']}",
               "other GREEN G-main (F9)": ", ".join(f"{d} H={h}" for d, h in f9.items()) or "none"}
    return LabResult(checks, {"bundle": bundle, "views": pages}, summary,
                     handoff={"bundle": rel(bundle), "corpus_sha256": snap.corpus_sha256,
                              "bundle_sha256": doc["bundle_sha256"], "selection": runtime, "f9": sorted(f9)},
                     next_hint=f"cdrt lab run 5{' --dev' if ctx.dev else ''}")
