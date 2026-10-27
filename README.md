# Composable CDRT experiment

Looking for the results, the logs or the data? See [GUIDE.md](GUIDE.md).

Control-decision risk testing over recorded decisions. A control (here RepoAudit, an LLM-agent repository auditor) makes a decision; ProofWeave records it with its intent, its basis and the policy in force; registered decision tests then judge whether the decision was licensed by its own policy (conformance) and whether it is enough for today's requirement (adequacy), and only verdicts bound to the active requirement reach posture, which a TAIP posture stub rolls up for the gateway.

**Scope (manuscript main-14).** Every RepoAudit run is captured as a decision under one policy (P1), and a Semgrep scan of the same repository is retained beside them, in no decision's basis. The first green conformant decision is tested by the two modules before and after the requirement adds `independent-check`, with one delayed-result check; every green decision is also assessed and drawn in the pathway figure. The timing study repeats the requirement change on synthetic bases of about 10² to 10⁵ records.

**Status: under construction.** Labs 3–9 run in development mode; the CDRT runtime (registry, resolver, executor, the two decision tests, posture consumer, gateway, monitor), the independent oracle, the fixture build, the protocol lock, the functional and scale harnesses and the report generator are built. No result has been produced. Everything under `capture/dev/`, `capture/records-dev/`, `fixtures/out-dev/` and `results/labs-dev/` is development data built from ProofWeave's fixtures and is never a result.

## Get everything (one repository)

```bash
git clone https://github.com/guylupo-stormtree/cdrt-decision-testing.git
cd cdrt-decision-testing && ./fetch-dependencies.sh
```

The script fetches ProofWeave (`vendor/proofweave-decision-assurance`, pinned tag) and, inside it, RepoAudit
(pinned commit), and nothing deeper: RepoAudit's own benchmark submodules (large C/C++/Go projects) are not
needed. Avoid `git clone --recurse-submodules`, which would also try to fetch them. The frozen corpus, fixtures, oracle, lock file and raw records are in this repository, so Labs 3-9
repeat offline with no RepoAudit, no language model and no API key:

```bash
uv venv --python 3.13 .venv && VIRTUAL_ENV=$PWD/.venv uv pip install -e '.[dev]'
.venv/bin/cdrt verify-lock
.venv/bin/cdrt lab run 3-9
```

## Capture (authors only: Labs 0-2)

1. Fill `capture/capture.yaml`: target repository URL and full commit, the files left out of the audited snapshot
   (`target.omit`), model provider and name, run counts. `cdrt capture reset --label TEXT` archives an earlier
   capture's working files (before any campaign) so Lab 0 starts clean.
2. `cdrt lab run 0`: environment, target fetched at its commit, scope manifests drafted from the code. Review
   (and edit if needed) `capture/manifests/drafts/`, then `cdrt manifests approve --by "Your Name"` and run Lab 0 again.
3. `cdrt lab run 1`: asks for the API key once, checks it with one minimal call, then runs the pilot (sets tau_h;
   reports model calls and minutes per run). The key stays in memory and is never written anywhere.
4. Optional, before the campaign: `cdrt capture campaign-runs N` sets the campaign size from the pilot's cost.
5. `cdrt lab run 2`: asks for the key again, locks the campaign protocol (tau_h and the campaign size), then runs
   the campaign. (`cdrt lab run 1-2` does both in one go, without the pause.)
   The campaign can be paused and resumed: Ctrl-C or a dropped connection pauses it, and `cdrt lab run 2` resumes
   the same campaign under the same lock (also after a reboot). Recorded runs are kept; the run that was cut off is
   kept as interrupted and run again, so a pause costs at most one run.
6. `cdrt lab run 3-9`: corpus, review and freeze, fixtures, lock, RQ1, RQ2, report.
   Offline (no key, no cost). If a lab is stopped, run again from that lab (e.g. `cdrt lab run 8-9`); it starts
   that lab over. Labs 3 and 4 are never repeated once passed: the corpus and the frozen bundle are built once.
7. `cdrt capture publish`: commits the campaign's declaration, protocol, records, frozen bundle, lock file and lab
   results on top of the locked code and tags the commit `cdrt-campaign-<NNN>`, the tag the manuscript cites; then
   `git push origin main --tags`. The fixtures are not committed: `cdrt lab run 5` rebuilds them byte for byte. From a
   clone of that tag, `cdrt lab run 5-9` repeats the assessment and timing offline.

