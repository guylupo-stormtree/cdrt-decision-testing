"""Functional protocol (RQ1; main-14 §4.4; requirements A10 as narrowed by D-017).

One pass runs, on the frozen bundle and the fixtures, with the capture entry points disabled:

  main sequence   register conformance-check, activate rev 1; register coverage-composition, activate rev 2
                  (before: adequacy answered by the evidence of every captured decision together); activate rev 3,
                  which adds independent-check (after). Cards go to the gateway process through the TAIP posture
                  stub; while rev 3's adequacy verdict is pending the gateway must serve no green
  timeline        the composed coverage after each decision is admitted in capture order: the observed estate,
                  the newly admitted decision's share of it (rho, narrow or not), the composed state and gateway
  delayed         a rev-2 adequacy SUCCESS is held and released after the rev-3 verdict is admitted
  observation     every captured GREEN G-main decision on its own: conformance, its individual adequacy
                  (adequacy-check) and whether a gateway relying on it alone would proceed (not part of A_comp)

Expected states come from oracle/expectations.yaml; every judgement is also compared with the independent
oracle (oracle_check.py batch). Code fingerprints are taken before and after every registration and
requirement change. The pass is run `functional.replay_runs` times. A_comp holds only if the four conditions
C1-C4 hold in every run; replay agreement is reported beside it. Every record carries the lock stamp.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from pwexp.hashing import sha256_json

from .. import monitor, paths
from ..control_guard import disabled_control
from ..gateway import Gateway
from ..posture import Consumer, verdict_ref
from ..records import view
from ..records.manifests import ManifestStore
from ..registry import ENTRIES, Registry
from ..tests_registered.common import FAIL, SUCCESS
from .fingerprints import fingerprint
from .scheduler import DelayQueue

H, A = "release.effectiveness", "release.adequacy"
CONF, ADEQ = "conformance-check@1.0", "adequacy-check@1.0"
IDS = ["step1", "step2", "step3", "before", "after", "timeline", "delayed", "observation", "isolation"]
COMP = "coverage-composition@1.0"
CONDITIONS = {"C1": "Verdicts match the oracle before and after", "C2": "Second-module composition",
              "C3": "Gateway transition and delayed-result rejection", "C4": "No control re-execution"}


@dataclass
class Env:
    bundle: Path
    fixtures: Path
    work: Path
    params: dict[str, Any]
    profiles: dict[str, dict[str, Any]]
    manifests: ManifestStore
    snap: view.Snapshot
    expect: dict[str, Any]
    stamp: dict[str, Any]
    green: list[str]


def load_env(bundle: Path, fixtures: Path, work: Path, stamp: dict[str, Any], green: list[str]) -> Env:
    profiles = {p.stem: yaml.safe_load(p.read_text()) for p in sorted((fixtures / "profiles").glob("*.yaml"))}
    corpus_sha = json.loads((bundle / "BUNDLE.json").read_text())["corpus_sha256"]
    return Env(bundle, fixtures, work, json.loads((fixtures / "parameters.json").read_text()), profiles,
               ManifestStore(bundle / "protocol", fixtures / "manifests"),
               view.load_snapshot(bundle / "corpus", bundle / "target", corpus_sha),
               yaml.safe_load((paths.root() / "oracle" / "expectations.yaml").read_text()), stamp, list(green))


# ------------------------------------------------------------------ oracle
def adequacy_params(profile: dict[str, Any]) -> dict[str, Any] | None:
    return next((r["parameters"] for r in profile["requirements"] if r["test"] in (ADEQ, COMP)), None)


def _oracle_params(p: dict[str, Any]) -> dict[str, Any]:
    ref = p["manifest_ref"]
    keys = ("minimum_coverage", "validators", "max_age_seconds", "assessment_time", "relative_threshold", "context")
    return {"manifest": {"file": f"manifests/{ref['id']}.json", "sha256": ref["sha256"]}, **{k: p[k] for k in keys if k in p}}


def prefixes(env: Env) -> list[list[str]]:
    """The decision set after each admission, in capture order."""
    order = [d for d in env.params["capture_order"] if d in view.list_decisions(env.snap)]
    return [order[: i + 1] for i in range(len(order))]


def oracle_judgements(env: Env) -> dict[tuple, dict[str, Any]]:
    """One oracle process for every judgement the protocol makes."""
    main = env.params["selection"]["main"]
    decisions = list(dict.fromkeys([main, *env.green]))
    every = view.list_decisions(env.snap)
    keys: list[tuple] = [("H", d) for d in decisions] + [("A", main, r) for r in ("rev2", "rev3")] + \
        [("A1", d) for d in decisions] + [("P", i) for i in range(len(prefixes(env)))]

    def req(k: tuple) -> dict[str, Any]:
        if k[0] == "H":
            return {"kind": "conformance", "decision": k[1]}
        if k[0] == "A":
            return {"kind": "composition", "decisions": every, "current": main,
                    "params": _oracle_params(adequacy_params(env.profiles[k[2]]))}
        if k[0] == "A1":
            return {"kind": "adequacy", "decision": k[1], "params": _oracle_params(adequacy_params(env.profiles["obs2"]))}
        ds = prefixes(env)[k[1]]
        return {"kind": "composition", "decisions": ds, "current": ds[-1],
                "params": _oracle_params(adequacy_params(env.profiles["rev2"]))}
    reqs = [req(k) for k in keys]
    f = env.work / "oracle-requests.json"
    f.write_text(json.dumps(reqs, indent=2, sort_keys=True))
    p = subprocess.run([sys.executable, str(paths.root() / "oracle" / "oracle_check.py"), "batch", str(env.bundle), str(f)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"oracle failed: {p.stderr.strip()[-300:]}")
    return dict(zip(keys, json.loads(p.stdout)))


def agrees(v: dict[str, Any], o: dict[str, Any] | None) -> list[str]:
    """Differences between a runtime verdict and the oracle's judgement (empty when they agree)."""
    if o is None:
        return ["no oracle judgement"]
    m, out = v.get("measurements") or {}, []
    if v.get("state") != o["state"]:
        out.append(f"state {v.get('state')} vs oracle {o['state']}")
    if "coverage" in o and f"{m.get('coverage_numerator')}/{m.get('coverage_denominator')}" != o["coverage"]:
        out.append(f"coverage {m.get('coverage_numerator')}/{m.get('coverage_denominator')} vs oracle {o['coverage']}")
    if "missing_validators" in o:
        counts: dict[str, int] = {}
        for vs in o["missing_validators"].values():
            for x in vs:
                counts[x] = counts.get(x, 0) + 1
        if {k: n for k, n in (m.get("missing_by_validator") or {}).items() if n} != counts:
            out.append(f"missing validators {m.get('missing_by_validator')} vs oracle {counts}")
    if "max_age_seconds" in o:
        a, b = m.get("max_age_seconds"), o["max_age_seconds"]
        if (a is None) != (b is None) or (a is not None and abs(a - b) > 0.002):
            out.append(f"age {a} vs oracle {b}")
    for k in ("covered", "uncovered", "observed_estate", "drift", "eligible", "excluded", "rho", "narrow", "current"):
        if "observed_estate" in o and m.get(k) != o.get(k):  # a composed judgement: the sets must agree exactly
            out.append(f"{k} {m.get(k)} vs oracle {o[k]}")
    return out


