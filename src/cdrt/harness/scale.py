"""Scale protocol (RQ2; requirements A12, R-SCL-1 … R-SCL-8).

Untimed set-up: every plane is loaded and verified through the record view, ProofWeave's decision index is
built (one retrieval), and the rev-2 verdicts of each plane's decision are computed once. Each cycle:

  reset (untimed)   a fresh consumer at the rev-2 posture with those verdicts; the gateway is given that card
  t_activation      time.monotonic_ns(); a reader thread is already waiting on the gateway for a complete
                    posture of revision 3 (deadline 5 s, then up to 60 s in all: late completions are kept)
  timed work        monitor.reassess(rev 3) with both tests re-run on one shared view of the decision:
                    resolution, decision()/basis() retrieval, the binding check, both tests, verdicts,
                    admission, aggregation, publication
  t_gateway_read    time.monotonic_ns() when the reader has the rev-3 posture over HTTP

T_assess = t_gateway_read − t_activation (Eq. 9). Every cycle checks H = SUCCESS, A = FAIL and the revision;
a mismatch, a late completion or a timeout is recorded, never dropped. Five warm-ups per size, then blocks
of all four sizes in a seeded order. The result is one number, the slowest update of the whole campaign
(T_max), read against the budget, with the number of updates over it; the slowest update per size is kept
for the table and figure (D-015).
"""
from __future__ import annotations

import copy
import os
import platform
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from pwexp.hashing import sha256_file

from .. import monitor, paths
from ..control_guard import disabled_control
from ..evaluation import evaluate
from ..gateway import Gateway
from ..posture import Consumer
from ..records import view
from ..records.manifests import ManifestStore
from ..registry import Registry
from ..resolver import resolve
from ..tests_registered.common import FAIL, SUCCESS

H, A = "release.effectiveness", "release.adequacy"


def with_decision(profile: dict[str, Any], d: str) -> dict[str, Any]:
    p = copy.deepcopy(profile)
    p["decision_ref"] = d
    return p


class Plane:
    """One loaded plane with its rev-2 reset posture (all untimed)."""

    def __init__(self, size: int, info: dict[str, Any], fixtures: Path, bundle: Path, manifests: ManifestStore,
                 registry: Registry, profiles: dict[str, dict[str, Any]]):
        self.size, self.decision = size, info["decision"]
        self.snap = view.load_snapshot(fixtures / "planes" / f"N{size}", bundle / "target", allow_synthetic=True)
        self.n = view.get_decision(self.snap, self.decision)["binding"]["payload"]["basis_count"]   # builds the index
        self.rev2, self.rev3 = (with_decision(profiles[r], self.decision) for r in ("rev2", "rev3"))
        invs = resolve(self.rev2, self.snap, registry, manifests)
        self.rev2_bindings = {i.leaf: i.binding for i in invs}
        self.rev3_bindings = {i.leaf: i.binding for i in resolve(self.rev3, self.snap, registry, manifests)}
        dv = view.retrieve(self.snap, self.decision)
        self.rev2_verdicts = [evaluate(i, self.snap, manifests, dv) for i in invs]
        # main-14 §4.5: at every size the baseline verdicts must both be SUCCESS
        self.baseline = {v["binding"]["d"]: v["state"] for v in self.rev2_verdicts}
        self.baseline_ok = sorted(self.baseline.values()) == [SUCCESS, SUCCESS]
        self.t2 = self.rev2["requirements"][1]["parameters"]["assessment_time"]

    def reset(self, gw: Gateway) -> Consumer:
        c = Consumer()
        c.activate(self.rev2, self.rev2_bindings)
        for v in self.rev2_verdicts:
            c.admit(v, self.t2)
        gw.publish(c.card(self.t2))
        return c