Every lab tells what it is about to do and, when it ends, what happened, in plain language for a non-technical
audience; during the capture each audit run gets one plain line. Every number comes from the run's own records
or a named public source (the target's PyPI download count, from pypistats.org, with the date). The story is saved
as `story.md` in each lab attempt and collected in `results/labs/STORY.md` (`cdrt lab story`). In a second
terminal, `cdrt lab watch` shows one live line: the running lab, the audit run under way, GREEN so far, and when
RepoAudit was last active. Long runs are best started inside `tmux`, so a dropped SSH connection does not stop them.

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
.venv/bin/cdrt lab run 8 --dev        # scale protocol (RQ2): 400 timed cycles; the slowest update vs the 5 s budget
.venv/bin/cdrt pilot scale --dev --blocks 20   # pilot timing before a lock (results/pilot/, never a result)
.venv/bin/cdrt lab run 9 --dev        # report: generated blocks and figure, filled into a compiled copy of the manuscript
```

Lab 9 reads the newest manuscript, `../ComposableCDRT/Manuscript/main-<N>.tex` (or `$CDRT_MANUSCRIPT`), and never writes to it. main-15 holds no result: it reads everything the experiment generates from a `generated/` folder with `\input` (result and fixture macros, the *Experiment record* subsection with every version and hash, the before/after table, the pathway figure, the scale table and figure). Lab 9 writes that folder to `results/labs[-dev]/lab9/attempt<k>/generated/`, compiles a copy of the manuscript with it, and checks that the manuscript reads every file. After the reported campaign, replace the manuscript's `generated/` folder (in Overleaf too) with it.

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
| 7 | Functional run (RQ1): before/after the requirement change, one delayed result, every green decision observed, isolation, replay, A_comp | no | built (dev) |
| 8 | Scale run (RQ2): 400 timed cycles over four basis sizes; one number, the slowest update, against the 5 s budget | no | built (dev) |
| 9 | Report: generated tables, figure and result text for the manuscript | no | built (dev) |

Labs 0–2 are run by the authors and need RepoAudit and a model. Labs 3–9 run offline from the frozen bundle, with Python only.

## Dependencies

- **ProofWeave** (`pwexp`) is pinned as the git submodule `vendor/proofweave-decision-assurance` at tag `pw-v0.2.5` (decision binding, standalone Semgrep scans in decision protocols, RepoAudit run on a neutral copy of the target, Stage 1 pause and resume, stopped Stages 2-4 rerun) and installed from it. CDRT imports only `pwexp.proofweave`, `pwexp.hashing`, `pwexp.chain` and the Stage 1/2 entry points, and drives capture through the `pwexp` command line; a test enforces this.
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
                       code fingerprints, scale protocol), report generator, labs
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
- **coverage-composition@1.0** answers the adequacy question from all eligible decisions together: it qualifies each decision (GREEN, conformant under its own policy, same repository, commit and bug type, complete record, evidence within the maximum age), takes the union of what they checked, counts each function once against the independent release manifest, and also reports the *observed estate* (everything eligible decisions reached) and each decision's share of it, flagging green-but-narrow decisions. It reuses the approved conformance code and is digest-pinned like the others.
- **Admission** (Eq. 8) accepts a verdict only if its 14-field binding equals the one the active requirement revision expects and it has not expired. Activating a revision withdraws affected support before any new verdict can be admitted.
- **TAIP posture stub** (`cdrt/taip_stub.py`). A minimal stand-in for TAIP's aggregation, not the TAIP engine: the admitted SUCCESS / FAIL / INCONCLUSIVE verdicts become TAIP pass / fail / inconclusive on the effectiveness and adequacy branches, a sustainability branch re-checks that every admitted support is still bound to the active revision and unexpired, and the root (any fail → fail, any inconclusive → inconclusive, else pass) gives the gateway proceed, hold or no-green.
- **A_comp** (main-14 §4.4) holds only if four conditions hold in every run: the verdicts match the oracle before and after the change; the second module needed only registration and a profile edit; the gateway went proceed → no green → hold and rejected the delayed success; no control was re-executed. Replay agreement is reported beside it.


## What is timed (RQ2)

- **T_assess** (Eq. 9) runs from the activation of rev 3 to the moment a waiting reader has a complete rev-3 posture from the gateway over HTTP. It includes profile resolution, `decision()` and `basis()` retrieval through ProofWeave's Query API, the basis-root and binding check, **both** decision tests (the unaffected conformance leaf is re-run too, so the figure is conservative), admission, aggregation and publication.
- Loading and verifying a plane, rebuilding its graph and building ProofWeave's decision index happen before timing.
- Within one cycle, the decision and its basis are retrieved once and that immutable view is shared by both tests (R-TST-5); every timing record logs the sharing. CDRT's record view groups the basis by run once, so the assessment projection is linear in N (R-SCL-10).
