"""One report (plain JSON-able dictionaries) from a data center: what is in it, what is wrong, how the racks and PDUs are loaded."""

from __future__ import annotations

from typing import Any

from dcimlite import check
from dcimlite.generate import Truth
from dcimlite.model import Model, allocated_w, summary_counts
from dcimlite.rules import RULES
from dcimlite.score import score

MAX_FINDINGS_KEPT = 200


def rack_rows(m: Model) -> list[dict[str, Any]]:
    conns = check.power_connections(m)
    shared, full = check.loads(m, conns)
    rows = []
    for name in sorted(m.racks):
        rack = m.racks[name]
        devs = [d for d in m.devices.values() if d.rack == name]
        occupied: set[int] = set()
        for d in devs:
            if d.height > 0:
                occupied.update(u for u in range(d.u, d.u + d.height) if 1 <= u <= rack.units)
        pdus = [
            {
                "name": d.name,
                "feed": d.feed,
                "capacity_w": d.capacity_w,
                "normal_w": shared.get(d.name, 0),
                "failover_w": full.get(d.name, 0),
            }
            for d in sorted(devs, key=lambda d: d.name)
            if d.kind == "pdu"
        ]
        rows.append(
            {
                "name": name,
                "units": rack.units,
                "used_u": len(occupied),
                "devices": sum(1 for d in devs if d.kind != "pdu"),
                "allocated_w": sum(allocated_w(d.nameplate_w) for d in devs if d.kind != "pdu"),
                "power_w": rack.power_w,
                "pdus": pdus,
            }
        )
    return rows


def build_report(m: Model, truth: Truth | None = None, source: str = "data center") -> dict[str, Any]:
    findings = check.check(m)
    by_rule = {r: 0 for r in RULES}
    for f in findings:
        by_rule[f.rule] += 1
    return {
        "kind": "report",
        "source": source,
        "summary": summary_counts(m),
        "findings": {
            "total": len(findings),
            "by_rule": by_rule,
            "shown": [{"rule": f.rule, "subject": f.subject, "detail": f.detail} for f in findings[:MAX_FINDINGS_KEPT]],
        },
        "racks": rack_rows(m),
        "accuracy": None if truth is None else score(findings, truth) | {"faults": [vars(f) for f in truth.faults]},
    }