def cycle(p: Plane, gw: Gateway, manifests: ManifestStore, registry: Registry, deadline_s: float,
          max_wait_s: float) -> dict[str, Any]:
    c = p.reset(gw)
    prof_id, rev = p.rev3["profile"], p.rev3["revision"]
    got: dict[str, Any] = {}
    ready = threading.Event()

    def reader():
        ready.set()
        code, body = gw.read(prof_id, revision=rev, wait_s=deadline_s)
        got["deadline_met"] = code == 200
        if code != 200:                                    # the gateway has recorded the timeout; keep waiting
            code, body = gw.read(prof_id, revision=rev, wait_s=max_wait_s - deadline_s)
        got["t1"] = time.monotonic_ns()
        got["code"], got["body"] = code, body

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    ready.wait()
    t0 = time.monotonic_ns()
    out = monitor.reassess(c, p.rev3, p.snap, manifests, publish=gw.publish, registry=registry, rerun_unaffected=True)
    th.join(max_wait_s + 10)
    card = (got.get("body") or {}).get("card") or {}
    leaves = card.get("leaves") or {}
    obs = {"H": (leaves.get(H) or {}).get("state"), "A": (leaves.get(A) or {}).get("state"),
           "revision": card.get("profile_revision")}
    completed = got.get("code") == 200
    return {"t_assess_s": (got["t1"] - t0) / 1e9 if completed else None, "completed": completed,
            "deadline_met": bool(got.get("deadline_met")), "gateway": (got.get("body") or {}).get("gateway"),
            "observed": obs, "match": obs == {"H": SUCCESS, "A": FAIL, "revision": rev},
            "shared_view": out["shared_view"]}


def host_manifest(cfg: dict[str, Any], planes: list[Plane], pwexp_commit: str) -> dict[str, Any]:
    """R-SCL-8 (D-003: no Docker image; the host is recorded instead)."""
    import subprocess
    try:
        lscpu = subprocess.run(["lscpu"], capture_output=True, text=True).stdout
        info = dict(l.split(":", 1) for l in lscpu.splitlines() if ":" in l)
        cpu = " ".join(v for v in (info.get(k, "").strip() for k in ("Vendor ID", "Model name")) if v not in ("", "-"))
    except OSError:
        cpu = ""
    try:
        mem = next(l.split(":", 1)[1].strip() for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemTotal"))
    except (OSError, StopIteration):
        mem = ""
    clock = time.get_clock_info("monotonic")
    return {"hardware": {"machine": platform.machine(), "cpu": cpu or platform.processor(), "cpus": os.cpu_count(),
                         "memory": mem},
            "os": platform.platform(), "python": sys.version.split()[0], "uv_lock_sha256": sha256_file(paths.root() / "uv.lock"),
            "pwexp_commit": pwexp_commit,
            "clock": {"source": "time.monotonic_ns", "implementation": clock.implementation, "resolution": clock.resolution},
            "warmups": cfg["warmups"], "blocks": cfg["blocks"], "seed": cfg["seed"], "deadline_s": cfg["deadline_s"],
            "max_wait_s": cfg["max_wait_s"], "sizes": {str(p.size): p.n for p in planes},
            "baseline": {str(p.size): p.baseline for p in planes},
            "load_average_before": list(os.getloadavg())}


def stats(records: list[dict[str, Any]], deadline_s: float) -> dict[str, Any]:
    out = {}
    for size in sorted({r["size"] for r in records}):
        rs = [r for r in records if r["size"] == size]
        xs = [r["t_assess_s"] for r in rs if r["t_assess_s"] is not None]
        out[str(size)] = {
            "N": rs[0]["N"], "observations": len(rs), "completed": len(xs),
            "slowest_s": max(xs) if xs else None,
            "exceedances": sum(1 for r in rs if r["t_assess_s"] is None or r["t_assess_s"] > deadline_s),
            "late": sum(1 for r in rs if r["completed"] and not r["deadline_met"]),
            "timeouts": sum(1 for r in rs if not r["completed"]), "mismatches": sum(1 for r in rs if not r["match"])}
    return out


def headline(st: dict[str, Any], deadline_s: float) -> dict[str, Any]:
    """The single result (D-015): T_max, the slowest completed update of the campaign, against the budget.
    An update that never completed counts as over the budget and makes T_max unknown."""
    done = [v for v in st.values() if v["slowest_s"] is not None]
    worst = max(done, key=lambda v: v["slowest_s"]) if done else None
    incomplete = sum(v["timeouts"] for v in st.values())
    wrong = sum(v.get("mismatches", 0) for v in st.values())
    return {"worst_s": worst["slowest_s"] if worst and not incomplete else None,
            "worst_N": worst["N"] if worst else None, "total": sum(v["observations"] for v in st.values()),
            "over": sum(v["exceedances"] for v in st.values()), "incomplete": incomplete, "mismatches": wrong,
            "budget_s": deadline_s,
            # all correct completions within the budget (main-14 §4.5): a wrong or outdated posture never counts
            "within": bool(done) and not incomplete and not wrong and worst["slowest_s"] <= deadline_s}


def sentence(st: dict[str, Any], deadline_s: float) -> str:
    """The result sentence (R-REP-5 as amended by D-015). Never 'real-time' or 'guaranteed'."""
    h = headline(st, deadline_s)
    if h["incomplete"]:
        return (f"{h['over']} of {h['total']} timed updates exceeded the {deadline_s:g} s budget; "
                f"{h['incomplete']} did not complete within the waiting limit.")
    if h["mismatches"]:
        return (f"{h['mismatches']} of {h['total']} timed updates returned an incorrect posture; "
                f"the slowest took {h['worst_s']:.2f} s.")
    if h["within"]:
        return (f"Every one of the {h['total']} timed updates reached the gateway within the {deadline_s:g} s budget; "
                f"the slowest took {h['worst_s']:.2f} s.")
    return f"{h['over']} of {h['total']} timed updates exceeded the {deadline_s:g} s budget; the slowest took {h['worst_s']:.2f} s."


def write(out: Path, result: dict[str, Any], mark: str) -> dict[str, Path]:
    import json
    out.mkdir(parents=True, exist_ok=True)
    files = {"timing_records": out / "timing_records.jsonl", "scale_stats": out / "scale_stats.json",
             "run_manifest": out / "run_manifest.json"}
    files["timing_records"].write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in result["records"]))
    files["scale_stats"].write_text(json.dumps({"mark": mark, "stats": result["stats"], "sentence": result["sentence"],
                                                "headline": result["headline"],
                                                "gateway_timeouts": result["gateway_timeouts"]}, indent=2, sort_keys=True) + "\n")
    files["run_manifest"].write_text(json.dumps({"mark": mark, **result["manifest"]}, indent=2, sort_keys=True) + "\n")
    return files


