"""Fixture build (Lab 5; R-FIX-1 … R-FIX-5, as narrowed by main-14). Deterministic and offline: everything
derives from the frozen bundle and the declared rules, so two builds give identical bytes.

  parameters.json   c_obs, tau_q, t_e, Delta_q, sizes, n_0, the main decision and the captured GREEN decisions
  profiles/         rev1 (conformance), rev2 (+ adequacy, base-check), rev3 (+ independent-check); decision_ref = main
  manifests/        the scope manifests, byte-identical copies from the bundle
  planes/N<k>/      scale planes: k synthetic copies of main's RepoAudit run, all marked synthetic, and one
                    synthetic decision whose basis is all k copies (PW-BIND-9; authentic records never mix in)
"""
from __future__ import annotations

import json
import math
import shutil
from datetime import timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml

from pwexp.hashing import manifest_hash, sha256_bytes, sha256_file, tree_manifest
from pwexp.proofweave.graph import TargetIndex
from pwexp.proofweave.ingress import EvidencePlane

from .records import view
from .records.assessments import BASE, assessments
from .tests_registered.common import parse_utc

ISO = "%Y-%m-%dT%H:%M:%S.%fZ"


class FixtureError(Exception):
    pass


def copy_tree(src: Path, dst: Path) -> Path:
    """Copy file contents only (the frozen bundle is read-only; its copies must not be)."""
    for f in sorted(Path(src).rglob("*")):
        t = Path(dst) / f.relative_to(src)
        if f.is_dir():
            t.mkdir(parents=True, exist_ok=True)
        else:
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, t)
    Path(dst).mkdir(parents=True, exist_ok=True)
    return Path(dst)


def _coverage(s: view.Snapshot, did: str, scope: list[str]) -> Fraction:
    got = {r["target"] for r in assessments(s, did)["records"] if r["validator"] == BASE}
    return Fraction(len(got & set(scope)), len(set(scope)))


def parameters(bundle: Path, s: view.Snapshot, selection: dict[str, str], cfg: dict[str, Any]) -> dict[str, Any]:
    """The declared rules of main-14 §4.3 over the main decision and every captured decision."""
    f = cfg["fixtures"]
    step = int(f["threshold_step"])
    mq = json.loads((bundle / "protocol" / "manifests" / "M_q.json").read_text())["functions"]
    mh = json.loads((bundle / "protocol" / "manifests" / "M_h.json").read_text())["functions"]
    main = selection["main"]
    c_obs = _coverage(s, main, mq)
    k = math.floor(step * c_obs)
    captured = view.list_decisions(s)
    records = {d: view.get_decision(s, d)["decision"]["payload"] for d in captured}
    decided = {d: parse_utc(r["decided_at"]) for d, r in records.items()}
    green = [d for d in captured if records[d]["verdict"] == "green"]
    t_e = max(decided.values()) + timedelta(seconds=int(f["age_after_decision_s"]))
    # relevant observations: every green captured decision is assessed (main and the observation), so the age
    # margin is taken over all of them and age never decides a verdict
    times = [parse_utc(r["time"]) for d in green for r in assessments(s, d)["records"] if r["time"]]
    oldest = min(times)
    delta = math.ceil((t_e - oldest).total_seconds()) + int(f["age_margin_s"])
    n0 = view.get_decision(s, main)["binding"]["payload"]["basis_count"]
    sizes = [int(n) for n in cfg["scale"]["target_sizes"]]
    ks = [max(1, math.ceil(n / n0)) for n in sizes]
    return {
        "selection": selection, "captured": len(captured), "green": green,
        "M_h_size": len(set(mh)), "M_q_size": len(set(mq)),
        "c_obs": f"{c_obs.numerator}/{c_obs.denominator}", "c_obs_count": f"{round(c_obs * len(set(mq)))}/{len(set(mq))}",
        "tau_q": {"numerator": k, "denominator": step},
        "t_e": t_e.strftime(ISO), "t_e_rule": f"latest decided_at of the captured decisions + {f['age_after_decision_s']} s",
        "oldest_relevant_observation": oldest.strftime(ISO), "max_age_seconds": delta,
        "n0": n0, "scale_target_sizes": sizes, "scale_k": ks,
        "checks": {"tau_q >= 1/2": Fraction(k, step) >= Fraction(1, 2)},
    }


def _manifest_ref(bundle: Path, name: str) -> dict[str, str]:
    return {"id": name, "sha256": sha256_file(bundle / "protocol" / "manifests" / f"{name}.json")}


