"""Functional protocol (RQ1; requirements A10, R-ISO-1 … R-ISO-3, R-LOCK-4).

One pass runs, on the frozen bundle and the fixtures:

  main sequence   register conformance-check, activate rev 1; register adequacy-check, activate rev 2;
                  activate rev 3. Cards go to the gateway process; while rev 3's A verdict is pending the
                  gateway must serve no green
  cases F1-F9     F1/F2 from the main sequence, F6 from interleaving I1, the others each on a fresh consumer
  I1, I2          delayed rev-2 verdicts released after / before the rev-3 verdict exists (scheduler.py)
  B1-B10          derived copies (B1-B3), assessment times (B4), mutated bindings (B5-B10)

Expected states come from oracle/expectations.yaml; every authentic judgement is also compared with the
independent oracle (oracle_check.py batch, a separate process that reads the bundle directly). The whole
pass runs with the capture entry points disabled (control_guard) and code fingerprints taken before and
after every registration and requirement change. The pass is run `functional.replay_runs` times and the
semantic content of the records must be identical (R-ISO-3). Every record carries the lock stamp.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

import yaml

from pwexp.hashing import sha256_json

from .. import monitor, paths
from ..control_guard import disabled_control
from ..gateway import Gateway
from ..posture import Consumer, aggregate, verdict_ref
from ..records import view
from ..records.assessments import BASE, assessments
from ..records.manifests import ManifestStore
from ..registry import ENTRIES, Registry
from ..resolver import resolve
from ..tests_registered.common import FAIL, INCONCLUSIVE, SUCCESS, parse_utc
from .fingerprints import fingerprint
from .scheduler import DelayQueue

H, A = "release.effectiveness", "release.adequacy"
CONF, ADEQ = "conformance-check@1.0", "adequacy-check@1.0"
ISO = "%Y-%m-%dT%H:%M:%S.%fZ"
IDS = ["step1", "step2", "step3", *[f"F{i}" for i in range(1, 10)], "I1", "I2", *[f"B{i}" for i in range(1, 11)],
       "isolation"]


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
    f9: list[str]


def load_env(bundle: Path, fixtures: Path, work: Path, stamp: dict[str, Any], f9: list[str]) -> Env:
    profiles = {p.stem: yaml.safe_load(p.read_text()) for p in sorted((fixtures / "profiles").glob("*.yaml"))}
    corpus_sha = json.loads((bundle / "BUNDLE.json").read_text())["corpus_sha256"]
    return Env(bundle, fixtures, work, json.loads((fixtures / "parameters.json").read_text()), profiles,
               ManifestStore(bundle / "protocol", fixtures / "manifests"),
               view.load_snapshot(bundle / "corpus", bundle / "target", corpus_sha),
               yaml.safe_load((paths.root() / "oracle" / "expectations.yaml").read_text()), stamp, f9)


# ------------------------------------------------------------------ oracle
def _oracle_params(p: dict[str, Any]) -> dict[str, Any]:
    ref = p["manifest_ref"]
    return {"manifest": {"file": f"manifests/{ref['id']}.json", "sha256": ref["sha256"]},
            **{k: p[k] for k in ("minimum_coverage", "validators", "max_age_seconds", "assessment_time")}}


def adequacy_params(profile: dict[str, Any]) -> dict[str, Any] | None:
    return next((r["parameters"] for r in profile["requirements"] if r["test"] == ADEQ), None)


def oracle_judgements(env: Env) -> dict[tuple, dict[str, Any]]:
    """One oracle process for every authentic (decision, requirement) the protocol judges."""
    sel = env.params["selection"]
    keys: list[tuple] = [("H", d) for d in dict.fromkeys([sel["main"], sel["strict"], sel["pipeline"], *env.f9])]
    keys += [("A", sel["main"], r) for r in ("rev2", "rev3", "rev3b")] + [("A", sel["strict"], r) for r in ("rev2", "rev3")]
    keys += [("A", sel["pipeline"], "rev3")] + [("A", d, r) for d in env.f9 for r in ("rev2", "rev3")]
    reqs = [{"kind": "conformance", "decision": k[1]} if k[0] == "H" else
            {"kind": "adequacy", "decision": k[1], "params": _oracle_params(adequacy_params(env.profiles[k[2]]))}
            for k in keys]
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
    return out


# ------------------------------------------------------------------ one pass
def summary(v: dict[str, Any] | None) -> dict[str, Any] | None:
    if v is None:
        return None
    return {"state": v["state"], "execution_status": v["execution_status"], "measurements": v["measurements"],
            "reasons": v["reasons"], "valid_until": v["valid_until"], "verdict_ref": verdict_ref(v)}


def leaves(card: dict[str, Any]) -> dict[str, Any]:
    return {"leaves": {d: {"state": l["state"], "verdict_ref": l["verdict_ref"]} for d, l in card["leaves"].items()},
            "aggregate": card["aggregate"], "complete": card["complete"]}


def with_decision(profile: dict[str, Any], d: str, **adequacy: Any) -> dict[str, Any]:
    p = copy.deepcopy(profile)
    p["decision_ref"] = d
    for r in p["requirements"]:
        if r["test"] == ADEQ:
            r["parameters"].update(adequacy)
    return p


class Pass:
    def __init__(self, env: Env, gateway: Gateway, guard, oracle: dict[tuple, dict[str, Any]], progress: Callable[[str], None]):
        self.env, self.gw, self.guard, self.oracle, self.progress = env, gateway, guard, oracle, progress
        self.records: list[dict[str, Any]] = []
        self.fingerprints: list[tuple[str, str]] = [("start", fingerprint())]
        self.guard_counts: list[tuple[str, int]] = []
        self.withdrawn: list[dict[str, Any]] = []
        self.sel = env.params["selection"]
        self.captured = {d: view.get_decision(env.snap, d)["binding"]["record_hash"] for d in view.list_decisions(env.snap)}
        self.regs: dict[str, tuple[Registry, list[dict[str, Any]]]] = {}

    # helpers
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

    def cycle(self, label: str, consumer: Consumer, profile: dict[str, Any], snap: view.Snapshot, registry: Registry,
              hold=None, publish=None) -> dict[str, Any]:
        self.fingerprints.append((f"{label}: before", fingerprint()))
        out = monitor.reassess(consumer, profile, snap, self.env.manifests, publish=publish, hold=hold, registry=registry)
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

    def bindings(self, out: dict[str, Any]) -> dict[str, Any]:
        return {d: v["binding"] for d, v in sorted(out["by_leaf"].items())}

    def judge(self, id: str, decision: str, prof_name: str, out: dict[str, Any], card: dict[str, Any],
              oracle_h: bool = True, oracle_a: bool = True, extra_checks: dict[str, bool] | None = None,
              expected: dict[str, str] | None = None, attainable: bool = True) -> dict[str, Any]:
        """Leaf and root states against expectations.yaml and the oracle; `extra_checks` are the case's 'also'."""
        exp = expected or {k: self.env.expect["cases"][id][k] for k in ("H", "A")}
        h, a = card["leaves"].get(H, {}), card["leaves"].get(A, {})
        obs = {"H": h.get("state"), "A": a.get("state"), "aggregate": card["aggregate"]}
        notes, oracle_states = [], {}
        hv, av = out["by_leaf"].get(H), out["by_leaf"].get(A)
        for leaf, v, use, key in (("H", hv, oracle_h, ("H", decision)), ("A", av, oracle_a, ("A", decision, prof_name))):
            if use and v is not None:
                o = self.oracle.get(key)
                oracle_states[leaf] = o["state"] if o else None
                notes += [f"{leaf}: {x}" for x in agrees(v, o)]
        states_ok = obs["H"] == exp["H"] and obs["A"] == exp["A"]
        if not attainable:
            notes.append("not attainable: the Semgrep basis run did not scan every file of M_q; reported, not forced")
        exp_agg = aggregate({"H": {"state": exp["H"]}, "A": {"state": exp["A"]}})
        root_ok = obs["aggregate"] == aggregate({d: {"state": s} for d, s in (("H", obs["H"]), ("A", obs["A"]))})
        # AC3: the root against the oracle's leaves (the expectation stands in where the oracle cannot judge)
        root_vs_oracle = obs["aggregate"] == aggregate({d: {"state": oracle_states.get(d, exp[d])} for d in ("H", "A")})
        also = extra_checks or {}
        notes += [f"failed: {k}" for k, ok in also.items() if not ok]
        if not states_ok and attainable:
            notes.append(f"states {obs['H']}/{obs['A']} vs expected {exp['H']}/{exp['A']}")
        oracle_ok = not any(n.startswith(("H:", "A:")) for n in notes)
        match = oracle_ok and root_ok and all(also.values()) and (states_ok or not attainable)
        h_h = {d: v["binding"]["h_H"] for d, v in out["by_leaf"].items()}
        return self.record("case", id, {**exp, "aggregate": exp_agg}, obs, match, self.bindings(out), notes,
                           decision=decision, profile=prof_name, oracle=oracle_states, also=also,
                           root_vs_oracle=root_vs_oracle,
                           attainable=attainable, h_H_ok=all(x == self.captured.get(decision) for x in h_h.values()),
                           verdicts={d: summary(v) for d, v in sorted(out["by_leaf"].items())}, card=leaves(card))

    def guarded(self, id: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as e:  # noqa: BLE001  a crash is recorded; the lab then cannot pass
            self.records.append({"kind": "error", "id": id, "executed": False, "error": f"{type(e).__name__}: {e}",
                                 "binding": None, **self.env.stamp})
            self.progress(f"✗ {id} did not run: {type(e).__name__}: {e}")

    # ---------------------------------------------------------------- main sequence (A10.1)
    def main_sequence(self) -> None:
        env, P, main = self.env, self.env.profiles, self.sel["main"]
        prof_id = P["rev1"]["profile"]

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
        reg1 = self.registry("step1", [CONF])
        o1 = self.cycle("step 1 (rev 1)", c, P["rev1"], env.snap, reg1, publish=publish)
        c1, g1 = c.card(), gateway(P["rev1"]["revision"])
        self.lane("rev 1", c1, g1)
        self.record("step", "step1", {"H": SUCCESS, "aggregate": SUCCESS, "gateway": "proceed"},
                    {"H": c1["leaves"][H]["state"], "aggregate": c1["aggregate"], "gateway": g1},
                    c1["leaves"][H]["state"] == SUCCESS and c1["aggregate"] == SUCCESS and g1 == "proceed",
                    self.bindings(o1), card=leaves(c1), verdicts={d: summary(v) for d, v in o1["by_leaf"].items()})

        reg2 = self.registry("step2", [CONF, ADEQ])
        o2 = self.cycle("step 2 (rev 2)", c, P["rev2"], env.snap, reg2, publish=publish)
        c2, g2 = c.card(P["rev2"]["requirements"][1]["parameters"]["assessment_time"]), gateway(P["rev2"]["revision"])
        self.lane("rev 2", c2, g2)
        h_kept = c2["leaves"][H]["verdict_ref"] == c1["leaves"][H]["verdict_ref"] and H not in o2["affected"]
        e1, e2 = self.regs["step1"][1], self.regs["step2"][1]
        only_registration = e2[: len(e1)] == e1 and [f"{e['id']}@{e['version']}" for e in e2[len(e1):]] == [ADEQ]
        r1, r2 = P["rev1"], P["rev2"]
        only_profile_edit = r2["requirements"][: len(r1["requirements"])] == r1["requirements"] and \
            {k: v for k, v in r1.items() if k not in ("revision", "label", "requirements")} == \
            {k: v for k, v in r2.items() if k not in ("revision", "label", "requirements")}
        self.record("step", "step2", {"H": "unchanged (SUCCESS)", "A": SUCCESS, "aggregate": SUCCESS, "gateway": "proceed"},
                    {"H": c2["leaves"][H]["state"], "H_kept": h_kept, "A": c2["leaves"][A]["state"],
                     "aggregate": c2["aggregate"], "gateway": g2},
                    h_kept and c2["leaves"][A]["state"] == SUCCESS and c2["aggregate"] == SUCCESS and g2 == "proceed",
                    self.bindings(o2), card=leaves(c2), verdicts={d: summary(v) for d, v in o2["by_leaf"].items()},
                    composition={"only_registration": only_registration, "only_profile_edit": only_profile_edit})
        self.judge("F1", main, "rev2", {"by_leaf": {H: o1["by_leaf"][H], **o2["by_leaf"]}}, c2,
                   extra_checks={"both tests use the shared interfaces (same snapshot, binding record, record and "
                                 "invocation contracts)": all(o1["by_leaf"][H]["binding"][k] == o2["by_leaf"][A]["binding"][k]
                                                              for k in ("s", "h_H", "v_E", "v_c"))})

        o3 = self.cycle("step 3 (rev 3)", c, P["rev3"], env.snap, reg2, publish=publish)
        c3, g3 = c.card(self.t(P["rev3"])), gateway(P["rev3"]["revision"])
        self.lane("rev 3", c3, g3)
        w = next((x for x in self.withdrawn if x["revision"] == P["rev3"]["revision"]), None)
        a3 = o3["by_leaf"].get(A) or {}
        m3 = a3.get("measurements") or {}
        withdrawn = bool(w) and w["card"]["leaves"][A]["verdict_ref"] is None and \
            w["card"]["leaves"][H]["verdict_ref"] == c1["leaves"][H]["verdict_ref"]
        no_green = bool(w) and w["gateway_now"] == "no-green" and w["revision_read"] == 504
        missing_all = m3.get("coverage_numerator", 0) > 0 and \
            (m3.get("missing_by_validator") or {}).get("independent-check") == m3.get("coverage_numerator")
        h_kept3 = c3["leaves"][H]["verdict_ref"] == c1["leaves"][H]["verdict_ref"] and o3["affected"] == [A]
        in_history = any(x["verdict_ref"] == c2["leaves"][A]["verdict_ref"] and "withdrawn" in x["reason"] for x in c3["history"])
        self.record("step", "step3", {"H": "unchanged", "A_withdrawn_first": True, "A": FAIL,
                                      "missing": "independent-check for every covered target", "aggregate": FAIL,
                                      "gateway": "hold", "gateway_while_pending": "no-green"},
                    {"H_kept": h_kept3, "A_withdrawn_first": withdrawn, "old_A_in_history": in_history,
                     "A": c3["leaves"][A]["state"], "missing_by_validator": m3.get("missing_by_validator"),
                     "covered": m3.get("coverage_numerator"), "aggregate": c3["aggregate"], "gateway": g3,
                     "gateway_while_pending": w and w["gateway_now"]},
                    h_kept3 and withdrawn and in_history and no_green and missing_all and c3["leaves"][A]["state"] == FAIL
                    and c3["aggregate"] == FAIL and g3 == "hold",
                    self.bindings(o3), card=leaves(c3), verdicts={d: summary(v) for d, v in o3["by_leaf"].items()},
                    withdrawn_card=w)
        self.judge("F2", main, "rev3", {"by_leaf": {H: o1["by_leaf"][H], A: a3}}, c3,
                   extra_checks={"H kept": h_kept3, "A support withdrawn before the new verdict": withdrawn,
                                 "independent-check reported missing for every covered target": missing_all})

    def lane(self, label: str, card: dict[str, Any], gw: str) -> None:
        """One row of the verdict timeline (manuscript Fig. 4)."""
        h, a = card["leaves"].get(H), card["leaves"].get(A)
        fmt = lambda l: "—" if l is None else (l["state"] or "pending")  # noqa: E731
        self.progress(f"{label:6} │ H {fmt(h):13} │ A {fmt(a):13} │ aggregate {card['aggregate']:13} │ gateway {gw}")

    # ---------------------------------------------------------------- cases (A10.2)
    def case(self, id: str, decision: str, prof_name: str, snap: view.Snapshot | None = None,
             also: Callable[[dict[str, Any]], dict[str, bool]] | None = None, **kw) -> None:
        """One case on a fresh consumer; `also(by_leaf)` gives the case's further checks."""
        prof = with_decision(self.env.profiles[prof_name], decision)
        c = Consumer()
        out = self.cycle(f"{id} ({decision}, {prof_name})", c, prof, snap or self.env.snap, self.regs["step2"][0])
        self.judge(id, decision, prof_name, out, c.card(self.t(prof)),
                   extra_checks=also(out["by_leaf"]) if also else None, **kw)

    def cases(self) -> None:
        env, s = self.env, self.sel
        green = lambda d: view.get_decision(env.snap, d)["decision"]["payload"]["verdict"] == "green"  # noqa: E731
        self.guarded("F3", lambda: self.case("F3", s["strict"], "rev3", also=lambda v: {
            "the decision is GREEN": green(s["strict"])}))

        def f4():
            snap = view.load_snapshot(env.fixtures / "derived" / "F4" / "corpus", env.bundle / "target")
            # the oracle reads the authentic bundle: it judges A (unaffected by the policy blob), not H
            self.case("F4", s["main"], "rev3", snap=snap, oracle_h=False, also=lambda v: {
                "the copy is missing the policy-at-event blob": len(snap.missing_blobs) == 1,
                "H names the unresolvable policy-at-event": any("policy-at-event" in r for r in v[H]["reasons"]),
                "today's requirement is not substituted (H has no coverage measurement)":
                    "coverage_numerator" not in v[H]["measurements"]})
        self.guarded("F4", f4)

        def f5():
            mq = json.loads((env.fixtures / "manifests" / "M_q.json").read_text())["functions"]
            scanned = {f for r in env.snap.query.basis(s["pipeline"])["records"] if r["event_type"] == "semgrep.scan"
                       for f in r["payload"].get("scanned", [])}
            self.case("F5", s["pipeline"], "rev3", attainable={u.split("::")[0] for u in mq} <= scanned)
        self.guarded("F5", f5)

        pol = view.get_decision(env.snap, s["main"])["policy"]["payload"]

        def f7_also(v: dict[str, Any]) -> dict[str, bool]:
            m = v[A]["measurements"]
            return {"coverage reported exactly as c_obs":
                        f"{m['coverage_numerator']}/{m['coverage_denominator']}" == env.params["c_obs_count"],
                    "policy identity preserved (H judged under the recorded policy)":
                        v[H]["measurements"].get("policy") == f"{pol['id']}@{pol['version']}"}
        self.guarded("F7", lambda: self.case("F7", s["main"], "rev3b", also=f7_also))
        self.guarded("F8", lambda: self.case("F8", s["strict"], "rev2"))

        def f9():
            obs = {}
            for d in env.f9:
                for rev in ("rev1", "rev2", "rev3"):
                    prof = with_decision(env.profiles[rev], d)
                    c = Consumer()
                    out = self.cycle(f"F9 ({d}, {rev})", c, prof, env.snap, self.regs["step2"][0])
                    card = c.card(self.t(prof))
                    diffs = agrees(out["by_leaf"][H], self.oracle.get(("H", d)))
                    if A in out["by_leaf"]:
                        diffs += agrees(out["by_leaf"][A], self.oracle.get(("A", d, rev)))
                    obs[f"{d} {rev}"] = {"H": card["leaves"][H]["state"], "A": (card["leaves"].get(A) or {}).get("state"),
                                         "aggregate": card["aggregate"], "oracle_agrees": not diffs, "notes": diffs,
                                         "binding": self.bindings(out)}
            self.record("observation", "F9", "as observed", obs, None,
                        {k: v.pop("binding") for k, v in obs.items()},
                        ["observation of Green Verdict Ambiguity; not part of A_comp"] if obs else
                        ["no other GREEN G-main decision"])
        self.guarded("F9", f9)

    # ---------------------------------------------------------------- interleavings (A10.3), F6
    def interleavings(self) -> None:
        env, P, main = self.env, self.env.profiles, self.sel["main"]
        reg1, reg2 = self.regs["step1"][0], self.regs["step2"][0]
        t3 = self.t(P["rev3"])

        def i1():
            c = Consumer()
            q = DelayQueue(c)
            self.cycle("I1 rev 1", c, P["rev1"], env.snap, reg1)
            h_ref = c.card()["leaves"][H]["verdict_ref"]
            self.cycle("I1 rev 2 (A delayed)", c, P["rev2"], env.snap, reg2, hold=q.hold_leaf(A))
            o3 = self.cycle("I1 rev 3", c, P["rev3"], env.snap, reg2)
            before = c.card(t3)
            old, ok, why = q.release(0, t3)
            after = c.card(t3)
            ref = verdict_ref(old)
            stored = any(x["verdict_ref"] == ref and x["reason"].startswith("rejected") for x in after["history"])
            unchanged = leaves(before) == leaves(after)
            h_same = after["leaves"][H]["verdict_ref"] == h_ref
            obs = {"old_admitted": ok, "reason": why, "in_history": stored, "posture_unchanged": unchanged,
                   "H_unchanged": h_same, "A": after["leaves"][A]["state"], "aggregate": after["aggregate"]}
            b = {"old": old["binding"], "new": o3["by_leaf"][A]["binding"]}
            self.record("interleaving", "I1", env.expect["interleavings"]["I1"]["expect"], obs,
                        not ok and stored and unchanged, b, card=leaves(after))
            self.record("case", "F6", {"H": "unchanged", "A": "old verdict rejected, kept in history"},
                        {"H_unchanged": h_same, "old_admitted": ok, "in_history": stored}, h_same and not ok and stored, b,
                        decision=main, profile="rev2 verdict delayed past rev3", h_H_ok=old["binding"]["h_H"] == self.captured[main])

        def i2():
            c = Consumer()
            q = DelayQueue(c)
            self.cycle("I2 rev 1", c, P["rev1"], env.snap, reg1)
            self.cycle("I2 rev 2 (A delayed)", c, P["rev2"], env.snap, reg2, hold=q.hold_leaf(A))
            self.cycle("I2 rev 3 (A delayed)", c, P["rev3"], env.snap, reg2, hold=q.hold_leaf(A))
            old, ok, why = q.release(0, t3)                 # the old verdict arrives first
            mid = c.card(t3)
            new, ok_new, _ = q.release(0, t3)
            end = c.card(t3)
            ref = verdict_ref(old)
            stored = any(x["verdict_ref"] == ref and x["reason"].startswith("rejected") for x in mid["history"])
            obs = {"old_admitted": ok, "reason": why, "in_history": stored, "A_after_old": mid["leaves"][A]["state"],
                   "aggregate_after_old": mid["aggregate"], "new_admitted_later": ok_new, "A_end": end["leaves"][A]["state"]}
            self.record("interleaving", "I2", env.expect["interleavings"]["I2"]["expect"], obs,
                        not ok and stored and mid["leaves"][A]["state"] is None and mid["aggregate"] != SUCCESS,
                        {"old": old["binding"], "new": new["binding"]}, card=leaves(mid))

        self.guarded("I1", i1)
        self.guarded("I2", i2)

    # ---------------------------------------------------------------- boundary checks (A10.4)
    def boundary(self) -> None:
        env, P, main = self.env, self.env.profiles, self.sel["main"]
        reg2 = self.regs["step2"][0]
        exp = env.expect["boundary"]
        positive = lambda card: any(l["state"] == SUCCESS for l in card["leaves"].values())  # noqa: E731
        derived = lambda k: view.load_snapshot(env.fixtures / "derived" / k / "corpus", env.bundle / "target")  # noqa: E731

        def b1():
            snap = derived("B1")
            st = view.get_decision(snap, main)["status"]
            prof = with_decision(P["rev2"], main)
            c = Consumer()
            out = self.cycle("B1", c, prof, snap, reg2)
            card = c.card(self.t(prof))
            obs = {"decision_status": st, "H": card["leaves"][H]["state"], "A": card["leaves"][A]["state"],
                   "positive_support": positive(card)}
            self.record("boundary", "B1", exp["B1"]["expect"], obs,
                        st == "unavailable" and obs["H"] == INCONCLUSIVE and not obs["positive_support"],
                        self.bindings(out), card=leaves(card))

        def b2():
            try:
                derived("B2")
                found, msg = False, "loaded"
            except view.IntegrityFinding as e:
                found, msg = True, str(e)
            self.record("boundary", "B2", exp["B2"]["expect"], {"integrity_finding_at_load": found, "finding": msg,
                                                                "verdicts_produced": 0}, found, None)

        def b3():
            snap = derived("B3")
            st = view.get_decision(snap, main)["status"]
            prof = with_decision(P["rev2"], main)
            c = Consumer()
            out = self.cycle("B3", c, prof, snap, reg2)
            card = c.card(self.t(prof))
            obs = {"decision_status": st, "H": card["leaves"][H]["state"], "A": card["leaves"][A]["state"],
                   "positive_support": positive(card)}
            self.record("boundary", "B3", exp["B3"]["expect"], obs,
                        st == "partial" and obs["H"] == INCONCLUSIVE and obs["A"] == INCONCLUSIVE, self.bindings(out),
                        card=leaves(card))

        def b4():
            recs = [r for r in assessments(env.snap, main)["records"] if r["validator"] == BASE and r["time"]]
            times = sorted(parse_utc(r["time"]) for r in recs)
            variants = {"t_e before the oldest supporting record": times[0] - timedelta(seconds=1),
                        "a supporting record after t_e": times[-1] - timedelta(seconds=1)}
            obs, bind, ok = {}, {}, True
            for name, te in variants.items():
                prof = with_decision(P["rev2"], main, assessment_time=te.strftime(ISO))
                c = Consumer()
                out = self.cycle(f"B4 ({name})", c, prof, env.snap, reg2)
                a = out["by_leaf"][A]
                obs[name] = {"t_e": te.strftime(ISO), "A": a["state"], "age": a["measurements"].get("max_age_seconds"),
                             "age_ok": a["measurements"].get("age_ok")}
                bind[name] = a["binding"]
                ok &= a["state"] == INCONCLUSIVE and a["measurements"].get("age_ok") is None
            notes = [] if times[0] != times[-1] else ["all supporting records share one time: both variants coincide"]
            self.record("boundary", "B4", exp["B4"]["expect"], obs, ok, bind, notes)

        def admission():
            """B5-B10: a consumer at rev 2 with H admitted and A pending; each mutated A verdict must be rejected."""
            prof = with_decision(P["rev2"], main)
            t = self.t(prof)
            invs = resolve(prof, env.snap, reg2, env.manifests)
            c = Consumer()
            c.activate(prof, {i.leaf: i.binding for i in invs})
            from ..evaluation import evaluate
            vs = {i.leaf: evaluate(i, env.snap, env.manifests) for i in invs}
            c.admit(vs[H], t)
            other = view.load_snapshot(env.fixtures / "derived" / "B3" / "corpus", env.bundle / "target").id
            mutations = {
                "B5": ("routed to the wrong destination leaf (the conformance leaf)", "d", H),
                "B6": ("requirement revision", "v_q", vs[A]["binding"]["v_q"] + 1),
                "B7": ("context", "kappa", "another-context"),
                "B8": ("snapshot", "s", other),
                "B9": ("test version", "v_mu", "1.1"),
                "B10": ("destination", "d", "release.other"),
            }
            for id, (what, field, value) in mutations.items():
                m = copy.deepcopy(vs[A])
                m["binding"][field] = value
                ok, why = c.admit(m, t)
                card = c.card(t)
                self.record("boundary", id, exp[id]["expect"], {"changed": what, "admitted": ok, "reason": why,
                                                                "A": card["leaves"][A]["state"], "aggregate": card["aggregate"]},
                            not ok and card["leaves"][A]["state"] is None and card["aggregate"] != SUCCESS, m["binding"])
            ok, why = c.admit(vs[A], t)                      # positive control: the genuine verdict is admitted
            self.record("control", "B5-B10 genuine verdict", {"admitted": True}, {"admitted": ok, "reason": why}, ok,
                        vs[A]["binding"])

        for id, fn in (("B1", b1), ("B2", b2), ("B3", b3), ("B4", b4), ("B5-B10", admission)):
            self.guarded(id, fn)

    def run(self) -> list[dict[str, Any]]:
        import pwexp.stages.stage1_acquire as stage1
        from ..control_guard import ENTRY_POINTS
        armed = all(getattr(getattr(stage1, n), "__qualname__", "").startswith("Guard._stub") for n in ENTRY_POINTS)
        for id, fn in (("main sequence", self.main_sequence), ("cases", self.cases),
                       ("interleavings", self.interleavings), ("boundary", self.boundary)):
            self.guarded(id, fn)
        fps = {fp for _, fp in self.fingerprints}
        calls = len(self.guard.calls)
        self.record("isolation", "isolation", {"guard_calls": 0, "fingerprints": "all equal"},
                    {"guard_armed": armed, "guard_calls": calls, "cycles": len(self.guard_counts),
                     "fingerprints_taken": len(self.fingerprints), "distinct_fingerprints": len(fps)},
                    armed and calls == 0 and all(n == 0 for _, n in self.guard_counts) and len(fps) == 1, None,
                    fingerprint=sorted(fps)[0] if len(fps) == 1 else sorted(fps))
        return self.records


def one_pass(env: Env, oracle: dict[tuple, dict[str, Any]], progress: Callable[[str], None]) -> list[dict[str, Any]]:
    with disabled_control() as guard, Gateway() as gw:
        return Pass(env, gw, guard, oracle, progress).run()


# ------------------------------------------------------------------ acceptance (A10.5)
def semantic(records: list[dict[str, Any]]) -> str:
    """R-ISO-3: request ids and elapsed times are excluded; the records hold neither."""
    return sha256_json(records)


def acceptance(records: list[dict[str, Any]], replay_digests: list[str]) -> dict[str, Any]:
    by = {r["id"]: r for r in records}
    m = lambda *ids: [(i, bool(by.get(i, {}).get("match"))) for i in ids]  # noqa: E731
    step2 = by.get("step2", {})
    comp = step2.get("composition") or {}
    cases = [i for i in ("F1", "F2", "F3", "F4", "F5", "F7", "F8") if i in by]
    root_ok = [(i, bool(by[i].get("root_vs_oracle"))) for i in cases]
    oracle_ok = [(i, not any(n.startswith(("H:", "A:")) for n in by[i]["notes"])) for i in cases]
    h_h = [(i, bool(by[i].get("h_H_ok"))) for i in [*cases, "F6"] if i in by]
    rows = {
        "AC1": ("Conformance/adequacy distinction", m("F2", "F3", "F8")),
        "AC2": ("Second-test composition", [("only registration", bool(comp.get("only_registration"))),
                                            ("only a profile edit", bool(comp.get("only_profile_edit"))),
                                            ("step2", bool(step2.get("match")))] + m("F1")),
        "AC3": ("Correct posture publication", [(f"{i} leaves", ok) for i, ok in oracle_ok] +
                [(f"{i} root", ok) for i, ok in root_ok] + m("step1", "step2", "step3")),
        "AC4": ("Policy-at-event binding preserved", [(f"{i} h_H", ok) for i, ok in h_h] + m("F4")),
        "AC5": ("Missing or invalid record handling", m("B1", "B2", "B3", "B4")),
        "AC6": ("Delayed or misrouted verdict rejection", m("I1", "I2", *[f"B{i}" for i in range(5, 11)])),
        "AC7": ("Control isolation and code stability", m("isolation")),
        "AC8": ("Semantic replay", [(f"replay {i + 1}", d == replay_digests[0]) for i, d in enumerate(replay_digests)]
                + [("at least two runs", len(replay_digests) >= 2)]),
    }
    out = {k: {"row": row, "passes": bool(items) and all(ok for _, ok in items),
               "failing": [i for i, ok in items if not ok], "checked": [i for i, _ in items]}
           for k, (row, items) in rows.items()}
    return {"acceptance": out, "A_comp": all(v["passes"] for v in out.values())}


def run_protocol(env: Env, replay_runs: int, progress: Callable[[str], None] = print) -> dict[str, Any]:
    oracle = oracle_judgements(env)
    runs, digests = [], []
    for i in range(replay_runs):
        progress(f"functional pass {i + 1} of {replay_runs}")
        recs = one_pass(env, oracle, progress if i == 0 else (lambda m: None))
        runs.append(recs)
        digests.append(semantic(recs))
    records = runs[0]
    acc = acceptance(records, digests)
    records.append({"kind": "replay", "id": "replay", "executed": True, "expected": "identical semantic records",
                    "observed": digests, "match": len(set(digests)) == 1 and len(digests) >= 2, "binding": None,
                    **env.stamp})
    missing = [i for i in IDS if not any(r["id"] == i and r.get("executed") for r in records)]
    return {"records": records, "acceptance": acc, "missing": missing, "digests": digests, "oracle": oracle}
