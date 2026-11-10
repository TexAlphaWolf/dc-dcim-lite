"""Score the findings of the checks against the faults that were injected."""

from __future__ import annotations

from typing import Any

from dcimlite.generate import Truth
from dcimlite.rules import RULES, Finding, keys


def score(findings: list[Finding], truth: Truth) -> dict[str, Any]:
    """Per rule: how many faults were injected, how many of them were reported, how many reports were not an injected fault."""
    expected = truth.expected()
    got = set(keys(findings))
    out: dict[str, Any] = {}
    for rule in RULES:
        want = {k for k in expected if k[0] == rule}
        have = {k for k in got if k[0] == rule}
        out[rule] = {
            "injected": len(want),
            "found": len(want & have),
            "missed": len(want - have),
            "extra": len(have - want),
        }
    return {
        "rules": out,
        "injected": len(expected),
        "found": len(expected & got),
        "missed": sorted(expected - got),
        "extra": sorted(got - expected),
    }


def summarize(cases: list[dict[str, Any]], clean_findings: int, clean_models: int) -> dict[str, Any]:
    """Add up the scores of many simulated data centers."""
    rules = {r: {"injected": 0, "found": 0, "missed": 0, "extra": 0} for r in RULES}
    for c in cases:
        for r in RULES:
            for k in ("injected", "found", "missed", "extra"):
                rules[r][k] += c["rules"][r][k]
    injected = sum(v["injected"] for v in rules.values())
    found = sum(v["found"] for v in rules.values())
    extra = sum(v["extra"] for v in rules.values())
    return {
        "data_centers": len(cases),
        "injected": injected,
        "found": found,
        "missed": injected - found,
        "extra": extra,
        "recall": found / injected if injected else None,
        "precision": found / (found + extra) if found + extra else None,
        "rules": rules,
        "clean_models": clean_models,
        "clean_findings": clean_findings,
    }
