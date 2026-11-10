"""The checks, built on indexes: devices sorted per rack and swept once, cables counted per port, loads summed per PDU."""

from __future__ import annotations

from dcimlite.model import POWERED, Device, Model, allocated_w
from dcimlite.rules import Finding, sort_findings


def power_connections(m: Model) -> dict[str, list[str]]:
    """Device -> the PDUs it is plugged into, one entry per cable. A power connection is a cable between a `power_in` port of one
    device and a `power_out` port of a PDU, whatever kind the cable is recorded as."""
    conns: dict[str, list[str]] = {}
    for c in m.cables.values():
        if c.b_device is None or c.b_port is None:
            continue
        pa = m.ports[(c.a_device, c.a_port)]
        pb = m.ports[(c.b_device, c.b_port)]
        for src, dst, dst_dev in ((pa, pb, c.b_device), (pb, pa, c.a_device)):
            if src.kind == "power_in" and dst.kind == "power_out" and m.devices[dst_dev].kind == "pdu":
                conns.setdefault(src.device, []).append(dst_dev)
    return conns


def loads(m: Model, conns: dict[str, list[str]]) -> tuple[dict[str, int], dict[str, int]]:
    """Per PDU: the load in normal operation (each cable of a device carries an equal share, whole watts rounded down) and the
    load if every device that uses the PDU drew all of its power from it."""
    shared: dict[str, int] = {}
    full: dict[str, int] = {}
    for name, pdus in conns.items():
        a = allocated_w(m.devices[name].nameplate_w)
        part = a // len(pdus)
        for p in pdus:
            shared[p] = shared.get(p, 0) + part
        for p in set(pdus):
            full[p] = full.get(p, 0) + a
    return shared, full


def check(m: Model) -> list[Finding]:
    out: list[Finding] = []

    # geometry: sweep the devices of each rack once, in order of their lowest unit
    by_rack: dict[str, list[Device]] = {}
    for d in m.devices.values():
        if d.height > 0:
            by_rack.setdefault(d.rack, []).append(d)
    for rack, devs in by_rack.items():
        units = m.racks[rack].units
        devs.sort(key=lambda d: (d.u, d.name))
        active: list[tuple[int, str]] = []  # (top unit, name) of the devices that reach the current one
        for d in devs:
            top = d.u + d.height - 1
            if d.u < 1 or top > units:
                out.append(Finding("out_of_rack", d.name, f"{d.name} occupies units {d.u}-{top} of {rack} ({units} U)"))
            active = [a for a in active if a[0] >= d.u]
            for _, other in active:
                a, b = sorted((other, d.name))
                out.append(Finding("overlap", f"{a}|{b}", f"{a} and {b} share units in {rack}"))
            active.append((top, d.name))

    # cables
    used: dict[tuple[str, str], int] = {}
    for c in m.cables.values():
        ends = [(c.a_device, c.a_port)]
        if c.b_device is not None and c.b_port is not None:
            ends.append((c.b_device, c.b_port))
        for e in ends:
            used[e] = used.get(e, 0) + 1
        if len(ends) == 1:
            out.append(
                Finding("open_cable", f"cable:{c.id}", f"cable {c.id} is plugged in at {c.a_device}:{c.a_port} only")
            )
            ok = (m.ports[ends[0]].kind == "net") if c.kind == "net" else (m.ports[ends[0]].kind != "net")
        else:
            ka, kb = m.ports[ends[0]].kind, m.ports[ends[1]].kind
            ok = (ka == "net" and kb == "net") if c.kind == "net" else {ka, kb} == {"power_in", "power_out"}
            if c.a_device == c.b_device:
                out.append(Finding("self_loop", f"cable:{c.id}", f"cable {c.id} joins two ports of {c.a_device}"))
        if not ok:
            out.append(Finding("kind_mismatch", f"cable:{c.id}", f"{c.kind} cable {c.id} is on ports it does not suit"))
    for (dev, port), n in used.items():
        if n > 1:
            out.append(Finding("double_connected", f"{dev}:{port}", f"{dev}:{port} has {n} cables"))

    # power
    conns = power_connections(m)
    for d in m.devices.values():
        if d.kind not in POWERED:
            continue
        pdus = conns.get(d.name, [])
        if not pdus:
            out.append(Finding("no_power", d.name, f"{d.name} is connected to no PDU"))
        elif len(pdus) == 1:
            out.append(Finding("single_feed", d.name, f"{d.name} draws from {pdus[0]} only"))
        elif len({m.devices[p].feed for p in pdus}) == 1:
            out.append(Finding("same_feed", d.name, f"{d.name} draws only from feed {m.devices[pdus[0]].feed}"))
    shared, full = loads(m, conns)
    for d in m.devices.values():
        if d.kind == "pdu" and d.capacity_w > 0:
            if shared.get(d.name, 0) > d.capacity_w:
                out.append(Finding("pdu_overload", d.name, f"{d.name} carries {shared[d.name]} W of {d.capacity_w} W"))
            elif full.get(d.name, 0) > d.capacity_w:
                out.append(
                    Finding(
                        "failover_overload", d.name, f"{d.name} would carry {full[d.name]} W of {d.capacity_w} W alone"
                    )
                )
    total: dict[str, int] = {}
    for d in m.devices.values():
        if d.kind != "pdu":
            total[d.rack] = total.get(d.rack, 0) + allocated_w(d.nameplate_w)
    for rack, watts in total.items():
        if watts > m.racks[rack].power_w:
            out.append(Finding("rack_power", rack, f"{rack} has {watts} W allocated of {m.racks[rack].power_w} W"))
    return sort_findings(out)
