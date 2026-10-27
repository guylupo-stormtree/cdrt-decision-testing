Lab 0 · Getting ready

  We are about to download python-dateutil, a real, widely used open-source library: about 899
  million downloads in the last month (pypistats.org, 26 October 2026).

  We audit one part of it: its date parser, the part that reads dates written as text. We will
  scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a value
  that may be empty (in Python, None) and crashing. First we mark, with our own independent
  analysis, the places in the code where such an empty value can be handed from one function
  to another. That is the area a careful audit has to look at.

Lab 0 · Getting ready · what happened

  The library is downloaded at exactly the published version we declared
  (https://github.com/dateutil/dateutil @ 10f317fde11c); its licence allows us to publish it
  with the results (LICENSE: Copyright 2017- Paul Ganssle <paul@ganssle.io>).

  Our own analysis, independent of the AI auditor, found 7 places where an empty value can be
  handed between functions; 5 of them form the auditor's own area of responsibility. A person
  reviewed and approved these lists before anything ran.

  The AI model will be gpt-4.1.

  This step passed all its checks.

