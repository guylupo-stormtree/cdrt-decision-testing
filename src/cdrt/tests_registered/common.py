"""Shared arithmetic for the registered decision tests (Eqs. 3-6). Exact fractions; no rounding.

Inputs are the projected assessment records {target, validator, record_ids, time}. W(Sigma, M) is the set of
targets in M with an accepted base-check (the control's own assessment); the other listed validators
corroborate the covered targets (Eq. 4). Duplicate records for one target never raise the numerator.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
from typing import Any

SUCCESS, FAIL, INCONCLUSIVE = "SUCCESS", "FAIL", "INCONCLUSIVE"
BASE = "base-check"


def frac(x: dict[str, Any]) -> Fraction:
    return Fraction(int(x["numerator"]), int(x["denominator"]))


def by_validator(records: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for r in records:
        out.setdefault(r["validator"], {}).setdefault(r["target"], []).append(r)
    return out


def licence(records: list[dict[str, Any]], scope: list[str], tau: Fraction, validators: list[str]) -> dict[str, Any]:
    acc = by_validator(records)
    covered = sorted(u for u in set(scope) if u in acc.get(BASE, {}))
    n, d = len(covered), len(set(scope))
    coverage = Fraction(n, d) if d else Fraction(0)
    missing = {u: [v for v in validators if u not in acc.get(v, {})] for u in covered}
    missing = {u: m for u, m in sorted(missing.items()) if m}
    support = {u: sorted({i for v in validators for r in acc.get(v, {}).get(u, []) for i in r["record_ids"]})
               for u in covered}
    per_validator = {v: sum(1 for m in missing.values() if v in m) for v in validators}
    return {"coverage_numerator": n, "coverage_denominator": d, "coverage_ok": coverage >= tau,
            "threshold": f"{tau.numerator}/{tau.denominator}", "corroboration_ok": not missing,
            "missing_validator_targets": len(missing), "missing_by_validator": per_validator,
            "missing_first_10": [{"target": u, "validators": m} for u, m in list(missing.items())[:10]],
            "support": support, "covered": covered}


def parse_utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(timezone.utc) if t.tzinfo else None
