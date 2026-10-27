# Where to find things

A short map of this repository for readers of the paper. Paths are relative to the repository root.

**The reported campaign is `campaign-004`** (tag `cdrt-campaign-004`). The experiment runs in ten labs (0–9). Each
lab keeps every attempt in `results/labs/labN/attemptK/`. The highest-numbered attempt is the final one. Earlier
attempts are kept on purpose: nothing is overwritten or deleted.

| Lab | Final attempt | What it did |
|---|---|---|
| 0 | `attempt6` | Declared the target and model, fetched the code, drafted the scope |
| 1 | `attempt5` | Pilot: 5 runs, set the conformance threshold τ_h |
| 2 | `attempt3` | Locked the capture rules and ran the 50 RepoAudit runs |
| 3 | `attempt1` | Built the evidence corpus with ProofWeave |
| 4 | `attempt1` | Review pages; froze the evidence |
| 5 | `attempt1` | Built the test fixtures |
| 6 | `attempt4` | Locked the experiment (campaign-004) |
| 7 | `attempt4` | RQ1: functional run |
| 8 | `attempt4` | RQ2: timing run |
| 9 | `attempt3` | Wrote the paper's results |

## 1. Outcomes

| You want | Look in |
|---|---|
| The results as they appear in the paper (tables, figures, sentences) | `results/labs/lab9/attempt3/generated/` |
| A one-screen summary of each lab: checks passed, key numbers | `results/labs/labN/attemptK/card.txt` |
| The whole experiment told in plain language | `results/labs/STORY.md` |
| RQ1 verdicts: acceptance conditions, A_comp | `results/labs/lab7/attempt4/acceptance.json` |
| RQ1 step by step | `results/labs/lab7/attempt4/trace.txt` |
| RQ2 slowest update per size | `results/labs/lab8/attempt4/scale_stats.json` |
| What each green run actually examined (open in a browser) | `results/labs/lab4/attempt1/views/pathways.html` and `decisions.html` |
| Which record each number in the paper comes from | `results/labs/lab9/attempt3/trace.json` |

## 2. Experiment logs

| You want | Look in |
|---|---|
| What was on screen during each lab | `results/labs/labN/attemptK/screen.txt` |
| Screen output of the 50-run capture, kept from the terminal | `results/screen-capture/` |
| Every lab run, pass or fail, in order (hash-chained) | `results/labs/lab-log.jsonl` |
| Every experiment lock and campaign | `results/CAMPAIGNS.md` |
| The capture's own log: stages, the two interruptions and resumes | `capture/records/cycles/campaign-0001/stage-log.jsonl` and `cycle.json` |
| RQ1 records, one per step | `results/labs/lab7/attempt4/functional_records.jsonl` |
| RQ2 records, one per timed update (400) | `results/labs/lab8/attempt4/timing_records.jsonl` |
| The timing host and settings | `results/labs/lab8/attempt4/run_manifest.json` |

## 3. Data

| You want | Look in |
|---|---|
| What the authors declared before the capture: target, model, run counts, scope | `capture/capture.yaml` |
| The capture protocol and its lock | `capture/cdrt-protocol.yaml`, `capture/protocol.lock.json` |
| The scope manifests (M_h, M_q) and who approved them | `capture/manifests/` (`REVIEW.json`) |
| The policy in force at capture (τ_h) | `capture/policies/` |
| The audited code (python-dateutil, parser only) | `capture/target/` |
| **The 50 RepoAudit runs:** RepoAudit's log, every model call, findings | `capture/records/cycles/campaign-0001/stage1/attempt1/repoaudit/gpt-pw-m1/runNNN/` |
| **The 50 decisions:** context sealed before the run, verdict after | `capture/records/cycles/campaign-0001/stage1/attempt1/decisions/G-main-NN/` |
| The two runs cut off by an interruption (kept, then run again) | `capture/records/cycles/campaign-0001/stage1/attempt1/interrupted/` |
| The independent Semgrep scan | `capture/records/cycles/campaign-0001/stage1/attempt1/semgrep/` |
| The ProofWeave evidence corpus | `capture/records/cycles/campaign-0001/stage2/attempt1/corpus/` |
| The pilot runs | `capture/records/cycles/pilot-0001/`, `pilot-0002/` |
| The frozen evidence everything after Lab 4 is judged on (read-only copy) | `capture/bundle/` |
| The experiment lock: hashes of the bundle, fixtures, code and settings | `protocol/protocol.lock.json` |
| An earlier, wider scope that was abandoned before the campaign | `capture/archive/` |

The test fixtures (`fixtures/out/`, 1.2 GB) are not in the repository. `cdrt lab run 5` rebuilds them byte for byte
from `capture/bundle/`, and the lock records their hash.

## 4. Code

| You want | Look in |
|---|---|
| How to install and run | `README.md` |
| CDRT itself: runtime, tests, gateway | `src/cdrt/` |
| The ten labs | `src/cdrt/labs/` |
| The independent oracle and its expectations | `oracle/` |
| RQ2 timing settings | `protocol/run_config.yaml` |
| ProofWeave and RepoAudit, at their pinned versions | `vendor/` (fetched by `fetch-dependencies.sh`) |

To repeat the assessment and timing offline, with no model or API key: `cdrt lab run 5-9`.
