# Composable CDRT experiment

Control-decision risk testing over recorded decisions. A control (here RepoAudit, an LLM-agent repository auditor) makes a decision; ProofWeave records it with its intent, its basis and the policy in force; registered decision tests then judge whether the decision was licensed by its own policy (conformance) and whether it is enough for today's requirement (adequacy), and only verdicts bound to the active requirement reach the gateway's posture.

**Status: under construction.** Labs 3 and 4 run in development mode. No result has been produced. Everything under `capture/dev/` and `capture/records-dev/` is development data built from ProofWeave's fixtures and is never a result.

## Run it lab by lab

```bash
git clone --recurse-submodules <this repository>
cd cdrt-decision-testing
uv venv --python 3.13 .venv && VIRTUAL_ENV=$PWD/.venv uv pip install -e '.[dev]'
.venv/bin/cdrt lab status --dev
.venv/bin/cdrt lab run 3 --dev        # build the corpus from the development fixtures
.venv/bin/cdrt lab run 4 --dev        # review decisions and pathways, freeze the bundle
.venv/bin/cdrt lab view 4 pathways --dev
```

Each lab re-verifies the previous lab's hand-off, runs fixed checks, prints a lab card (inputs, checks, outputs, what it hands on) and seals its own hand-off. A lab passes only when every check passes; a check whose code is not built yet is shown as such and keeps the lab from passing. Passing a lab means the run was complete and intact. The result it reports is whatever it is.

| Lab | Name | Needs a model | Status |
|---|---|---|---|
| 0 | Set up and declare: target, scope manifests M_h and M_q, policies, decision schedule | no | not built |
| 1 | Pilot capture: declare τ_h from pilot runs, take the capture lock | yes | not built |
| 2 | Capture: the locked schedule of decisions, each context sealed before its runs | yes | not built |
| 3 | Build the corpus: ProofWeave Stage 2 with decision binding, re-verified by the record view | no | built (dev) |
| 4 | Review ProofWeave and freeze: decisions, pathways, selection, frozen bundle | no | built (dev), selection pending |
| 5 | Build fixtures: thresholds, profiles, derived variants, scale planes | no | not built |
| 6 | Lock: hash everything the runs depend on; tag | no | not built |
| 7 | Functional run (RQ1): cases, interleavings, boundary checks, isolation, replay, A_comp | no | not built |
| 8 | Scale run (RQ2): 400 timed cycles over four basis sizes, 5 s budget, p95 | no | not built |
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
src/cdrt/              record view, lab framework and labs, review pages, command line
results/labs[-dev]/    lab state, hash-chained lab log, per-attempt hand-offs and cards
tests/                 development tests (not experiment results)
```
