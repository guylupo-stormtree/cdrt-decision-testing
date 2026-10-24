# Composable CDRT experiment

Control-decision risk testing over recorded decisions. A control (here RepoAudit, an LLM-agent repository auditor) makes a decision; ProofWeave records it with its intent, its basis and the policy in force; registered decision tests then judge whether the decision was licensed by its own policy (conformance) and whether it is enough for today's requirement (adequacy), and only verdicts bound to the active requirement reach the gateway's posture.

**Status: under construction.** Labs 3–8 run in development mode; the CDRT runtime (registry, resolver, executor, the two decision tests, posture consumer, gateway, monitor), the independent oracle, the fixture build, the protocol lock, the functional harness and the scale harness are built. No result has been produced. Everything under `capture/dev/`, `capture/records-dev/`, `fixtures/out-dev/` and `results/labs-dev/` is development data built from ProofWeave's fixtures and is never a result.

## Run it lab by lab

```bash
git clone --recurse-submodules <this repository>
cd cdrt-decision-testing
uv venv --python 3.13 .venv && VIRTUAL_ENV=$PWD/.venv uv pip install -e '.[dev]'
.venv/bin/cdrt lab status --dev
.venv/bin/cdrt lab run 3 --dev        # build the corpus from the development fixtures
.venv/bin/cdrt lab run 4 --dev        # review decisions and pathways, freeze the bundle
.venv/bin/cdrt lab view 4 pathways --dev
.venv/bin/cdrt lab run 5 --dev        # fixtures: parameters, profiles, derived copies, scale planes (built twice)
.venv/bin/cdrt lab run 6 --dev        # lock everything later labs depend on
.venv/bin/cdrt verify-lock --dev
.venv/bin/cdrt lab run 7 --dev        # functional protocol (RQ1): A_comp
.venv/bin/cdrt lab run 8 --dev        # scale protocol (RQ2): 400 timed cycles, p95 per size
.venv/bin/cdrt pilot scale --dev --blocks 20   # pilot timing before a lock (results/pilot/, never a result)
```

Each lab re-verifies the previous lab's hand-off, runs fixed checks, prints a lab card (inputs, checks, outputs, what it hands on) and seals its own hand-off. A lab passes only when every check passes; a check whose code is not built yet is shown as such and keeps the lab from passing. Passing a lab means the run was complete and intact. The result it reports is whatever it is.

| Lab | Name | Needs a model | Status |
|---|---|---|---|
| 0 | Set up and declare: target, scope manifests M_h and M_q, policies, decision schedule | no | not built |
| 1 | Pilot capture: declare τ_h from pilot runs, take the capture lock | yes | not built |
| 2 | Capture: the locked schedule of decisions, each context sealed before its runs | yes | not built |
| 3 | Build the corpus: ProofWeave Stage 2 with decision binding, re-verified by the record view | no | built (dev) |
| 4 | Review ProofWeave and freeze: decisions, pathways, selection (runtime and oracle must agree), frozen bundle | no | built (dev) |
| 5 | Build fixtures: thresholds, profiles, derived variants, scale planes | no | built (dev) |
| 6 | Lock: hash everything the runs depend on; tag | no | built (dev) |
| 7 | Functional run (RQ1): cases, interleavings, boundary checks, isolation, replay, A_comp | no | built (dev) |
| 8 | Scale run (RQ2): 400 timed cycles over four basis sizes, 5 s budget, p95 | no | built (dev) |
| 9 | Report: generated tables, figure and result text for the manuscript | no | not built |

Labs 0–2 are run by the authors and need RepoAudit and a model. Labs 3–9 run offline from the frozen bundle, with Python only.

## Dependencies

- **ProofWeave** (`pwexp`) is pinned as the git submodule `vendor/proofweave-decision-assurance` at tag `pw-v0.2.0` and installed from it. CDRT imports only `pwexp.proofweave`, `pwexp.hashing`, `pwexp.chain` and the Stage 1/2 entry points, and drives capture through the `pwexp` command line; a test enforces this.
- **RepoAudit** is pinned inside the ProofWeave checkout (commit `160f5bc`) and runs only in Labs 1–2.
- API keys are typed at a masked prompt for each run, held in memory only, and never written anywhere.

## Layout

```
capture/dev/           development capture protocol, policies, manifests (fixtures only)
capture/records-dev/   development capture cycles (local, git-ignored)
capture/bundle[-dev]/  frozen corpus, Stage 1 bundles, target snapshot, protocol files (read-only)
fixtures/out[-dev]/    parameters.json, profiles rev 1–3b, manifests, derived copies F4 B1–B3, scale planes
protocol/              run_config.yaml (every seed and count) and, for the reported campaign, protocol.lock.json
src/cdrt/              record view and assessments, registry, resolver, executor, the two registered
                       decision tests, posture consumer, gateway (separate process), monitor, fixtures,
                       lock, control guard, harness (functional protocol, delayed-result scheduler,
                       code fingerprints, scale protocol), labs
oracle/                expectations.yaml and oracle_check.py (standard library only, imports nothing of
                       cdrt or pwexp; reads the frozen bundle directly)
results/labs[-dev]/    lab state, hash-chained lab log, per-attempt hand-offs and cards
results/pilot/         pilot timing runs before a lock (local, git-ignored; disclosed, never results)
tests/                 development tests (not experiment results)
```

## How a decision is judged

- **Assessment records.** For a decision, every record of its basis runs is read through ProofWeave's query interface and turned into assessment records. `base-check` is accepted for a function when the RepoAudit run carried a None into it from another function and reported no finding involving it. `independent-check` is accepted when the Semgrep run scanned its file and found nothing in it.
- **Coverage** (Eq. 3) counts the scope functions with an accepted `base-check`; the other listed validators must corroborate every covered function (Eq. 4). Exact fractions; duplicates never raise the count.
- **conformance-check@1.0** judges the decision under its own policy-at-event, resolved through the recorded binding. **adequacy-check@1.0** judges it under the current requirement, adding the age condition (Eq. 6).
- **Admission** (Eq. 8) accepts a verdict only if its 14-field binding equals the one the active requirement revision expects and it has not expired. Activating a revision withdraws affected support before any new verdict can be admitted.


## What is timed (RQ2)

- **T_assess** (Eq. 9) runs from the activation of rev 3 to the moment a waiting reader has a complete rev-3 posture from the gateway over HTTP. It includes profile resolution, `decision()` and `basis()` retrieval through ProofWeave's Query API, the basis-root and binding check, **both** decision tests (the unaffected conformance leaf is re-run too, so the figure is conservative), admission, aggregation and publication.
- Loading and verifying a plane, rebuilding its graph and building ProofWeave's decision index happen before timing.
- Within one cycle, the decision and its basis are retrieved once and that immutable view is shared by both tests (R-TST-5); every timing record logs the sharing. CDRT's record view groups the basis by run once, so the assessment projection is linear in N (R-SCL-10).
