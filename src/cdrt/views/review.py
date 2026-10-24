"""Read-only review pages for Lab 4: the recorded decisions, and the pathways behind each GREEN decision.

Self-contained HTML (no scripts, light and dark). Built from the record view only. The pathway page shows,
for every decision's RepoAudit run on the same target and bug type, each step where RepoAudit carried a
None from one function into the next (pwexp QueryAPI.pathway), and marks the functions of the auditor's
scope M_h it reached that way. Those are the functions a base-check can count.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from ..records.view import Snapshot, get_decision, list_decisions

CSS = """
:root{--bg:#f6f7f9;--fg:#17202a;--mut:#4b5563;--card:#fff;--line:#dde1e6;--g:#0f766e;--gb:#ecfdf5;--r:#b91c1c;--rb:#fef2f2;--hl:#eef2ff}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--fg:#e5e7eb;--mut:#9ca3af;--card:#1a1f26;--line:#2d333b;--g:#5eead4;--gb:#0f2e2a;--r:#fca5a5;--rb:#3a1a1a;--hl:#1e2433}}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 56px} h1{font-size:24px;margin:0 0 4px} h2{font-size:18px;margin:28px 0 8px}
.m{color:var(--mut);font-size:13px} .tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13px} th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
td.w{white-space:normal} .y{color:var(--g);font-weight:700;text-align:center} .n{color:var(--r);text-align:center}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-weight:600;font-size:12px}.g{color:var(--g);background:var(--gb)}.r{color:var(--r);background:var(--rb)}
code{font-family:ui-monospace,monospace;font-size:12px} th.in{background:var(--hl)}
"""


def _page(title: str, body: str, watermark: str) -> str:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{CSS}</style></head>"
            f"<body><main><h1>{html.escape(title)}</h1><p class='m'>{html.escape(watermark)}</p>{body}</main></body></html>")


def _badge(v: str) -> str:
    return f"<span class='badge {'g' if v == 'green' else 'r'}'>{'GREEN' if v == 'green' else 'not green'}</span>"


def decisions_page(s: Snapshot, out: Path, watermark: str) -> Path:
    e = html.escape
    rows = []
    for d in list_decisions(s):
        rec = get_decision(s, d)
        dp, bp = rec["decision"]["payload"], rec["binding"]["payload"]
        ip, pp = rec["intent"]["payload"], rec["policy"]["payload"]
        content = pp.get("content", {})
        rows.append(f"<tr><td><code>{e(d)}</code></td><td>{_badge(dp['verdict'])}</td><td>{e(rec['status'])}</td>"
                    f"<td><code>{e(pp['id'])}@{e(str(pp['version']))}</code></td>"
                    f"<td class='w'>{e(', '.join(content.get('validators', [])))}; threshold "
                    f"{e(json.dumps(content.get('threshold')))}</td>"
                    f"<td class='w'>{e(', '.join(f'{r} ' + ('GREEN' if g else 'not GREEN') for r, g in dp['per_run'].items()))}</td>"
                    f"<td>{bp['basis_count']}</td><td><code>{e(bp['basis_root'][:12])}</code></td>"
                    f"<td class='w'>{e(ip['action'])} {e(ip['repo'])}@{e(str(ip['commit'])[:12])} · {e(ip['bug_type'])} · "
                    f"scope <code>{e(ip['scope_ref']['file'])}</code></td>"
                    f"<td class='w m'>context {e(dp['context_written_at'])}<br>decided {e(dp['decided_at'])}</td></tr>")
    body = (f"<p class='m'>Corpus {e(s.corpus_sha256)} · ledger head {s.ledger_head[0]} · {e(s.ledger_head[1][:16])}</p>"
            "<div class='tw'><table><thead><tr><th>Decision</th><th>Verdict</th><th>Binding</th><th>Policy-at-event</th>"
            "<th>Policy requires</th><th>Basis runs</th><th>Basis records</th><th>Basis root</th><th>Intent</th>"
            "<th>Order</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")
    out.write_text(_page("Recorded decisions", body, watermark))
    return out


def _scope(policy: dict[str, Any], root: Path) -> list[str]:
    ref = (policy.get("content") or {}).get("manifest") or {}
    f = root / ref.get("file", "")
    return json.loads(f.read_text()).get("functions", []) if ref.get("file") and f.is_file() else []


def pathways_page(s: Snapshot, out: Path, protocol_dir: Path, watermark: str) -> Path:
    """Pathway × decision table for the RepoAudit run of every decision, plus reached-scope counts."""
    e = html.escape
    cols, paths, scope = [], {}, []
    for d in list_decisions(s):
        rec = get_decision(s, d)
        ra = [r for r in rec["decision"]["payload"]["basis_runs"] if not r.startswith("semgrep/")]
        if not ra:
            continue
        run = ra[0]
        cols.append((d, run, rec["decision"]["payload"]["verdict"]))
        paths[d] = s.query.pathway(run)
        scope = scope or _scope(rec["policy"]["payload"], protocol_dir)
    steps = sorted({k for p in paths.values() for k in p}, key=lambda k: (-sum(k in paths[d] for d, _, _ in cols), k))
    head = "".join(f"<th class='in'><code>{e(d)}</code><br><span class='m'>{e(run)}</span><br>{_badge(v)}</th>"
                   for d, run, v in cols)
    rows = "".join(
        f"<tr><td class='w'>{e(a.removeprefix('fn:').split('::')[-1])}() → {e(b.removeprefix('fn:').split('::')[-1])}() "
        f"<span class='m'>({e(paths[next(d for d, _, _ in cols if (a, b) in paths[d])][(a, b)]['via'])})</span></td>"
        + "".join(f"<td class='{'y' if (a, b) in paths[d] else 'n'}'>{'✓' if (a, b) in paths[d] else '✗'}</td>"
                  for d, _, _ in cols) + "</tr>" for a, b in steps)
    reach = []
    for fn in scope:
        reach.append(f"<tr><td><code>{e(fn)}</code></td>" + "".join(
            f"<td class='{'y' if any(b == 'fn:' + fn for _, b in paths[d]) else 'n'}'>"
            f"{'✓' if any(b == 'fn:' + fn for _, b in paths[d]) else '✗'}</td>" for d, _, _ in cols) + "</tr>")
    total = "".join(f"<td><b>{sum(any(b == 'fn:' + fn for _, b in paths[d]) for fn in scope)}/{len(scope)}</b></td>"
                    for d, _, _ in cols)
    body = ("<p>Every column is one recorded decision's RepoAudit run on the same target and bug type. A row is one "
            "step RepoAudit took while following a None: from one function into the next, which it then analysed.</p>"
            f"<h2>Pathways</h2><div class='tw'><table><thead><tr><th>Pathway step</th>{head}</tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
            "<h2>Scope M_h reached by following a None</h2><p class='m'>A function of the auditor's scope counts for "
            "base-check only when the run followed a None into it.</p>"
            f"<div class='tw'><table><thead><tr><th>Function in M_h</th>{head}</tr></thead><tbody>{''.join(reach)}"
            f"<tr><td><b>reached</b></td>{total}</tr></tbody></table></div>")
    out.write_text(_page("Pathways behind the recorded decisions", body, watermark))
    return out