def run(fixtures: Path, bundle: Path, cfg: dict[str, Any], stamp: dict[str, Any], progress: Callable[[str], None] = print,
        blocks: int | None = None, warmups: int | None = None) -> dict[str, Any]:
    cfg = {**cfg, **({"blocks": blocks} if blocks is not None else {}), **({"warmups": warmups} if warmups is not None else {})}
    params = yaml.safe_load((fixtures / "parameters.json").read_text())
    profiles = {p.stem: yaml.safe_load(p.read_text()) for p in sorted((fixtures / "profiles").glob("*.yaml"))}
    manifests = ManifestStore(bundle / "protocol", fixtures / "manifests")
    registry = Registry()
    sizes = [int(n) for n in params["scale_target_sizes"]]
    planes = []
    for n in sizes:
        progress(f"loading plane N ≈ {n:,} (untimed)")
        planes.append(Plane(n, params["planes"][str(n)], fixtures, bundle, manifests, registry, profiles))
    manifest = host_manifest(cfg, planes, stamp.get("pwexp_commit", ""))
    rng = random.Random(int(cfg["seed"]))
    records, guard_calls = [], []
    with disabled_control() as guard, Gateway() as gw:
        for p in planes:
            for _ in range(int(cfg["warmups"])):
                cycle(p, gw, manifests, registry, float(cfg["deadline_s"]), float(cfg["max_wait_s"]))
            progress(f"warm-ups done for N = {p.n:,}")
        for b in range(int(cfg["blocks"])):
            order = planes[:]
            rng.shuffle(order)
            for pos, p in enumerate(order):
                r = cycle(p, gw, manifests, registry, float(cfg["deadline_s"]), float(cfg["max_wait_s"]))
                guard_calls.append(len(guard.calls))
                records.append({"kind": "timing", "block": b + 1, "position": pos + 1, "size": p.size, "N": p.n,
                                "decision": p.decision, **r, "guard_calls": len(guard.calls),
                                "binding": p.rev3_bindings, **stamp})
            if (b + 1) % 10 == 0 or b == 0:
                st = stats(records, float(cfg["deadline_s"]))
                progress(f"block {b + 1:3}/{cfg['blocks']}  " + "  ".join(
                    f"N={v['N']:,}: slowest {v['slowest_s']:.3f}s ({v['exceedances']} over)" for v in st.values()))
        gateway_timeouts = gw.timeouts()
    st = stats(records, float(cfg["deadline_s"]))
    return {"records": records, "stats": st, "manifest": manifest, "sentence": sentence(st, float(cfg["deadline_s"])),
            "headline": headline(st, float(cfg["deadline_s"])),
            "gateway_timeouts": len(gateway_timeouts), "guard_calls": guard_calls[-1] if guard_calls else 0,
            "expected_cycles": int(cfg["blocks"]) * len(planes)}
