"""Decision-test registry (R-REG-1, R-REG-2).

entries.yaml lists approved test versions with their declared input fields, parameter and result schemas,
prerequisites, limits, result meanings and the code digest (sha256 over the code files, package-relative).
Only an approved entry whose digest matches can execute; the digest is checked at load and again at every
invocation. A failed lookup is an explicit execution status and never gives positive support.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pwexp.hashing import sha256_file, sha256_json

PKG = Path(__file__).resolve().parents[1]           # src/cdrt
ENTRIES = Path(__file__).with_name("entries.yaml")


class LookupFailure(Exception):
    pass


@dataclass(frozen=True)
class Entry:
    id: str
    version: str
    module: str
    code: tuple[str, ...]
    code_digest: str
    inputs: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict, compare=False)
    result: tuple[str, ...] = ("state", "measurements", "reasons")
    prerequisites: tuple[str, ...] = ()
    limits: dict[str, Any] = field(default_factory=dict, compare=False)
    meanings: dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


def code_digest(files: tuple[str, ...] | list[str]) -> str:
    return sha256_json({f: sha256_file(PKG / f) for f in sorted(files)})


class Registry:
    def __init__(self, path: Path = ENTRIES):
        doc = yaml.safe_load(Path(path).read_text())
        self.entries: dict[str, Entry] = {}
        self.rejected: dict[str, str] = {}
        for e in doc["entries"]:
            ref = f"{e['id']}@{e['version']}"
            if not e.get("approved"):
                self.rejected[ref] = "not approved"
                continue
            entry = Entry(e["id"], str(e["version"]), e["module"], tuple(e["code"]), e["code_digest"],
                          tuple(e["inputs"]), e.get("parameters", {}), tuple(e.get("result", ("state", "measurements", "reasons"))),
                          tuple(e.get("prerequisites", ())), e.get("limits", {}), e.get("meanings", {}))
            if code_digest(entry.code) != entry.code_digest:
                self.rejected[ref] = "code digest does not match the approved digest"
                continue
            self.entries[ref] = entry

    def lookup(self, ref: str) -> Entry:
        if ref in self.rejected:
            raise LookupFailure(f"{ref}: {self.rejected[ref]}")
        if ref not in self.entries:
            raise LookupFailure(f"{ref}: not registered")
        return self.entries[ref]

    def describe(self) -> list[dict[str, Any]]:
        return [{"ref": e.ref, "code_digest": e.code_digest, "inputs": list(e.inputs), "limits": e.limits}
                for e in self.entries.values()]
