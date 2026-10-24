"""R-DEP-2: CDRT imports only the allow-listed parts of pwexp, never pwexp's oracle, and never the workbench."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
ALLOWED = ("pwexp.proofweave", "pwexp.hashing", "pwexp.chain", "pwexp.stages.stage1_acquire",
           "pwexp.stages.stage2_timing")
CHECKED = ("src/cdrt", "harness", "oracle", "report")


def _imports(path: Path) -> list[str]:
    out = []
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            out.append(n.module)
    return out


def test_import_allow_list():
    bad = []
    for d in CHECKED:
        for p in (ROOT / d).rglob("*.py"):
            for m in _imports(p):
                top = m.split(".")[0]
                if top == "pwexp" and m != "pwexp" and not m.startswith(ALLOWED):
                    bad.append(f"{p.relative_to(ROOT)}: {m}")
                if m == "pwexp" or top in ("oracle", "cdrt_workbench"):
                    bad.append(f"{p.relative_to(ROOT)}: {m}")
    assert not bad, "forbidden imports:\n" + "\n".join(bad)


def test_oracle_uses_standard_library_only():
    import sys
    for p in (ROOT / "oracle").rglob("*.py"):
        for m in _imports(p):
            assert m.split(".")[0] in sys.stdlib_module_names, f"{p.name} imports {m}"
