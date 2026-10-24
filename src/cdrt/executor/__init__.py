"""Common executor (R-RES-2, R-EXE-1).

Projects the record view down to the test's declared input fields, then runs the approved test in a forked
child process with a wall-time limit and an address-space limit. The child receives the projected inputs
by copy and holds no handle to the ledger or the graph. A crash, timeout or malformed output is an
execution failure with state None. The code digest is re-checked before every invocation (R-REG-1).
"""
from __future__ import annotations

import importlib
import json
import multiprocessing as mp
import resource
from typing import Any

from ..registry import Entry, code_digest
from ..tests_registered.common import FAIL, INCONCLUSIVE, SUCCESS

STATES = {SUCCESS, FAIL, INCONCLUSIVE}


def _child(conn, module: str, inputs: dict, params: dict, memory_mb: int) -> None:
    try:
        lim = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
        out = importlib.import_module(module).evaluate(inputs, params)
        conn.send(json.dumps(out, sort_keys=True))
    except BaseException as e:  # noqa: BLE001  any failure inside the test is a crash
        conn.send(json.dumps({"__crash__": f"{type(e).__name__}: {e}"}))
    finally:
        conn.close()


def execute(entry: Entry, inputs: dict[str, Any], params: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """(execution_status, output): status ok | crash | timeout | malformed | digest-mismatch."""
    if code_digest(entry.code) != entry.code_digest:
        return "digest-mismatch", None
    projected = {k: inputs.get(k) for k in entry.inputs}
    ctx = mp.get_context("fork")
    a, b = ctx.Pipe(duplex=False)
    p = ctx.Process(target=_child, args=(b, entry.module, projected, params, int(entry.limits.get("memory_mb", 4096))))
    p.start()
    b.close()
    wall = float(entry.limits.get("wall_seconds", 60))
    if not a.poll(wall):
        p.kill()
        p.join()
        return "timeout", None
    try:
        raw = a.recv()
    except EOFError:
        p.join()
        return "crash", None
    p.join()
    try:
        out = json.loads(raw)
    except ValueError:
        return "malformed", None
    if "__crash__" in out:
        return "crash", {"error": out["__crash__"]}
    if not isinstance(out, dict) or out.get("state") not in STATES or not all(k in out for k in entry.result):
        return "malformed", None
    return "ok", out
