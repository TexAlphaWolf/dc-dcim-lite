"""A static HTML page of the data center: summary, findings, rack elevations and the device list. Everything that comes from the
database is escaped."""

from __future__ import annotations

from html import escape

from dcimlite.elevation import MAX_RACKS, elevation_svg
from dcimlite.model import Model, summary_counts
from dcimlite.rules import RULES, Finding

MAX_FINDINGS = 500
MAX_DEVICES = 1000
CSS = (
    "body{font:15px/1.5 system-ui,Helvetica,Arial,sans-serif;margin:24px;color:#222}"
    "table{border-collapse:collapse;margin:8px 0 24px}th,td{border:1px solid #ccc;padding:3px 9px;text-align:left}"
    "th{background:#f0f0f0}.bad{color:#c00000;font-weight:600}.scroll{overflow-x:auto}h1,h2{font-weight:600}"
)


def html_page(m: Model, findings: list[Finding], title: str = "Data center") -> str:
    s = summary_counts(m)
    by_rule: dict[str, int] = {}
    for f in findings:
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
    out = [
        "<!doctype html>",
        f'<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{CSS}</style></head><body>",
        f"<h1>{escape(title)}</h1>",
        f"<p>{s['racks']} racks, {s['devices']:,} devices, {s['ports']:,} ports, {s['cables']:,} cables. "
        + (f'<span class="bad">{len(findings)} findings.</span>' if findings else "No findings.")
        + "</p>",
    ]
    if findings:
        out.append("<h2>Findings</h2><table><tr><th>Rule</th><th>Count</th><th>Meaning</th></tr>")
        for rule, n in by_rule.items():
            out.append(f"<tr><td>{escape(rule)}</td><td>{n}</td><td>{escape(RULES[rule])}</td></tr>")
        out.append("</table><div class='scroll'><table><tr><th>Rule</th><th>Subject</th><th>Detail</th></tr>")
        for f in findings[:MAX_FINDINGS]:
            out.append(f"<tr><td>{escape(f.rule)}</td><td>{escape(f.subject)}</td><td>{escape(f.detail)}</td></tr>")
        out.append("</table></div>")
        if len(findings) > MAX_FINDINGS:
            out.append(f"<p>The first {MAX_FINDINGS} of {len(findings):,} findings are listed.</p>")
    out.append("<h2>Rack elevations</h2><div class='scroll'>")
    out.append(elevation_svg(m, findings=findings))
    out.append("</div>")
    if len(m.racks) > MAX_RACKS:
        out.append(f"<p>The first {MAX_RACKS} of {len(m.racks)} racks are drawn.</p>")
    out.append(
        "<h2>Devices</h2><div class='scroll'><table><tr><th>Device</th><th>Rack</th><th>Units</th><th>Kind</th><th>Nameplate</th></tr>"
    )
    for d in sorted(m.devices.values(), key=lambda d: (d.rack, d.u, d.name))[:MAX_DEVICES]:
        units = f"{d.u}-{d.u + d.height - 1}" if d.height else "vertical"
        out.append(
            f"<tr><td>{escape(d.name)}</td><td>{escape(d.rack)}</td><td>{units}</td><td>{escape(d.kind)}</td><td>{d.nameplate_w} W</td></tr>"
        )
    out.append("</table></div>")
    if len(m.devices) > MAX_DEVICES:
        out.append(f"<p>The first {MAX_DEVICES:,} of {len(m.devices):,} devices are listed.</p>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"
