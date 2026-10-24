"""Gateway read interface: a separate process on 127.0.0.1 (R-GW-1, R-GW-2). Nothing is released.

POST /publish                      store a posture card (the consumer publishes after every change)
GET  /posture?profile=P            the latest card for P and the stub decision
GET  /posture?profile=P&revision=N&wait=S
                                   wait up to S seconds for a complete card of revision N or later; past
                                   that, record a timeout. A card of an earlier revision is never served
                                   in its place, so a superseded green posture cannot be read.
GET  /log                          the recorded timeouts
Stub gateway policy: SUCCESS → proceed, FAIL → hold, anything else → no-green.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CARDS: dict[str, dict] = {}
TIMEOUTS: list[dict] = []
COND = threading.Condition()


def stub_policy(card: dict | None) -> str:
    agg = (card or {}).get("aggregate")
    return "proceed" if agg == "SUCCESS" and card.get("complete") else "hold" if agg == "FAIL" else "no-green"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, doc: dict) -> None:
        body = json.dumps(doc, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        card = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        with COND:
            CARDS[card.get("profile_id")] = card
            COND.notify_all()
        self._send(200, {"stored": True})

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/log":
            return self._send(200, {"timeouts": TIMEOUTS})
        prof = q.get("profile")
        if "revision" not in q:
            with COND:
                card = CARDS.get(prof)
            return self._send(200, {"card": card, "gateway": stub_policy(card)})
        rev, deadline = int(q["revision"]), time.monotonic() + float(q.get("wait", 0))
        with COND:
            while True:
                card = CARDS.get(prof)
                if card and (card.get("profile_revision") or -1) >= rev and card.get("complete"):
                    return self._send(200, {"card": card, "gateway": stub_policy(card)})
                left = deadline - time.monotonic()
                if left <= 0:
                    TIMEOUTS.append({"profile": prof, "revision": rev, "time": time.time()})
                    return self._send(504, {"timeout": True, "gateway": "no-green"})
                COND.wait(left)


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(f"PORT {srv.server_address[1]}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
