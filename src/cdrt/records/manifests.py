"""Scope manifests (M_h, M_q), supplied separately from what the control reported (manuscript Sec. 3.5).

A manifest is referenced by {file or id, sha256}; it resolves only when a file with exactly that digest is
in the store. The store holds the frozen bundle's protocol manifests and the fixture manifests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pwexp.hashing import sha256_file


class ManifestStore:
    def __init__(self, *dirs: Path):
        self.by_sha: dict[str, list[str]] = {}
        self.by_id: dict[str, str] = {}
        for d in dirs:
            for f in sorted(Path(d).rglob("*.json")) if Path(d).is_dir() else []:
                try:
                    doc = json.loads(f.read_text())
                except ValueError:
                    continue
                if isinstance(doc, dict) and isinstance(doc.get("functions"), list):
                    sha = sha256_file(f)
                    self.by_sha[sha] = list(doc["functions"])
                    if doc.get("id"):
                        self.by_id[doc["id"]] = sha

    def resolve(self, ref: dict[str, Any] | None) -> tuple[list[str] | None, str | None]:
        """(functions, sha256) or (None, the requested sha) when unresolvable."""
        if not ref:
            return None, None
        sha = ref.get("sha256") or self.by_id.get(ref.get("id", ""))
        return (self.by_sha.get(sha), sha) if sha else (None, None)