# ------------------------------------------------------------------ one pass
def summary(v: dict[str, Any] | None) -> dict[str, Any] | None:
    if v is None:
        return None
    return {"state": v["state"], "execution_status": v["execution_status"], "requirement": v.get("requirement"),
            "measurements": v["measurements"], "evidence_refs": v.get("evidence_refs"), "reasons": v["reasons"],
            "valid_until": v["valid_until"], "verdict_ref": verdict_ref(v)}


def leaves(card: dict[str, Any]) -> dict[str, Any]:
    return {"leaves": {d: {"state": l["state"], "verdict_ref": l["verdict_ref"]} for d, l in card["leaves"].items()},
            "taip_root": card["taip"]["root"], "taip_branches": {b: x["state"] for b, x in card["taip"]["branches"].items()},
            "gateway_decision": card["gateway_decision"], "complete": card["complete"]}


def with_decision(profile: dict[str, Any], d: str) -> dict[str, Any]:
    p = copy.deepcopy(profile)
    p["decision_ref"] = d
    return p


class Pass:
    def __init__(self, env: Env, gateway: Gateway, guard, oracle: dict[tuple, dict[str, Any]], progress: Callable[[str], None]):
        self.env, self.gw, self.guard, self.oracle, self.progress = env, gateway, guard, oracle, progress
        self.records: list[dict[str, Any]] = []
        self.fingerprints: list[tuple[str, str]] = [("start", fingerprint())]
        self.guard_counts: list[tuple[str, int]] = []
        self.withdrawn: list[dict[str, Any]] = []
        self.main = env.params["selection"]["main"]
        self.captured = {d: view.get_decision(env.snap, d)["binding"]["record_hash"] for d in view.list_decisions(env.snap)}
        self.regs: dict[str, tuple[Registry, list[dict[str, Any]]]] = {}
        self.cards: dict[str, dict[str, Any]] = {}

    def registry(self, name: str, refs: list[str]) -> Registry:
        """Registration through the declaration schema: a registry file holding exactly these approved entries."""
        doc = yaml.safe_load(ENTRIES.read_text())
        doc["entries"] = [e for e in doc["entries"] if f"{e['id']}@{e['version']}" in refs]
        f = self.env.work / f"registry-{name}.yaml"
        f.write_text(yaml.safe_dump(doc, sort_keys=True))
        reg = Registry(f)
        self.regs[name] = (reg, doc["entries"])
        self.fingerprints.append((f"registered {name}", fingerprint()))
        return reg

    def cycle(self, label: str, consumer: Consumer, profile: dict[str, Any], registry: Registry,
              hold=None, publish=None) -> dict[str, Any]:
        self.fingerprints.append((f"{label}: before", fingerprint()))
        out = monitor.reassess(consumer, profile, self.env.snap, self.env.manifests, publish=publish, hold=hold,
                               registry=registry)
        self.fingerprints.append((f"{label}: after", fingerprint()))
        self.guard_counts.append((label, len(self.guard.calls)))
        out["by_leaf"] = {v["binding"]["d"]: v for v in out["verdicts"]}
        return out

    def t(self, profile: dict[str, Any]) -> str:
        return (adequacy_params(profile) or {}).get("assessment_time") or ""

    def record(self, kind: str, id: str, expected: Any, observed: Any, match: bool | None, binding: Any,
               notes: list[str] | None = None, **extra: Any) -> dict[str, Any]:
        r = {"kind": kind, "id": id, "executed": True, "expected": expected, "observed": observed, "match": match,
             "notes": notes or [], "binding": binding, **extra, **self.env.stamp}
        self.records.append(r)
        return r

    def guarded(self, id: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as e:  # noqa: BLE001  a crash is recorded; the lab then cannot pass
            self.records.append({"kind": "error", "id": id, "executed": False, "error": f"{type(e).__name__}: {e}",
                                 "binding": None, **self.env.stamp})
            self.progress(f"✗ {id} did not run: {type(e).__name__}: {e}")

    def lane(self, label: str, card: dict[str, Any]) -> None:
        """One row of the verdict timeline: CDRT leaves, the TAIP root and the gateway."""
        h, a = card["leaves"].get(H), card["leaves"].get(A)
        fmt = lambda l: "—" if l is None else (l["state"] or "pending")  # noqa: E731
        self.progress(f"{label:6} │ H {fmt(h):13} │ A {fmt(a):13} │ TAIP {card['taip']['root']:12} │ "
                      f"gateway {card['gateway_decision']}")

    def judge(self, id: str, prof_name: str, verdicts: dict[str, dict], card: dict[str, Any]) -> dict[str, Any]:
        """H and A of the main decision against expectations.yaml and the oracle, and the gateway decision."""
        exp = self.env.expect["cases"][id]
        notes = []
        for leaf, key in ((H, ("H", self.main)), (A, ("A", self.main, prof_name))):
            notes += [f"{'H' if leaf == H else 'A'}: {x}" for x in agrees(verdicts[leaf], self.oracle.get(key))]
        obs = {"H": verdicts[H]["state"], "A": verdicts[A]["state"], "gateway": card["gateway_decision"]}
        match = obs == {k: exp[k] for k in ("H", "A", "gateway")} and not notes
        if obs != {k: exp[k] for k in ("H", "A", "gateway")}:
            notes.append(f"observed {obs} vs expected {exp}")
        return self.record("case", id, {k: exp[k] for k in ("H", "A", "gateway")}, obs, match,
                           {d: v["binding"] for d, v in sorted(verdicts.items())}, notes, decision=self.main,
                           profile=prof_name, oracle_agrees=not any(n.startswith(("H:", "A:")) for n in notes),
                           h_H_ok=all(v["binding"]["h_H"] == self.captured[self.main] for v in verdicts.values()),
                           verdicts={d: summary(v) for d, v in sorted(verdicts.items())}, card=leaves(card))

    # ---------------------------------------------------------------- main sequence
    def main_sequence(self) -> None:
        P, prof_id = self.env.profiles, self.env.profiles["rev1"]["profile"]

        def publish(card: dict[str, Any]) -> None:
            self.gw.publish(card)
            if not card["complete"]:                       # support withdrawn, new verdict pending
                code, _ = self.gw.read(prof_id, revision=card["profile_revision"], wait_s=0.2)
                self.withdrawn.append({"revision": card["profile_revision"], "card": leaves(card),
                                       "revision_read": code, "gateway_now": self.gw.read(prof_id)[1]["gateway"]})

        def gateway(rev: int) -> str:
            code, body = self.gw.read(prof_id, revision=rev, wait_s=10)
            return body["gateway"] if code == 200 else f"timeout ({code})"

        c = Consumer()
        o1 = self.cycle("step 1 (rev 1)", c, P["rev1"], self.registry("step1", [CONF]), publish=publish)
        c1, g1 = c.card(), gateway(P["rev1"]["revision"])
        self.lane("rev 1", c1)
        self.record("step", "step1", {"H": SUCCESS, "taip": "pass", "gateway": "proceed"},
                    {"H": c1["leaves"][H]["state"], "taip": c1["taip"]["root"], "gateway": g1},
                    c1["leaves"][H]["state"] == SUCCESS and c1["taip"]["root"] == "pass" and g1 == "proceed",
                    {d: v["binding"] for d, v in o1["by_leaf"].items()}, card=leaves(c1))

        o2 = self.cycle("step 2 (rev 2)", c, P["rev2"], self.registry("step2", [CONF, COMP]), publish=publish)
        c2, g2 = c.card(self.t(P["rev2"])), gateway(P["rev2"]["revision"])
        self.lane("rev 2", c2)
        h_kept = c2["leaves"][H]["verdict_ref"] == c1["leaves"][H]["verdict_ref"] and H not in o2["affected"]
        e1, e2 = self.regs["step1"][1], self.regs["step2"][1]
        only_registration = e2[: len(e1)] == e1 and [f"{e['id']}@{e['version']}" for e in e2[len(e1):]] == [COMP]
        r1, r2 = P["rev1"], P["rev2"]
        only_profile_edit = r2["requirements"][: len(r1["requirements"])] == r1["requirements"] and \
            {k: v for k, v in r1.items() if k not in ("revision", "label", "requirements")} == \
            {k: v for k, v in r2.items() if k not in ("revision", "label", "requirements")}
        self.record("step", "step2", {"H": "unchanged (SUCCESS)", "A": SUCCESS, "taip": "pass", "gateway": "proceed"},
                    {"H_kept": h_kept, "A": c2["leaves"][A]["state"], "taip": c2["taip"]["root"], "gateway": g2},
                    h_kept and c2["leaves"][A]["state"] == SUCCESS and c2["taip"]["root"] == "pass" and g2 == "proceed",
                    {d: v["binding"] for d, v in o2["by_leaf"].items()}, card=leaves(c2),
                    composition={"only_registration": only_registration, "only_profile_edit": only_profile_edit})
        self.judge("before", "rev2", {H: o1["by_leaf"][H], A: o2["by_leaf"][A]}, c2)

        o3 = self.cycle("step 3 (rev 3)", c, P["rev3"], self.regs["step2"][0], publish=publish)
        c3, g3 = c.card(self.t(P["rev3"])), gateway(P["rev3"]["revision"])
        self.lane("rev 3", c3)
        w = next((x for x in self.withdrawn if x["revision"] == P["rev3"]["revision"]), None)
        a3 = o3["by_leaf"][A]
        m3 = a3["measurements"]
        withdrawn = bool(w) and w["card"]["leaves"][A]["verdict_ref"] is None and \
            w["card"]["leaves"][H]["verdict_ref"] == c1["leaves"][H]["verdict_ref"]
        no_green = bool(w) and w["gateway_now"] == "no-green" and w["revision_read"] == 504
        missing_all = m3.get("coverage_numerator", 0) > 0 and \
            (m3.get("missing_by_validator") or {}).get("independent-check") == m3.get("coverage_numerator")
        h_kept3 = c3["leaves"][H]["verdict_ref"] == c1["leaves"][H]["verdict_ref"] and o3["affected"] == [A]
        in_history = any(x["verdict_ref"] == c2["leaves"][A]["verdict_ref"] and "withdrawn" in x["reason"] for x in c3["history"])
        self.record("step", "step3", {"H": "unchanged", "A_withdrawn_first": True, "gateway_while_pending": "no-green",
                                      "A": FAIL, "missing": "independent-check for every covered target",
                                      "taip": "fail", "gateway": "hold"},
                    {"H_kept": h_kept3, "A_withdrawn_first": withdrawn, "old_A_in_history": in_history,
                     "gateway_while_pending": w and w["gateway_now"], "A": c3["leaves"][A]["state"],
                     "missing_by_validator": m3.get("missing_by_validator"), "covered": m3.get("coverage_numerator"),
                     "taip": c3["taip"]["root"], "gateway": g3},
                    h_kept3 and withdrawn and in_history and no_green and missing_all and c3["leaves"][A]["state"] == FAIL
                    and c3["taip"]["root"] == "fail" and g3 == "hold",
                    {d: v["binding"] for d, v in o3["by_leaf"].items()}, card=leaves(c3), withdrawn_card=w)
        self.judge("after", "rev3", {H: o1["by_leaf"][H], A: a3}, c3)
        self.cards = {"step1": c1, "step2": c2, "step3": c3}

    # ---------------------------------------------------------------- delayed result
    def delayed(self) -> None:
        P = self.env.profiles
        reg1, reg2 = self.regs["step1"][0], self.regs["step2"][0]
        t3 = self.t(P["rev3"])
        c = Consumer()
        q = DelayQueue(c)
        self.cycle("delayed rev 1", c, P["rev1"], reg1)
        h_ref = c.card()["leaves"][H]["verdict_ref"]
        self.cycle("delayed rev 2 (A held)", c, P["rev2"], reg2, hold=q.hold_leaf(A))
        o3 = self.cycle("delayed rev 3", c, P["rev3"], reg2)
        before = c.card(t3)
        old, ok, why = q.release(0, t3)
        after = c.card(t3)
        ref = verdict_ref(old)
        stored = any(x["verdict_ref"] == ref and x["reason"].startswith("rejected") for x in after["history"])
        unchanged = leaves(before) == leaves(after)
        obs = {"old_state": old["state"], "old_admitted": ok, "reason": why, "in_history": stored,
               "posture_unchanged": unchanged, "H_unchanged": after["leaves"][H]["verdict_ref"] == h_ref,
               "gateway_after_release": after["gateway_decision"]}
        self.record("delayed", "delayed", self.env.expect["delayed"]["expect"], obs,
                    old["state"] == SUCCESS and not ok and stored and unchanged and after["gateway_decision"] == "hold",
                    {"old": old["binding"], "new": o3["by_leaf"][A]["binding"]}, card=leaves(after))

    # ---------------------------------------------------------------- timeline: composed coverage per admission
    def timeline(self) -> None:
        reg = self.regs["step2"][0]
        rows, bind, diffs = [], {}, []
        for i, ds in enumerate(prefixes(self.env)):
            prof = with_decision(self.env.profiles["rev2"], ds[-1])
            for r in prof["requirements"]:
                if r["test"] == COMP:
                    r["parameters"]["decision_set"] = list(ds)
            c = Consumer()
            out = self.cycle(f"timeline {i + 1} ({ds[-1]})", c, prof, reg)
            card = c.card(self.t(prof))
            v = out["by_leaf"][A]
            m = v["measurements"]
            d = [f"after {ds[-1]}: {x}" for x in agrees(v, self.oracle.get(("P", i)))]
            diffs += d
            rows.append({"admitted": ds[-1], "decisions": len(ds), "observed_estate": m.get("observed_estate_size"),
                         "covered": f"{m.get('coverage_numerator')}/{m.get('coverage_denominator')}",
                         "rho_admitted": (m.get("current") or {}).get("rho"), "narrow_admitted": (m.get("current") or {}).get("narrow"),
                         "eligible_admitted": (m.get("current") or {}).get("eligible"), "drift": m.get("drift"),
                         "composed": v["state"], "gateway": card["gateway_decision"], "oracle_agrees": not d})
            bind[ds[-1]] = v["binding"]
        self.record("timeline", "timeline", {"oracle": "exact agreement after every admission"}, rows,
                    bool(rows) and not diffs, bind, diffs)

    # ---------------------------------------------------------------- observation: every green decision on its own
    def observation(self) -> None:
        reg = self.registry("observation", [CONF, ADEQ])
        final = (self.cards.get("step2") or {})
        comp = next((r for r in self.records if r["id"] == "before"), {})
        m = ((comp.get("verdicts") or {}).get(A) or {}).get("measurements") or {}
        obs, bind = {}, {}
        for d in self.env.green:
            diffs = []
            c = Consumer()
            out = self.cycle(f"observation ({d})", c, with_decision(self.env.profiles["obs2"], d), reg)
            card = c.card(self.t(self.env.profiles["obs2"]))
            diffs += agrees(out["by_leaf"][H], self.oracle.get(("H", d)))
            diffs += [f"A: {x}" for x in agrees(out["by_leaf"][A], self.oracle.get(("A1", d)))]
            a = out["by_leaf"][A]["measurements"]
            narrow = d in (m.get("narrow") or [])
            alone = "hold" if narrow and card["gateway_decision"] == "proceed" else card["gateway_decision"]
            obs[d] = {"H": card["leaves"][H]["state"], "A_alone": card["leaves"][A]["state"],
                      "coverage_alone": f"{a.get('coverage_numerator')}/{a.get('coverage_denominator')}",
                      "rho": (m.get("rho") or {}).get(d), "narrow": narrow, "gateway_alone": alone,
                      "eligible": d in (m.get("eligible") or []), "excluded": (m.get("excluded") or {}).get(d),
                      "oracle_agrees": not diffs, "notes": diffs}
            bind[d] = {x: v["binding"] for x, v in out["by_leaf"].items()}
        self.record("observation", "observation", self.env.expect["observation"]["expect"], obs,
                    all(v["oracle_agrees"] for v in obs.values()), bind,
                    [] if obs else ["no GREEN G-main decision was captured"],
                    composed={"state": final.get("leaves", {}).get(A, {}).get("state"), "gateway": final.get("gateway_decision"),
                              "covered": f"{m.get('coverage_numerator')}/{m.get('coverage_denominator')}",
                              "observed_estate": m.get("observed_estate_size")})

    def run(self) -> list[dict[str, Any]]:
        import pwexp.stages.stage1_acquire as stage1
        from ..control_guard import ENTRY_POINTS
        armed = all(getattr(getattr(stage1, n), "__qualname__", "").startswith("Guard._stub") for n in ENTRY_POINTS)
        for id, fn in (("main sequence", self.main_sequence), ("timeline", self.timeline), ("delayed", self.delayed),
                       ("observation", self.observation)):
            self.guarded(id, fn)
        fps = {fp for _, fp in self.fingerprints}
        calls = len(self.guard.calls)
        self.record("isolation", "isolation", {"guard_calls": 0, "fingerprints": "all equal"},
                    {"guard_armed": armed, "guard_calls": calls, "entry_points": list(ENTRY_POINTS),
                     "cycles": len(self.guard_counts), "fingerprints_taken": len(self.fingerprints),
                     "distinct_fingerprints": len(fps)},
                    armed and calls == 0 and all(n == 0 for _, n in self.guard_counts) and len(fps) == 1, None,
                    fingerprint=sorted(fps)[0] if len(fps) == 1 else sorted(fps))
        return self.records


def one_pass(env: Env, oracle: dict[tuple, dict[str, Any]], progress: Callable[[str], None]) -> list[dict[str, Any]]:
    with disabled_control() as guard, Gateway() as gw:
        return Pass(env, gw, guard, oracle, progress).run()


# ------------------------------------------------------------------ acceptance (main-14 §4.4)
def semantic(records: list[dict[str, Any]]) -> str:
    """Request ids and elapsed times are excluded; the records hold neither."""
    return sha256_json(records)


def conditions(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by = {r["id"]: r for r in records}
    ok = lambda i: bool(by.get(i, {}).get("match"))  # noqa: E731
    comp = (by.get("step2") or {}).get("composition") or {}
    iso = (by.get("isolation") or {}).get("observed") or {}
    items = {
        "C1": [("before", ok("before") and by["before"]["oracle_agrees"]), ("after", ok("after") and by["after"]["oracle_agrees"]),
               ("composed coverage after every admission", ok("timeline"))],
        "C2": [("only registration", bool(comp.get("only_registration"))), ("only a profile edit", bool(comp.get("only_profile_edit"))),
               ("fingerprints unchanged", iso.get("distinct_fingerprints") == 1)],
        "C3": [("step 1 proceed", ok("step1")), ("step 2 proceed", ok("step2")), ("step 3 no green then hold", ok("step3")),
               ("delayed success rejected", ok("delayed"))],
        "C4": [("guard counted no call", iso.get("guard_calls") == 0 and bool(iso.get("guard_armed"))),
               ("fingerprints unchanged", iso.get("distinct_fingerprints") == 1)],
    }
    return {k: {"row": CONDITIONS[k], "passes": all(v for _, v in xs), "failing": [n for n, v in xs if not v],
                "checked": [n for n, _ in xs]} for k, xs in items.items()}


def acceptance(runs: list[list[dict[str, Any]]], digests: list[str]) -> dict[str, Any]:
    per_run = [conditions(r) for r in runs]
    merged = {k: {**per_run[0][k], "passes": all(pr[k]["passes"] for pr in per_run),
                  "failing": sorted({f for pr in per_run for f in pr[k]["failing"]})} for k in CONDITIONS}
    replay = len(digests) >= 2 and len(set(digests)) == 1
    a_comp = all(v["passes"] for v in merged.values())
    return {"acceptance": merged, "A_comp": a_comp, "runs": len(runs), "replay_agrees": replay,
            "RQ1_supported": a_comp and replay}


def run_protocol(env: Env, replay_runs: int, progress: Callable[[str], None] = print) -> dict[str, Any]:
    oracle = oracle_judgements(env)
    runs, digests = [], []
    for i in range(replay_runs):
        progress(f"functional pass {i + 1} of {replay_runs}")
        recs = one_pass(env, oracle, progress if i == 0 else (lambda m: None))
        runs.append(recs)
        digests.append(semantic(recs))
    records = runs[0]
    acc = acceptance(runs, digests)
    records.append({"kind": "replay", "id": "replay", "executed": True, "expected": env.expect["replay"],
                    "observed": digests, "match": acc["replay_agrees"], "binding": None, **env.stamp})
    missing = [i for i in IDS if not any(r["id"] == i and r.get("executed") for r in records)]
    return {"records": records, "acceptance": acc, "missing": missing, "digests": digests, "oracle": oracle}