def profiles(bundle: Path, p: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """rev 1 conformance only; rev 2 adds adequacy with base-check; rev 3 adds independent-check, nothing else."""
    conf = {"id": "decision-conformance", "revision": 1, "test": "conformance-check@1.0",
            "posture_leaf": "release.effectiveness", "parameters": {"policy_source": "recorded-decision-policy"}}

    def adq(rev: int, validators: list[str]) -> dict[str, Any]:
        return {"id": "decision-adequacy", "revision": rev, "test": "adequacy-check@1.0", "posture_leaf": "release.adequacy",
                "parameters": {"manifest_ref": _manifest_ref(bundle, "M_q"), "minimum_coverage": p["tau_q"],
                               "validators": validators, "max_age_seconds": p["max_age_seconds"],
                               "assessment_time": p["t_e"]}}
    base = {"profile": "release-assurance", "claim": "audit-decision-supports-release", "context_ref": "release-context",
            "snapshot_ref": "corpus", "decision_ref": p["selection"]["main"], "composition": "all-mandatory"}
    return {
        "rev1": {**base, "revision": 1, "label": "rev 1", "requirements": [conf]},
        "rev2": {**base, "revision": 2, "label": "rev 2", "requirements": [conf, adq(1, ["base-check"])]},
        "rev3": {**base, "revision": 3, "label": "rev 3", "requirements": [conf, adq(2, ["base-check", "independent-check"])]},
    }


# ------------------------------------------------------------------ scale planes
def _synthetic_run(src: Path, dst: Path, tag: str) -> None:
    dst.mkdir(parents=True)
    bits = bin(int(sha256_bytes(tag.encode())[:16], 16))[2:].zfill(64)
    pad = ("\n" + "".join(" " if c == "0" else "\t" for c in bits) + "\n").encode()
    for f in sorted(src.iterdir()):
        if not f.is_file():
            continue
        data = f.read_bytes()
        if f.suffix == ".log":
            data = f"# cdrt synthetic copy {tag}\n".encode() + data      # before the first entry: ignored
        elif f.name == "manifest.json":
            doc = json.loads(data)
            doc.update(synthetic_copy_of=doc.get("run"), run=tag)
            data = json.dumps(doc, indent=2, sort_keys=True).encode() + pad
        elif f.suffix in (".json", ".jsonl"):
            data = data + pad
        (dst / f.name).write_bytes(data)


def _synthetic_decision(src: Path, dst: Path, did: str, runs: list[str]) -> None:
    copy_tree(src / "policy", dst / "policy")
    ctx = json.loads((src / "decision_context.json").read_text())
    ctx.update(decision_id=did, basis_runs=runs, synthetic=True)
    ctx["intent"] = {**ctx["intent"], "intent_id": f"intent-{did}"}
    dec = json.loads((src / "decision.json").read_text())
    dec.update(decision_id=did, verdict="green", per_run={r: True for r in runs})
    for name, doc in (("decision_context.json", ctx), ("decision.json", dec)):
        (dst / name).write_text(json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    files = {p.relative_to(dst).as_posix(): sha256_file(p) for p in sorted(dst.rglob("*")) if p.is_file()}
    (dst / "manifest.json").write_text(json.dumps({"kind": "decision", "decision_id": did, "files": files},
                                                  indent=2, sort_keys=True) + "\n")


def plane(bundle: Path, s: view.Snapshot, out: Path, main: str, k: int, work: Path) -> dict[str, Any]:
    d = view.get_decision(s, main)
    run = d["binding"]["payload"]["basis_runs"][0]
    src = bundle / "stage1" / "repoaudit" / run
    p = EvidencePlane(out, TargetIndex.from_snapshot(bundle / "target"), durability="none")
    runs = []
    for i in range(1, k + 1):
        tag = f"synthetic/{run.replace('/', '-')}-c{i:05d}"
        b = work / tag.replace("/", "_")
        _synthetic_run(src, b, tag)
        p.ingest(b, tag, {"synthetic": True})
        runs.append(tag)
        shutil.rmtree(b)
    did = f"S-{k:05d}"
    db = work / did
    _synthetic_decision(bundle / "stage1" / "decisions" / main, db, did, runs)
    p.ingest_decision(db, {}, synthetic=True)
    shutil.rmtree(db)
    p.checkpoint()
    rec = p.query.decision(did)
    return {"decision": did, "k": k, "basis_count": rec["binding"]["payload"]["basis_count"], "status": rec["status"],
            "records": p.ledger.head[0] + 1}


def build(bundle: Path, selection: dict[str, str], out: Path, cfg: dict[str, Any], progress=print) -> dict[str, Any]:
    bundle, out = Path(bundle), Path(out)
    out.mkdir(parents=True)
    s = view.load_snapshot(bundle / "corpus", bundle / "target")
    p = parameters(bundle, s, selection, cfg)
    copy_tree(bundle / "protocol" / "manifests", out / "manifests")
    (out / "profiles").mkdir()
    for name, prof in profiles(bundle, p).items():
        (out / "profiles" / f"{name}.yaml").write_text(yaml.safe_dump(prof, sort_keys=True))
    planes = {}
    work = out / ".work"
    for n, k in zip(p["scale_target_sizes"], p["scale_k"]):
        progress(f"scale plane for N ≈ {n}: {k} synthetic copies of main's run")
        planes[str(n)] = plane(bundle, s, out / "planes" / f"N{n}", selection["main"], k, work)
    shutil.rmtree(work, ignore_errors=True)
    shutil.copyfile(bundle / "CAPTURE.json", out / "planes" / "CAPTURE.json")
    p["planes"] = planes
    p["actual_sizes"] = [planes[str(n)]["basis_count"] for n in p["scale_target_sizes"]]
    p["source"] = {"bundle_sha256": json.loads((bundle / "BUNDLE.json").read_text())["bundle_sha256"],
                   "corpus_sha256": s.corpus_sha256}
    (out / "parameters.json").write_text(json.dumps(p, indent=2, sort_keys=True, default=str) + "\n")
    files = tree_manifest(out)
    (out / "FIXTURES.json").write_text(json.dumps({"files_sha256": manifest_hash(files), "count": len(files)},
                                                  indent=2) + "\n")
    return p
