Lab 0 · Getting ready

  We are about to download python-dateutil, a real, widely used open-source library: about 899
  million downloads in the last month (pypistats.org, 26 October 2026).

  We will scan it with RepoAudit, an AI code auditor, for one kind of bug: a program using a
  value that may be empty (in Python, None) and crashing. First we mark, with our own
  independent analysis, the places in the code where such an empty value can be handed from
  one function to another. That is the area a careful audit has to look at.

Lab 0 · Getting ready · what happened

  Our own analysis, independent of the AI auditor, has drafted the list of places to check: 12
  places where an empty value can be handed between functions, 9 of them in the auditor's own
  area of responsibility.

  Before anything runs, a person reviews and approves this list. Then this step is run again.

