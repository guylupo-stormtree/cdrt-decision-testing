<!-- 2026-10-26 15:18 UTC -->
Lab 0 · Getting ready

  We are about to download python-dateutil, a real, widely used open-source library: about 899
  million downloads in the last month (pypistats.org, 26 October 2026).

  We will scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a
  value that may be empty (in Python, None) and crashing. First we mark, with our own
  independent analysis, the places in the code where such an empty value can be handed from
  one function to another. That is the area a careful audit has to look at.

<!-- 2026-10-26 15:18 UTC -->
Lab 0 · Getting ready · what happened

  Our own analysis, independent of the AI auditor, has drafted the list of places to check: 12
  places where an empty value can be handed between functions, 9 of them in the auditor's own
  area of responsibility.

  Before anything runs, a person reviews and approves this list. Then this step is run again.

<!-- 2026-10-26 15:19 UTC -->
Lab 0 · Getting ready

  We are about to download python-dateutil, a real, widely used open-source library: about 899
  million downloads in the last month (pypistats.org, 26 October 2026).

  We will scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a
  value that may be empty (in Python, None) and crashing. First we mark, with our own
  independent analysis, the places in the code where such an empty value can be handed from
  one function to another. That is the area a careful audit has to look at.

<!-- 2026-10-26 15:19 UTC -->
Lab 0 · Getting ready · what happened

  The library is downloaded at exactly the published version we declared
  (https://github.com/dateutil/dateutil @ 10f317fde11c); its licence allows us to publish it
  with the results (LICENSE: Copyright 2017- Paul Ganssle <paul@ganssle.io>).

  Our own analysis, independent of the AI auditor, found 12 places where an empty value can be
  handed between functions; 9 of them form the auditor's own area of responsibility. A person
  reviewed and approved these lists before anything ran.

  The AI model will be gpt-4.1.

  This step passed all its checks.

<!-- 2026-10-26 15:25 UTC -->
Lab 1 · A first look (pilot)

  RepoAudit now audits the library 5 times, as a first look, using the AI model gpt-4.1. Each
  run ends with a verdict: GREEN means no bug found.

  From these first runs we fix the auditor's own policy, the standard it was held to at the
  time, before the real audit starts. Once fixed, it cannot be changed.

<!-- 2026-10-26 15:25 UTC -->
Lab 1 · A first look (pilot) · what happened

  This step did not complete. In plain words: tau_h set by the declared rule and above zero
  (R-CAP-4) (tau_h = 0). Nothing is lost: the attempt is recorded, and the step can be run
  again once the cause is fixed.

<!-- 2026-10-26 15:33 UTC -->
Lab 0 · Getting ready

  We are about to download python-dateutil, a real, widely used open-source library: about 899
  million downloads in the last month (pypistats.org, 26 October 2026).

  We will scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a
  value that may be empty (in Python, None) and crashing. First we mark, with our own
  independent analysis, the places in the code where such an empty value can be handed from
  one function to another. That is the area a careful audit has to look at.

<!-- 2026-10-26 15:33 UTC -->
Lab 0 · Getting ready · what happened

  The library is downloaded at exactly the published version we declared
  (https://github.com/dateutil/dateutil @ 10f317fde11c); its licence allows us to publish it
  with the results (LICENSE: Copyright 2017- Paul Ganssle <paul@ganssle.io>).

  Our own analysis, independent of the AI auditor, found 12 places where an empty value can be
  handed between functions; 9 of them form the auditor's own area of responsibility. A person
  reviewed and approved these lists before anything ran.

  The AI model will be gpt-4.1.

  This step passed all its checks.

<!-- 2026-10-26 15:34 UTC -->
Lab 0 · Getting ready

  We are about to download python-dateutil, a real, widely used open-source library: about 899
  million downloads in the last month (pypistats.org, 26 October 2026).

  We will scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a
  value that may be empty (in Python, None) and crashing. First we mark, with our own
  independent analysis, the places in the code where such an empty value can be handed from
  one function to another. That is the area a careful audit has to look at.

<!-- 2026-10-26 15:34 UTC -->
Lab 0 · Getting ready · what happened

  The library is downloaded at exactly the published version we declared
  (https://github.com/dateutil/dateutil @ 10f317fde11c); its licence allows us to publish it
  with the results (LICENSE: Copyright 2017- Paul Ganssle <paul@ganssle.io>).

  Our own analysis, independent of the AI auditor, found 12 places where an empty value can be
  handed between functions; 9 of them form the auditor's own area of responsibility. A person
  reviewed and approved these lists before anything ran.

  The AI model will be gpt-4.1.

  This step passed all its checks.

<!-- 2026-10-26 15:35 UTC -->
Lab 1 · A first look (pilot)

  RepoAudit now audits the library 5 times, as a first look, using the AI model gpt-4.1. Each
  run ends with a verdict: GREEN means no bug found.

  From these first runs we fix the auditor's own policy, the standard it was held to at the
  time, before the real audit starts. Once fixed, it cannot be changed.

<!-- 2026-10-26 15:35 UTC -->
Lab 1 · A first look (pilot) · what happened

  This step did not complete. In plain words: tau_h set by the declared rule and above zero
  (R-CAP-4) (tau_h = 0). Nothing is lost: the attempt is recorded, and the step can be run
  again once the cause is fixed.

<!-- 2026-10-26 15:51 UTC -->
Lab 1 · A first look (pilot)

  RepoAudit now audits the library 5 times, as a first look, using the AI model gpt-4.1. Each
  run ends with a verdict: GREEN means no bug found.

  From these first runs we fix the auditor's own policy, the standard it was held to at the
  time, before the real audit starts. Once fixed, it cannot be changed.

<!-- 2026-10-26 17:53 UTC -->
Lab 0 · Getting ready

  We are about to download python-dateutil, a real, widely used open-source library: about 899
  million downloads in the last month (pypistats.org, 26 October 2026).

  We audit one part of it: its date parser, the part that reads dates written as text. We will
  scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a value
  that may be empty (in Python, None) and crashing. First we mark, with our own independent
  analysis, the places in the code where such an empty value can be handed from one function
  to another. That is the area a careful audit has to look at.

<!-- 2026-10-26 17:53 UTC -->
Lab 0 · Getting ready · what happened

  Our own analysis, independent of the AI auditor, has drafted the list of places to check: 7
  places where an empty value can be handed between functions, 5 of them in the auditor's own
  area of responsibility.

  Before anything runs, a person reviews and approves this list. Then this step is run again.

<!-- 2026-10-26 18:20 UTC -->
Lab 0 · Getting ready

  We are about to download python-dateutil, a real, widely used open-source library: about 899
  million downloads in the last month (pypistats.org, 26 October 2026).

  We audit one part of it: its date parser, the part that reads dates written as text. We will
  scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a value
  that may be empty (in Python, None) and crashing. First we mark, with our own independent
  analysis, the places in the code where such an empty value can be handed from one function
  to another. That is the area a careful audit has to look at.

<!-- 2026-10-26 18:20 UTC -->
Lab 0 · Getting ready · what happened

  The library is downloaded at exactly the published version we declared
  (https://github.com/dateutil/dateutil @ 10f317fde11c); its licence allows us to publish it
  with the results (LICENSE: Copyright 2017- Paul Ganssle <paul@ganssle.io>).

  Our own analysis, independent of the AI auditor, found 7 places where an empty value can be
  handed between functions; 5 of them form the auditor's own area of responsibility. A person
  reviewed and approved these lists before anything ran.

  The AI model will be gpt-4.1.

  This step passed all its checks.

<!-- 2026-10-26 18:22 UTC -->
Lab 1 · A first look (pilot)

  RepoAudit now audits the library 5 times, as a first look, using the AI model gpt-4.1. Each
  run ends with a verdict: GREEN means no bug found.

  From these first runs we fix the auditor's own policy, the standard it was held to at the
  time, before the real audit starts. Once fixed, it cannot be changed.

<!-- 2026-10-26 18:43 UTC -->
Lab 1 · A first look (pilot) · what happened

  This step did not complete. In plain words: at least 4 of 5 pilot runs GREEN (A5.1) (1
  GREEN). Nothing is lost: the attempt is recorded, and the step can be run again once the
  cause is fixed.

<!-- 2026-10-27 01:00 UTC -->
Lab 1 · A first look (pilot)

  RepoAudit now audits the library 5 times, as a first look, using the AI model gpt-4.1. Each
  run ends with a verdict: GREEN means no bug found.

  From these first runs we fix the auditor's own policy, the standard it was held to at the
  time, before the real audit starts. Once fixed, it cannot be changed.

<!-- 2026-10-27 01:30 UTC -->
Lab 1 · A first look (pilot) · what happened

  All 5 first runs are in: 1 said GREEN, no bugs found; 4 reported possible bugs, and not the
  same ones.

  But they did not check the same amount: of the auditor's area they covered 3/5, 4/5, 4/5,
  1/5, 2/5.

  From these runs the auditor's policy is now fixed: a run must cover at least 2/5 (40%) of
  its area. This policy, and the number of runs, are locked in at the start of the real audit.

  Each run asked the AI model 147 to 163 questions and took 6 to 7 minutes.

  This step passed all its checks.

<!-- 2026-10-27 01:30 UTC -->
Lab 2 · The real audit runs

  First we lock the audit's rules: the policy from the first look and the number of runs. From
  now on they cannot be changed.

  Now the real audit: RepoAudit runs 50 times on exactly the same code, with the same model
  and the same question. Before every run we seal what was asked and which policy applies.
  Every result is kept, good or bad.

  Watch the verdicts. What each GREEN actually checked stays hidden for now.

<!-- 2026-10-27 02:38 UTC -->
Lab 2 · The real audit runs

  First we lock the audit's rules: the policy from the first look and the number of runs. From
  now on they cannot be changed.

  Now the real audit: RepoAudit runs 50 times on exactly the same code, with the same model
  and the same question. Before every run we seal what was asked and which policy applies.
  Every result is kept, good or bad.

  Watch the verdicts. What each GREEN actually checked stays hidden for now.

<!-- 2026-10-27 04:44 UTC -->
Lab 2 · The real audit runs · what happened

  This step did not complete. In plain words: campaign finished (it was paused: `cdrt lab run
  2` resumes it) (⏸ Stage 1 paused (Ctrl-C); recorded work is kept. Resume: the same command
  with --resume). Nothing is lost: the attempt is recorded, and the step can be run again once
  the cause is fixed.

<!-- 2026-10-27 05:30 UTC -->
Lab 2 · The real audit runs

  First we lock the audit's rules: the policy from the first look and the number of runs. From
  now on they cannot be changed.

  Now the real audit: RepoAudit runs 50 times on exactly the same code, with the same model
  and the same question. Before every run we seal what was asked and which policy applies.
  Every result is kept, good or bad.

  Watch the verdicts. What each GREEN actually checked stays hidden for now.

<!-- 2026-10-27 12:17 UTC -->
Lab 2 · The real audit runs · what happened

  The real audit is complete: RepoAudit said GREEN in 5 of 50 runs. Every run, with what was
  asked and the policy in force, is kept.

  So far it looks like a clean bill of health. Next we look at what those GREENs actually rest
  on.

  This step passed all its checks.

<!-- 2026-10-27 13:00 UTC -->
Lab 3 · Freezing the evidence

  We hand every decision to ProofWeave, our evidence ledger. It binds together what was asked,
  which policy applied, what RepoAudit decided, and exactly what it examined, and seals it so
  that nothing can be changed afterwards.

<!-- 2026-10-27 13:00 UTC -->
Lab 3 · Freezing the evidence · what happened

  All decisions are now in the evidence ledger: 14437 records, each traceable to RepoAudit's
  own log, bound to its question, its decision and its policy, and sealed.

  Decisions: G-main 5/50 green.

  This step passed all its checks.

<!-- 2026-10-27 13:00 UTC -->
Lab 4 · The reveal: same green, different checks

  Now we look inside the GREEN verdicts: for each run, which of the places that needed
  checking did RepoAudit actually follow?

<!-- 2026-10-27 13:00 UTC -->
Lab 4 · The reveal: same green, different checks · what happened

  Here is the problem. All 5 runs said GREEN. But behind the same answer, they checked between
  0 and 5 of the 7 places that needed checking, along 3 different paths.

  Same tool, same code, same question, same model: a different audit every time. The verdict
  alone cannot tell a gateway which kind it got. We call this the Green Verdict Ambiguity.

  Together, though, the runs reached 5 of the 7 places. Keep that number in mind.

  One run is chosen by a rule fixed in advance to be tested in detail: G-main-19.

  This step passed all its checks.

<!-- 2026-10-27 13:00 UTC -->
Lab 5 · Today's requirement

  We set out today's release requirement, written down before any test is run, and prepare the
  test fixtures from the frozen evidence.

<!-- 2026-10-27 13:02 UTC -->
Lab 5 · Today's requirement · what happened

  Today's release requirement: at least 80% of the 7 places must have been checked, that is 6
  or more.

  The chosen run, on its own, checked 4/7.

  The requirement was written down before any of the evidence was examined.

  This step passed all its checks.

<!-- 2026-10-27 13:02 UTC -->
Lab 6 · Locking the experiment

  We lock the whole experiment: every file, every rule and every piece of code gets a
  fingerprint. From here on nothing can be adjusted to fit the results; any change would be
  detected.

<!-- 2026-10-27 13:02 UTC -->
Lab 6 · Locking the experiment · what happened

  The experiment is locked. Its fingerprint begins 21de6a1e1654. Every result from now on
  carries this fingerprint, so anyone can check that nothing was changed.

  This step passed all its checks.

<!-- 2026-10-27 13:02 UTC -->
Lab 7 · CDRT tests the decisions

  CDRT now tests the recorded decisions without running the auditor again. First it asks: did
  each decision follow the policy of its time? Then: is the evidence enough for today's
  requirement? Then the requirement changes, and we watch the gateway react.

<!-- 2026-10-27 13:02 UTC -->
Lab 7 · CDRT tests the decisions · what happened

  First question, did each decision follow the policy of its time? 4 of 5: yes.

  Second question, is the evidence enough for today? The chosen run alone checked 4/7: the
  gateway would say HOLD. 3 of the 5 GREEN runs were each too narrow on their own.

  CDRT then combines the qualified runs: together they checked 5/7, and the gateway says HOLD.
  The decision rests on independently tested, combined evidence, not on one GREEN verdict.

  Now the requirement changes: an independent second check is also required, which no run had.
  The past decisions still followed their own policy, but they are no longer enough: the
  gateway says HOLD.

  A late, outdated 'yes' from before the change arrives afterwards and is refused, so it
  cannot switch the gateway back to proceed.

  Throughout, the AI auditor was never run again.

  This step passed all its checks.

<!-- 2026-10-27 13:02 UTC -->
Lab 8 · How fast is it?

  How fast does this work? We make the evidence much larger, up to about a hundred thousand
  records, and time how long a requirement change takes to reach the gateway, 400 times over,
  against a 5-second limit.

<!-- 2026-10-27 13:05 UTC -->
Lab 8 · How fast is it? · what happened

  This step did not complete. In plain words: baseline verdicts are both SUCCESS at every size
  (main-14 §4.5). Nothing is lost: the attempt is recorded, and the step can be run again once
  the cause is fixed.

<!-- 2026-10-27 13:28 UTC -->
Lab 6 · Locking the experiment

  We lock the whole experiment: every file, every rule and every piece of code gets a
  fingerprint. From here on nothing can be adjusted to fit the results; any change would be
  detected.

<!-- 2026-10-27 13:28 UTC -->
Lab 6 · Locking the experiment · what happened

  The experiment is locked. Its fingerprint begins 5027e2dd7806. Every result from now on
  carries this fingerprint, so anyone can check that nothing was changed.

  This step passed all its checks.

<!-- 2026-10-27 13:28 UTC -->
Lab 7 · CDRT tests the decisions

  CDRT now tests the recorded decisions without running the auditor again. First it asks: did
  each decision follow the policy of its time? Then: is the evidence enough for today's
  requirement? Then the requirement changes, and we watch the gateway react.

<!-- 2026-10-27 13:29 UTC -->
Lab 7 · CDRT tests the decisions · what happened

  First question, did each decision follow the policy of its time? 4 of 5: yes.

  Second question, is the evidence enough for today? The chosen run alone checked 4/7: the
  gateway would say HOLD. 3 of the 5 GREEN runs were each too narrow on their own.

  CDRT then combines the qualified runs: together they checked 5/7, and the gateway says HOLD.
  The decision rests on independently tested, combined evidence, not on one GREEN verdict.

  Now the requirement changes: an independent second check is also required, which no run had.
  The past decisions still followed their own policy, but they are no longer enough: the
  gateway says HOLD.

  A late, outdated 'yes' from before the change arrives afterwards and is refused, so it
  cannot switch the gateway back to proceed.

  Throughout, the AI auditor was never run again.

  This step passed all its checks.

<!-- 2026-10-27 13:29 UTC -->
Lab 8 · How fast is it?

  How fast does this work? We make the evidence much larger, up to about a hundred thousand
  records, and time how long a requirement change takes to reach the gateway, 400 times over,
  against a 5-second limit.

<!-- 2026-10-27 13:32 UTC -->
Lab 8 · How fast is it? · what happened

  Even with 100,330 records of evidence, the slowest of all 400 updates reached the gateway in
  2.298 seconds, inside the 5-second limit.

  Every one of the 400 timed updates reached the gateway within the 5 s budget; the slowest
  took 2.30 s.

  This step passed all its checks.

<!-- 2026-10-27 13:32 UTC -->
Lab 9 · Writing the results into the paper

  Finally the results are written into the paper's tables and figures, straight from the
  locked records.

<!-- 2026-10-27 13:32 UTC -->
Lab 9 · Writing the results into the paper · what happened

  The paper's numbers, tables and figures are now generated directly from the locked records.

  Anyone can download the single public repository and repeat every step after the audit
  without the AI model.

  This step passed all its checks.

<!-- 2026-10-27 13:51 UTC -->
Lab 6 · Locking the experiment

  We lock the whole experiment: every file, every rule and every piece of code gets a
  fingerprint. From here on nothing can be adjusted to fit the results; any change would be
  detected.

<!-- 2026-10-27 13:51 UTC -->
Lab 6 · Locking the experiment · what happened

  The experiment is locked. Its fingerprint begins f26528d86fc2. Every result from now on
  carries this fingerprint, so anyone can check that nothing was changed.

  This step passed all its checks.

<!-- 2026-10-27 13:51 UTC -->
Lab 7 · CDRT tests the decisions

  CDRT now tests the recorded decisions without running the auditor again. First it asks: did
  each decision follow the policy of its time? Then: is the evidence enough for today's
  requirement? Then the requirement changes, and we watch the gateway react.

<!-- 2026-10-27 13:52 UTC -->
Lab 7 · CDRT tests the decisions · what happened

  First question, did each decision follow the policy of its time? 4 of 5: yes.

  Second question, is the evidence enough for today? The chosen run alone checked 4/7: the
  gateway would say HOLD. 3 of the 5 GREEN runs were each too narrow on their own.

  CDRT then combines the qualified runs: together they checked 5/7, and the gateway says HOLD.
  The decision rests on independently tested, combined evidence, not on one GREEN verdict.

  Now the requirement changes: an independent second check is also required, which no run had.
  The past decisions still followed their own policy, but they are no longer enough: the
  gateway says HOLD.

  A late, outdated 'yes' from before the change arrives afterwards and is refused, so it
  cannot switch the gateway back to proceed.

  Throughout, the AI auditor was never run again.

  This step passed all its checks.

<!-- 2026-10-27 13:52 UTC -->
Lab 8 · How fast is it?

  How fast does this work? We make the evidence much larger, up to about a hundred thousand
  records, and time how long a requirement change takes to reach the gateway, 400 times over,
  against a 5-second limit.

<!-- 2026-10-27 13:54 UTC -->
Lab 8 · How fast is it? · what happened

  Even with 100,330 records of evidence, the slowest of all 400 updates reached the gateway in
  1.435 seconds, inside the 5-second limit.

  Every one of the 400 timed updates reached the gateway within the 5 s budget; the slowest
  took 1.43 s.

  This step passed all its checks.

<!-- 2026-10-27 13:54 UTC -->
Lab 9 · Writing the results into the paper

  Finally the results are written into the paper's tables and figures, straight from the
  locked records.

<!-- 2026-10-27 13:54 UTC -->
Lab 9 · Writing the results into the paper · what happened

  The paper's numbers, tables and figures are now generated directly from the locked records.

  Anyone can download the single public repository and repeat every step after the audit
  without the AI model.

  This step passed all its checks.

<!-- 2026-10-27 15:24 UTC -->
Lab 6 · Locking the experiment

  We lock the whole experiment: every file, every rule and every piece of code gets a
  fingerprint. From here on nothing can be adjusted to fit the results; any change would be
  detected.

<!-- 2026-10-27 15:24 UTC -->
Lab 6 · Locking the experiment · what happened

  The experiment is locked. Its fingerprint begins 59af9d417b60. Every result from now on
  carries this fingerprint, so anyone can check that nothing was changed.

  This step passed all its checks.

<!-- 2026-10-27 15:24 UTC -->
Lab 7 · CDRT tests the decisions

  CDRT now tests the recorded decisions without running the auditor again. First it asks: did
  each decision follow the policy of its time? Then: is the evidence enough for today's
  requirement? Then the requirement changes, and we watch the gateway react.

<!-- 2026-10-27 15:24 UTC -->
Lab 7 · CDRT tests the decisions · what happened

  First question, did each decision follow the policy of its time? 4 of 5: yes.

  Second question, is the evidence enough for today? The chosen run alone checked 4/7: the
  gateway would say HOLD. 3 of the 5 GREEN runs were each too narrow on their own.

  CDRT then combines the qualified runs: together they checked 5/7, and the gateway says HOLD.
  The decision rests on independently tested, combined evidence, not on one GREEN verdict.

  Now the requirement changes: an independent second check is also required, which no run had.
  The past decisions still followed their own policy, but they are no longer enough: the
  gateway says HOLD.

  A late, outdated 'yes' from before the change arrives afterwards and is refused, so it
  cannot switch the gateway back to proceed.

  Throughout, the AI auditor was never run again.

  This step passed all its checks.

<!-- 2026-10-27 15:24 UTC -->
Lab 8 · How fast is it?

  How fast does this work? We make the evidence much larger, up to about a hundred thousand
  records, and time how long a requirement change takes to reach the gateway, 400 times over,
  against a 5-second limit.

<!-- 2026-10-27 15:27 UTC -->
Lab 8 · How fast is it? · what happened

  Even with 100,330 records of evidence, the slowest of all 400 updates reached the gateway in
  1.570 seconds, inside the 5-second limit.

  Every one of the 400 timed updates reached the gateway within the 5 s budget; the slowest
  took 1.57 s.

  This step passed all its checks.

<!-- 2026-10-27 15:27 UTC -->
Lab 9 · Writing the results into the paper

  Finally the results are written into the paper's tables and figures, straight from the
  locked records.

<!-- 2026-10-27 15:28 UTC -->
Lab 9 · Writing the results into the paper · what happened

  The paper's numbers, tables and figures are now generated directly from the locked records.

  Anyone can download the single public repository and repeat every step after the audit
  without the AI model.

  This step passed all its checks.

