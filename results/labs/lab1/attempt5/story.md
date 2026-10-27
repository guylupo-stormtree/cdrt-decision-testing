Lab 1 · A first look (pilot)

  RepoAudit now audits the library 5 times, as a first look, using the AI model gpt-4.1. Each
  run ends with a verdict: GREEN means no bug found.

  From these first runs we fix the auditor's own policy, the standard it was held to at the
  time, before the real audit starts. Once fixed, it cannot be changed.

Lab 1 · A first look (pilot) · what happened

  All 5 first runs are in: 1 said GREEN, no bugs found; 4 reported possible bugs, and not the
  same ones.

  But they did not check the same amount: of the auditor's area they covered 3/5, 4/5, 4/5,
  1/5, 2/5.

  From these runs the auditor's policy is now fixed: a run must cover at least 2/5 (40%) of
  its area. This policy, and the number of runs, are locked in at the start of the real audit.

  Each run asked the AI model 147 to 163 questions and took 6 to 7 minutes.

  This step passed all its checks.

