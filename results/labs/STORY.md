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

