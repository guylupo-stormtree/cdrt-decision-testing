"""Record view on ProofWeave (R-REC-1 … R-REC-6).

Loading happens before any timing (R-REC-1): the corpus hash is recomputed and compared with the expected
one, the hash-chained ledger is verified, the graph is rebuilt from the ledger and compared with the
checkpoint. Any mismatch is an integrity finding and no records are served. A loaded view is an immutable
snapshot s = (corpus_sha256, ledger_head) (R-REC-2); CDRT never appends to it.

Decision records come only from ProofWeave's QueryAPI.decision() and basis() (R-REC-3); their `status`
(complete | partial | unavailable) is passed through, and only `complete` may establish absence.
Inside the timed path, `check_binding` recomputes the basis root from the snapshot's record hashes and
checks that the binding record is in the verified chain (R-REC-4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pwexp.hashing import manifest_hash, sha256_json, tree_manifest
from pwexp.proofweave.graph import InMemoryGraphStore, TargetIndex, Weaver
from pwexp.proofweave.ledger import Ledger
from pwexp.proofweave.query import COMPLETE, QueryAPI


class IntegrityFinding(Exception):
    """The corpus cannot be trusted as loaded. Not a policy violation of any decision."""


@dataclass(frozen=True)
class Snapshot:
    path: Path
    corpus_sha256: str
    ledger_head: tuple[int, str]
    allow_synthetic: bool
    store: InMemoryGraphStore = field(repr=False, compare=False)
    query: QueryAPI = field(repr=False, compare=False)
    record_hashes: frozenset[str] = field(repr=False, compare=False)
    log_utc_offset: str | None = None   # how RepoAudit's zone-less log times are read (bundle CAPTURE.json)
    missing_blobs: frozenset[str] = frozenset()   # native files absent from this copy: content unavailable

    @property
    def id(self) -> dict[str, Any]:
        return {"corpus_sha256": self.corpus_sha256, "ledger_head": list(self.ledger_head)}


def load_snapshot(corpus: Path, target: Path, expected_corpus_sha256: str | None = None,
                  allow_synthetic: bool = False, log_utc_offset: str | None = None) -> Snapshot:
    """Verify and load a sealed ProofWeave corpus (or a scale plane). Untimed."""
    corpus = Path(corpus)
    sha = manifest_hash(tree_manifest(corpus))
    if expected_corpus_sha256 and sha != expected_corpus_sha256:
        raise IntegrityFinding(f"corpus hash {sha[:12]} does not match the expected {expected_corpus_sha256[:12]}")
    ledger = Ledger(corpus)
    problems = ledger.verify()
    records = list(ledger.records())
    # An absent native file is unavailable content, not an altered record: it is passed on, never an integrity
    # finding. Any other problem (changed, removed or reordered record) is.
    missing = frozenset(r["source_ref"]["sha256"] for r in records
                        if (r.get("source_ref") or {}).get("sha256") and not (corpus / "blobs" / r["source_ref"]["sha256"]).exists())
    problems = [x for x in problems if "native blob" not in x]
    if problems:
        raise IntegrityFinding("ledger does not verify: " + "; ".join(problems[:3]))
    if not allow_synthetic and any(r.get("synthetic") for r in records):
        raise IntegrityFinding("synthetic records in a corpus loaded with allow_synthetic=false (R-REC-6)")
    store = InMemoryGraphStore.load(corpus / "graph-checkpoint.json")
    rebuilt = InMemoryGraphStore()
    Weaver(rebuilt, TargetIndex.from_snapshot(Path(target))).apply(records)
    if rebuilt.graph_hash() != store.graph_hash():
        raise IntegrityFinding("graph rebuilt from the ledger differs from the checkpoint")
    if log_utc_offset is None and (corpus.parent / "CAPTURE.json").is_file():
        import json
        log_utc_offset = json.loads((corpus.parent / "CAPTURE.json").read_text()).get("log_utc_offset")
    return Snapshot(corpus, sha, ledger.head, allow_synthetic, store=store, query=QueryAPI(store, ledger),
                    record_hashes=frozenset(r["record_hash"] for r in records), log_utc_offset=log_utc_offset,
                    missing_blobs=missing)


def get_decision(s: Snapshot, decision_id: str) -> dict[str, Any]:
    """The decision record exactly as ProofWeave resolves it; `status` passed through (R-REC-3)."""
    return s.query.decision(decision_id)


@dataclass(frozen=True)
class DecisionView:
    """One retrieval of a decision and its basis through the Query API, with the timed-path binding check,
    shared by the tests of one cycle (R-TST-5: one immutable view per cycle; the sharing is logged)."""
    decision_id: str
    decision: dict[str, Any] = field(repr=False)
    basis: tuple[dict[str, Any], ...] = field(repr=False)
    binding_ok: bool = False


def retrieve(s: Snapshot, decision_id: str) -> DecisionView:
    d = get_decision(s, decision_id)
    if d["status"] == "unavailable":
        return DecisionView(decision_id, d, ())
    basis = s.query.basis(decision_id)["records"]
    return DecisionView(decision_id, d, tuple(basis), check_binding(s, d, basis))


def list_decisions(s: Snapshot) -> list[str]:
    return s.query.decisions()


def check_binding(s: Snapshot, decision: dict[str, Any], basis: list[dict[str, Any]]) -> bool:
    """Timed-path check (R-REC-4): the binding record is in the verified chain and the basis root
    recomputed from the supplied basis records' hashes equals the recorded one."""
    b = decision.get("binding")
    if decision.get("status") != COMPLETE or not b or b["record_hash"] not in s.record_hashes:
        return False
    if any(r["record_hash"] not in s.record_hashes for r in basis):
        return False
    if any((r.get("source_ref") or {}).get("sha256") in s.missing_blobs for r in basis):
        return False                      # a basis record whose native bytes are unavailable is not verifiable
    return sha256_json(sorted(r["record_hash"] for r in basis)) == b["payload"]["basis_root"]
