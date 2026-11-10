"""Markdown and figures built from a report or a benchmark (both are plain JSON)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dcimlite.rules import RULES

COLORS = {"blue": "#0072b2", "orange": "#d55e00", "green": "#009e73", "grey": "#666666", "pink": "#cc79a7"}
MAX_ROWS = 40


def pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def _t(s: float) -> str:
    if s < 1e-3:
        return f"{s * 1e6:.0f} us"
    if s < 1.0:
        return f"{s * 1e3:.1f} ms"
    return f"{s:.2f} s"


def render_report(rep: dict[str, Any]) -> str:
    s, f = rep["summary"], rep["findings"]
    kinds = ", ".join(f"{n} {k}" for k, n in s["by_kind"].items())
    out = [
        "# Data center report",
        "",
        f"Source: {rep['source']}. {s['racks']} racks, {s['devices']:,} devices ({kinds}), {s['ports']:,} ports and {s['cables']:,} cables.",
        "",
        "## 1. Findings",
        "",
    ]
    if f["total"] == 0:
        out += ["The checks found nothing.", ""]
    else:
        out += [f"{f['total']} findings.", "", "| Rule | Count | Meaning |", "|---|---|---|"]
        out += [f"| {r} | {n} | {RULES[r]} |" for r, n in f["by_rule"].items() if n]
        out += ["", "| Rule | Subject | Detail |", "|---|---|---|"]
        out += [f"| {x['rule']} | {x['subject']} | {x['detail']} |" for x in f["shown"][:MAX_ROWS]]
        if f["total"] > MAX_ROWS:
            out += ["", f"The first {MAX_ROWS} of {f['total']:,} findings are listed."]
        out.append("")
    out += [
        "## 2. Racks and power",
        "",
        "| Rack | Units used | Devices | Allocated | Rack limit | PDUs (normal / alone / capacity, W) |",
        "|---|---|---|---|---|---|",
    ]
    for r in rep["racks"][:MAX_ROWS]:
        pdus = "; ".join(
            f"{p['feed']}: {p['normal_w']:,} / {p['failover_w']:,} / {p['capacity_w']:,}" for p in r["pdus"]
        )
        out.append(
            f"| {r['name']} | {r['used_u']} of {r['units']} | {r['devices']} | {r['allocated_w']:,} W | {r['power_w']:,} W | {pdus} |"
        )
    if len(rep["racks"]) > MAX_ROWS:
        out += ["", f"The first {MAX_ROWS} of {len(rep['racks'])} racks are listed."]
    acc = rep["accuracy"]
    if acc:
        out += [
            "",
            "## 3. Against the injected faults",
            "",
            f"{acc['injected']} faults were injected; {acc['found']} were reported, {len(acc['missed'])} missed, {len(acc['extra'])} reports were not an injected fault.",
            "",
            "| Rule | Injected | Found | Missed | Extra |",
            "|---|---|---|---|---|",
        ]
        out += [
            f"| {r} | {v['injected']} | {v['found']} | {v['missed']} | {v['extra']} |"
            for r, v in acc["rules"].items()
            if v["injected"] or v["extra"]
        ]
    return "\n".join(out) + "\n"


def report_figure(rep: dict[str, Any], path: Path) -> None:
    racks = rep["racks"][:60]
    names = [r["name"] for r in racks]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4), constrained_layout=True)
    ax[0].bar(names, [100 * r["used_u"] / r["units"] for r in racks], color=COLORS["blue"])
    ax[0].set_title("Rack units in use")
    ax[0].set_ylabel("% of the rack")
    ax[0].set_ylim(0, 100)
    ax[1].bar(names, [100 * r["allocated_w"] / r["power_w"] for r in racks], color=COLORS["orange"])
    ax[1].axhline(100, color=COLORS["grey"], linestyle=":", linewidth=1)
    ax[1].set_title("Power allocated in the rack")
    ax[1].set_ylabel("% of what the rack may draw")
    worst = [
        max((100 * p["failover_w"] / p["capacity_w"] for p in r["pdus"] if p["capacity_w"]), default=0.0) for r in racks
    ]
    ax[2].bar(names, worst, color=COLORS["green"])
    ax[2].axhline(100, color=COLORS["grey"], linestyle=":", linewidth=1)
    ax[2].set_title("Worst PDU if the other feed failed")
    ax[2].set_ylabel("% of its capacity")
    for a in ax:
        a.tick_params(axis="x", labelrotation=90, labelsize=7)
        a.spines[["top", "right"]].set_visible(False)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def render_bench(b: dict[str, Any]) -> str:
    env = b["environment"]
    acc = b["accuracy"]["summary"]
    out = [
        "# Benchmark",
        "",
        f"Run on {env['system']}, {env['cpus']} CPUs, Python {env['python']}; seed {env['seed']}; each time is the median of {env['repeat']} runs; command `{env['command']}`.",
        "",
        "## 1. Checking time by size",
        "",
        "Synthetic data centers (racks with a switch, a patch panel, two PDUs and servers cabled to all of them), without faults. The time is that of `check` on the data center in memory.",
        "",
        "| Devices | Racks | Ports | Cables | Time | Devices per second |",
        "|---|---|---|---|---|---|",
    ]
    out += [
        f"| {r['devices']:,} | {r['racks']:,} | {r['ports']:,} | {r['cables']:,} | {_t(r['seconds'])} | {r['devices'] / r['seconds']:,.0f} |"
        for r in b["checks"]
    ]
    out += [
        "",
        "## 2. Against the literal implementation, on the same data centers",
        "",
        "| Devices | Indexed | Literal | Ratio |",
        "|---|---|---|---|",
    ]
    out += [
        f"| {r['devices']:,} | {_t(r['indexed'])} | {_t(r['literal'])} | {r['literal'] / r['indexed']:.1f}x |"
        for r in b["literal"]
    ]
    out += ["", "## 3. SQLite", "", "| Devices | Cables | Save | Load | File size |", "|---|---|---|---|---|"]
    out += [
        f"| {r['devices']:,} | {r['cables']:,} | {_t(r['save'])} | {_t(r['load'])} | {r['bytes'] / 1e6:,.1f} MB |"
        for r in b["database"]
    ]
    out += [
        "",
        f"## 4. Faults found, over {acc['data_centers']} synthetic data centers",
        "",
        f"Seeds 1 to {acc['data_centers']}; each data center is built consistent ({acc['clean_models']} of them were checked before any fault went in: {acc['clean_findings']} findings), "
        f"then faults of the 12 kinds are injected at random places (0 to 2 of each kind). {acc['injected']} faults were injected: {acc['found']} were reported, {acc['missed']} missed, "
        f"and {acc['extra']} reports were not an injected fault. Recall {pct(acc['recall'])}, precision {pct(acc['precision'])}.",
        "",
        "| Rule | Injected | Found | Missed | Extra |",
        "|---|---|---|---|---|",
    ]
    out += [f"| {r} | {v['injected']} | {v['found']} | {v['missed']} | {v['extra']} |" for r, v in acc["rules"].items()]
    v = b["verification"]
    out += [
        "",
        "## 5. Agreement with the literal implementation",
        "",
        f"{v['checks']} comparisons (a generated data center and {v['checks'] - 1} random broken ones): {v['findings']:,} findings compared. "
        + ("All match." if v["ok"] else f"{v['bad']} DIFFER."),
        "",
    ]
    return "\n".join(out)


def bench_figure(b: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4), constrained_layout=True)
    n = [r["devices"] for r in b["checks"]]
    ax[0].plot(n, [r["seconds"] for r in b["checks"]], "o-", color=COLORS["blue"], label="indexed")
    ax[0].plot(
        [r["devices"] for r in b["literal"]],
        [r["literal"] for r in b["literal"]],
        "s--",
        color=COLORS["grey"],
        label="literal",
    )
    ax[0].set_xscale("log")
    ax[0].set_yscale("log")
    ax[0].set_title("Checking time")
    ax[0].set_xlabel("devices")
    ax[0].set_ylabel("seconds")
    ax[0].legend()
    rules = b["accuracy"]["summary"]["rules"]
    xs = range(len(rules))
    ax[1].bar(
        [i - 0.2 for i in xs], [v["injected"] for v in rules.values()], 0.4, color=COLORS["grey"], label="injected"
    )
    ax[1].bar([i + 0.2 for i in xs], [v["found"] for v in rules.values()], 0.4, color=COLORS["green"], label="found")
    ax[1].set_xticks(list(xs), list(rules), rotation=90, fontsize=7)
    ax[1].set_title("Faults injected and found")
    ax[1].legend()
    db = b["database"]
    ax[2].bar([i - 0.2 for i in range(len(db))], [r["save"] for r in db], 0.4, color=COLORS["orange"], label="save")
    ax[2].bar([i + 0.2 for i in range(len(db))], [r["load"] for r in db], 0.4, color=COLORS["blue"], label="load")
    ax[2].set_xticks(range(len(db)), [f"{r['devices']:,}" for r in db])
    ax[2].set_title("SQLite")
    ax[2].set_xlabel("devices")
    ax[2].set_ylabel("seconds")
    ax[2].legend()
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    fig.savefig(path, dpi=130)
    plt.close(fig)
