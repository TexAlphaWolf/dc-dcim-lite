"""The same checks written the plain way: every pair of devices in a rack compared, every cable end listed and sorted, every
device's power cables looked at one by one. It shares with check.py only the definitions in rules.py and model.py."""

from __future__ import annotations

from dcimlite.model import Model
from dcimlite.rules import Finding, sort_findings

NET_OK = {("net", "net")}
POWER_OK = {("power_out", "power_in"), ("power_in", "power_out")}


def check(m: Model) -> list[Finding]:
    out: list[Finding] = []
    names = sorted(m.devices)

    for rack in m.racks.values():
        here = [m.devices[n] for n in names if m.devices[n].rack == rack.name and m.devices[n].height > 0]
        for i, d in enumerate(here):
            if d.u < 1 or d.u + d.height - 1 > rack.units:
                out.append(Finding("out_of_rack", d.name, "literal"))
            for e in here[i + 1 :]:
                if d.u <= e.u + e.height - 1 and e.u <= d.u + d.height - 1:
                    out.append(Finding("overlap", f"{d.name}|{e.name}", "literal"))  # names are in order: d < e

    ends: list[tuple[str, str]] = []
    for cid in sorted(m.cables):
        c = m.cables[cid]
        ends.append((c.a_device, c.a_port))
        if c.b_device is None:
            out.append(Finding("open_cable", f"cable:{cid}", "literal"))
            pk = m.ports[(c.a_device, c.a_port)].kind
            good = (pk == "net") if c.kind == "net" else pk in ("power_in", "power_out")
        else:
            assert c.b_port is not None
            ends.append((c.b_device, c.b_port))
            pair = (m.ports[(c.a_device, c.a_port)].kind, m.ports[(c.b_device, c.b_port)].kind)
            good = pair in (NET_OK if c.kind == "net" else POWER_OK)
            if c.a_device == c.b_device:
                out.append(Finding("self_loop", f"cable:{cid}", "literal"))
        if not good:
            out.append(Finding("kind_mismatch", f"cable:{cid}", "literal"))
    ends.sort()
    i = 0
    while i < len(ends):
        j = i
        while j < len(ends) and ends[j] == ends[i]:
            j += 1
        if j - i > 1:
            out.append(Finding("double_connected", f"{ends[i][0]}:{ends[i][1]}", "literal"))
        i = j

    # power: for every device, look at each of its power input ports and every cable that ends on it
    cables_at: dict[tuple[str, str], list[int]] = {}
    for cid in sorted(m.cables):
        c = m.cables[cid]
        cables_at.setdefault((c.a_device, c.a_port), []).append(cid)
        if c.b_device is not None and c.b_port is not None:
            cables_at.setdefault((c.b_device, c.b_port), []).append(cid)
    inputs: dict[str, list[str]] = {n: [] for n in names}
    for (dev, pname), port in sorted(m.ports.items()):
        if port.kind == "power_in":
            inputs[dev].append(pname)
    plugs: dict[str, list[str]] = {n: [] for n in names}
    for n in names:
        for pname in inputs[n]:
            for cid in cables_at.get((n, pname), []):
                c = m.cables[cid]
                if c.b_device is None or c.b_port is None:
                    continue
                other = (c.b_device, c.b_port) if (c.a_device, c.a_port) == (n, pname) else (c.a_device, c.a_port)
                if m.ports[other].kind == "power_out" and m.devices[other[0]].kind == "pdu":
                    plugs[n].append(other[0])
    for n in names:
        d = m.devices[n]
        if d.kind in ("server", "switch", "storage"):
            if len(plugs[n]) == 0:
                out.append(Finding("no_power", n, "literal"))
            elif len(plugs[n]) == 1:
                out.append(Finding("single_feed", n, "literal"))
            elif all(m.devices[p].feed == m.devices[plugs[n][0]].feed for p in plugs[n]):
                out.append(Finding("same_feed", n, "literal"))
    normal = {n: 0 for n in names}
    alone = {n: 0 for n in names}
    for dn in names:
        mine = plugs[dn]
        a = m.devices[dn].nameplate_w * 4 // 5
        for p in mine:
            normal[p] += a // len(mine)
        for p in sorted(set(mine)):
            alone[p] += a
    for n in names:
        pdu = m.devices[n]
        if pdu.kind != "pdu" or pdu.capacity_w <= 0:
            continue
        if normal[n] > pdu.capacity_w:
            out.append(Finding("pdu_overload", n, "literal"))
        elif alone[n] > pdu.capacity_w:
            out.append(Finding("failover_overload", n, "literal"))
    for rack in m.racks.values():
        watts = sum(d.nameplate_w * 4 // 5 for d in m.devices.values() if d.rack == rack.name and d.kind != "pdu")
        if watts > rack.power_w:
            out.append(Finding("rack_power", rack.name, "literal"))
    return sort_findings(out)
