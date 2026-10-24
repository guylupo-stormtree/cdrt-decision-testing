"""Gateway read interface in its own process (R-GW-1, R-GW-2)."""
from __future__ import annotations

from cdrt.gateway import Gateway


def card(rev, agg, complete=True):
    return {"profile_id": "p", "profile_revision": rev, "aggregate": agg, "complete": complete, "leaves": {}}


def test_gateway_serves_only_the_requested_revision_and_records_timeouts():
    with Gateway() as g:
        g.publish(card(2, "SUCCESS"))
        assert g.read("p")[1]["gateway"] == "proceed"
        code, body = g.read("p", revision=3, wait_s=0.3)
        assert code == 504 and body["gateway"] == "no-green"            # rev-2 green is never served for rev 3
        g.publish(card(3, "INCONCLUSIVE", complete=False))                # support withdrawn, assessment pending
        assert g.read("p")[1]["gateway"] == "no-green"
        assert g.read("p", revision=3, wait_s=0.3)[0] == 504
        g.publish(card(3, "FAIL"))
        code, body = g.read("p", revision=3, wait_s=1)
        assert code == 200 and body["gateway"] == "hold" and body["card"]["profile_revision"] == 3
        assert len(g.timeouts()) == 2
