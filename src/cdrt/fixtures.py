"""Fixture build (Lab 5; R-FIX-1 … R-FIX-5). Deterministic and offline: everything derives from the frozen
bundle and the declared rules, so two builds give identical bytes.

  parameters.json   c_obs, tau_q(rev2), tau_q(rev3b), t_e, Delta_q, sizes, n_0 and the selected decisions
  profiles/         rev1, rev2, rev3, rev3b (manuscript Listing 1 shape), decision_ref = main
  manifests/        the scope manifests, byte-identical copies from the bundle
  derived/          disclosed transformations of copies of the corpus:
                      F4  main's policy blob removed (policy-at-event unavailable; records intact)
                      B1  rebuilt without main's binding record (records re-chained)
                      B2  one byte of one main basis record altered (not re-chained: integrity finding)
                      B3  rebuilt without main's basis run (records re-chained)
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
from pwexp.proofweave.graph import InMemoryGraphStore, TargetIndex, Weaver
from pwexp.proofweave.ingress import EvidencePlane
from pwexp.proofweave.ledger import Ledger

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
    f = cfg["fixtures"]
    step = int(f["threshold_step"])
    mq = json.loads((bundle / "protocol" / "manifests" / "M_q.json").read_text())["functions"]
    mh = json.loads((bundle / "protocol" / "manifests" / "M_h.json").read_text())["functions"]
    main = selection["main"]
    c_obs = _coverage(s, main, mq)
    k = math.floor(step * c_obs)
    decided = {d: parse_utc(view.get_decision(s, d)["decision"]["payload"]["decided_at"]) for d in selection.values()}
    t_e = max(decided.values()) + timedelta(seconds=int(f["age_after_decision_s"]))
    times = [parse_utc(r["time"]) for d in selection.values() for r in assessments(s, d)["records"] if r["time"]]
    oldest = min(times)
    delta = math.ceil((t_e - oldest).total_seconds()) + int(f["age_margin_s"])
    n0 = view.get_decision(s, main)["binding"]["payload"]["basis_count"]
    sizes = [int(n) for n in cfg["scale"]["target_sizes"]]
    ks = [max(1, math.ceil(n / n0)) for n in sizes]
    return {
        "selection": selection, "M_h_size": len(set(mh)), "M_q_size": len(set(mq)),
        "c_obs": f"{c_obs.numerator}/{c_obs.denominator}", "c_obs_count": f"{round(c_obs * len(set(mq)))}/{len(set(mq))}",
        "tau_q_rev2": {"numerator": k, "denominator": step}, "tau_q_rev3b": {"numerator": k + 1, "denominator": step},
        "t_e": t_e.strftime(ISO), "t_e_rule": "latest decided_at of the selected decisions + "
                                             f"{f['age_after_decision_s']} s",
        "t_e_literal_R_FIX_2": (decided[main] + timedelta(seconds=int(f["age_after_decision_s"]))).strftime(ISO),
        "oldest_relevant_observation": oldest.strftime(ISO), "max_age_seconds": delta,
        "n0": n0, "scale_target_sizes": sizes, "scale_k": ks,
        "checks": {"tau_q(rev2) >= 1/2": Fraction(k, step) >= Fraction(1, 2), "c_obs < 1": c_obs < 1},
    }


def _manifest_ref(bundle: Path, name: str) -> dict[str, str]:
    return {"id": name, "sha256": sha256_file(bundle / "protocol" / "manifests" / f"{name}.json")}


def profiles(bundle: Path, p: dict[str, Any]) -> dict[str, dict[str, Any]]:
    conf = {"id": "decision-conformance", "revision": 1, "test": "conformance-check@1.0",
            "posture_leaf": "release.effectiveness", "parameters": {"policy_source": "recorded-decision-policy"}}

    def adq(rev: int, tau: dict, validators: list[str]) -> dict[str, Any]:
        return {"id": "decision-adequacy", "revision": rev, "test": "adequacy-check@1.0", "posture_leaf": "release.adequacy",
                "parameters": {"manifest_ref": _manifest_ref(bundle, "M_q"), "minimum_coverage": tau,
                               "validators": validators, "max_age_seconds": p["max_age_seconds"],
                               "assessment_time": p["t_e"]}}
    base = {"profile": "release-assurance", "claim": "audit-decision-supports-release", "context_ref": "release-context",
            "snapshot_ref": "corpus", "decision_ref": p["selection"]["main"], "composition": "all-mandatory"}
    return {
        "rev1": {**base, "revision": 1, "label": "rev 1", "requirements": [conf]},
        "rev2": {**base, "revision": 2, "label": "rev 2", "requirements": [conf, adq(1, p["tau_q_rev2"], ["base-check"])]},
        "rev3": {**base, "revision": 3, "label": "rev 3",
                 "requirements": [conf, adq(2, p["tau_q_rev2"], ["base-check", "independent-check"])]},
        "rev3b": {**base, "revision": 4, "label": "rev 3b", "requirements": [conf, adq(3, p["tau_q_rev3b"], ["base-check"])]},
    }


# ------------------------------------------------------------------ derived copies
def _records(corpus: Path) -> list[dict[str, Any]]:
    return [{k: v for k, v in r.items() if k not in ("seq", "prev_hash", "record_hash")} for r in Ledger(corpus).records()]


def rebuild(corpus: Path, out: Path, target: Path, keep) -> Path:
    """A new, valid plane from the records `keep` accepts, re-chained, with its own graph checkpoint."""
    out.mkdir(parents=True)
    copy_tree(corpus / "blobs", out / "blobs")
    led = Ledger(out, durability="none")
    led.append_batch([r for r in _records(corpus) if keep(r)])
    st = InMemoryGraphStore()
    Weaver(st, TargetIndex.from_snapshot(target)).apply(led.records())
    st.checkpoint(out / "graph-checkpoint.json")
    return out


def derived(bundle: Path, s: view.Snapshot, out: Path, main: str) -> dict[str, str]:
    corpus, target = bundle / "corpus", bundle / "target"
    d = view.get_decision(s, main)
    pol_blob = d["policy"]["source_ref"]["sha256"]
    run = d["binding"]["payload"]["basis_runs"][0]
    made = {}
    f4 = copy_tree(corpus, out / "F4" / "corpus")
    (f4 / "blobs" / pol_blob).unlink()
    made["F4"] = "main's policy-at-event blob removed; every record intact"
    rebuild(corpus, out / "B1" / "corpus", target, lambda r: r["id"] != d["binding"]["id"])
    made["B1"] = "rebuilt without main's binding record (all records re-chained)"
    b2 = copy_tree(corpus, out / "B2" / "corpus")
    lines = (b2 / "ledger.jsonl").read_text().splitlines()
    i = next(n for n, l in enumerate(lines) if json.loads(l)["id"] == d["binding"]["payload"]["basis_record_ids"][0])
    rec = json.loads(lines[i])
    rec["payload_hash"] = ("1" if rec["payload_hash"][0] != "1" else "2") + rec["payload_hash"][1:]   # one byte
    lines[i] = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    (b2 / "ledger.jsonl").write_text("\n".join(lines) + "\n")
    made["B2"] = "one byte of one basis record of main altered, not re-chained"
    rebuild(corpus, out / "B3" / "corpus", target, lambda r: r["run"] != run)
    made["B3"] = f"rebuilt without main's basis run {run} (all records re-chained)"
    for k in made:                       # each copy keeps the capture declaration (log time offset)
        shutil.copyfile(bundle / "CAPTURE.json", out / k / "CAPTURE.json")
    return made


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
    progress("derived copies F4, B1, B2, B3")
    p["derived"] = derived(bundle, s, out / "derived", selection["main"])
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
