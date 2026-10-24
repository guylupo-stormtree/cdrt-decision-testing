"""Client for the gateway read interface (R-GW-1, R-GW-2)."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


class Gateway:
    """Starts `python -m cdrt.gateway.server` as a separate process on 127.0.0.1 and talks to it over HTTP."""

    def __init__(self):
        self.proc = subprocess.Popen([sys.executable, "-m", "cdrt.gateway.server"], stdout=subprocess.PIPE, text=True)
        line = self.proc.stdout.readline().strip()
        if not line.startswith("PORT "):
            self.proc.kill()
            raise RuntimeError(f"gateway did not start: {line!r}")
        self.url = f"http://127.0.0.1:{int(line.split()[1])}"

    def _call(self, path: str, body: dict | None = None, timeout: float = 70) -> tuple[int, dict[str, Any]]:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def publish(self, card: dict[str, Any]) -> None:
        self._call("/publish", card)

    def read(self, profile: str, revision: int | None = None, wait_s: float = 0.0) -> tuple[int, dict[str, Any]]:
        """The current posture; with `revision`, wait up to `wait_s` for a complete posture of that revision."""
        q = f"/posture?profile={profile}" + (f"&revision={revision}&wait={wait_s}" if revision is not None else "")
        return self._call(q, timeout=wait_s + 10)

    def timeouts(self) -> list[dict[str, Any]]:
        return self._call("/log")[1]["timeouts"]

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
