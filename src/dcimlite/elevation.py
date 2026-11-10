"""Rack elevations as SVG (written by hand: no dependency)."""

from __future__ import annotations

from html import escape

from dcimlite.model import Model
from dcimlite.rules import Finding

UNIT_H = 12
RACK_W = 168
GAP = 28
HEAD = 30
PDU_W = 7
FILL = {"server": "#4c78a8", "switch": "#59a14f", "storage": "#f28e2b", "patch": "#b07aa1", "other": "#999999"}
FEED_FILL = {"A": "#d55e00", "B": "#0072b2"}
MAX_RACKS = 60


def flagged_devices(m: Model, findings: list[Finding]) -> set[str]:
    """The devices a list of findings points at (a device, a pair of devices, a PDU, or the owner of a port or of a cable's end)."""
    out: set[str] = set()
    for f in findings:
        if f.rule == "overlap":
            out.update(f.subject.split("|"))
        elif f.rule == "double_connected":
            out.add(f.subject.split(":", 1)[0])
        elif f.rule in ("open_cable", "kind_mismatch", "self_loop"):
            c = m.cables.get(int(f.subject.split(":", 1)[1]))
            if c is not None:
                out.add(c.a_device)
                if c.b_device is not None:
                    out.add(c.b_device)
        elif f.rule != "rack_power":
            out.add(f.subject)
    return out


def elevation_svg(
    m: Model, racks: list[str] | None = None, findings: list[Finding] | None = None, per_row: int = 8
) -> str:
    names = [r for r in (racks if racks is not None else sorted(m.racks)) if r in m.racks][:MAX_RACKS]
    flagged = flagged_devices(m, findings or [])
    bad_racks = {f.subject for f in (findings or []) if f.rule == "rack_power"}
    tallest = max((m.racks[r].units for r in names), default=0)
    row_h = HEAD + tallest * UNIT_H + 2 * UNIT_H + GAP
    rows = (len(names) + per_row - 1) // per_row
    width = min(len(names), per_row) * (RACK_W + GAP) + GAP
    height = max(rows, 1) * row_h + GAP
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'font-family="Helvetica, Arial, sans-serif" role="img" aria-label="Rack elevations">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    by_rack: dict[str, list[str]] = {}
    for d in m.devices.values():
        by_rack.setdefault(d.rack, []).append(d.name)
    for i, r in enumerate(names):
        rack = m.racks[r]
        x0 = GAP + (i % per_row) * (RACK_W + GAP)
        y0 = GAP + (i // per_row) * row_h + HEAD
        h = rack.units * UNIT_H
        color = "#c00000" if r in bad_racks else "#222222"
        out.append(f'<text x="{x0}" y="{y0 - 10}" font-size="12" font-weight="bold" fill="{color}">{escape(r)}</text>')
        out.append(
            f'<rect x="{x0}" y="{y0}" width="{RACK_W}" height="{h}" fill="#f4f4f4" stroke="{color}" stroke-width="1.5"/>'
        )
        for u in range(1, rack.units + 1):
            if u % 5 == 0:
                y = y0 + h - u * UNIT_H
                out.append(f'<text x="{x0 - 4}" y="{y + 9}" font-size="7" text-anchor="end" fill="#888888">{u}</text>')
        pdus = sorted(n for n in by_rack.get(r, []) if m.devices[n].kind == "pdu")
        for n in pdus:
            d = m.devices[n]
            px = x0 - PDU_W - 1 if d.feed == "A" else x0 + RACK_W + 1
            stroke = ' stroke="#c00000" stroke-width="2"' if n in flagged else ""
            out.append(
                f'<rect x="{px}" y="{y0}" width="{PDU_W}" height="{h}" fill="{FEED_FILL.get(d.feed, "#999999")}"{stroke}>'
                f"<title>{escape(n)} (feed {escape(d.feed)}, {d.capacity_w} W)</title></rect>"
            )
        for n in sorted(by_rack.get(r, [])):
            d = m.devices[n]
            if d.height < 1:
                continue
            top = d.u + d.height - 1
            y = y0 + h - top * UNIT_H
            stroke = 'stroke="#c00000" stroke-width="2.5"' if n in flagged else 'stroke="#ffffff" stroke-width="0.8"'
            tip = f"{n}: {d.kind}, units {d.u}-{top}, {d.nameplate_w} W"
            out.append(
                f'<rect x="{x0 + 2}" y="{y}" width="{RACK_W - 4}" height="{d.height * UNIT_H}" fill="{FILL.get(d.kind, "#999999")}" '
                f'fill-opacity="0.85" {stroke}><title>{escape(tip)}</title></rect>'
            )
            label = n if len(n) <= 24 else n[:23] + "..."
            out.append(
                f'<text x="{x0 + 6}" y="{y + min(d.height * UNIT_H, UNIT_H) - 3}" font-size="8.5" fill="#ffffff">{escape(label)}</text>'
            )
    out.append("</svg>")
    return "\n".join(out) + "\n"
