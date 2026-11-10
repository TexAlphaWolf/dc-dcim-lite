"""The data model: racks, devices, ports and cables, held in memory. Geometry and wiring mistakes are allowed in the model (they are
what the checks look for); only references that cannot make sense (a cable to a port that does not exist) are refused."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KINDS = ("server", "switch", "storage", "pdu", "patch", "other")
POWERED = frozenset({"server", "switch", "storage"})  # the kinds that must be fed by two power feeds
PORT_KINDS = ("net", "power_in", "power_out")
CABLE_KINDS = ("net", "power")
FEEDS = ("A", "B")


class ModelError(ValueError):
    pass


def check_name(what: str, name: str) -> None:
    """Names appear in findings as `device:port`, `a|b` and `cable:7`, so they may not contain the separators."""
    if not name or name != name.strip():
        raise ModelError(f"{what} needs a name without leading or trailing spaces")
    if any(ch in name for ch in ":|"):
        raise ModelError(f"{what} '{name}': a name may not contain ':' or '|'")


def allocated_w(nameplate_w: int) -> int:
    """Power allocated to a device for planning: 80% of the nameplate, in whole watts (integers, so every sum is exact)."""
    return nameplate_w * 4 // 5


@dataclass(slots=True)
class Rack:
    name: str
    units: int
    power_w: int  # what the rack may draw, planning figure


@dataclass(slots=True)
class Device:
    name: str
    rack: str
    u: int  # lowest unit occupied (1-based); 0 for a vertical PDU
    height: int  # units taken; 0 for a vertical PDU
    kind: str
    nameplate_w: int
    feed: str = ""  # for a PDU: the feed it hangs on ("A" or "B")
    capacity_w: int = 0  # for a PDU: what it can carry (0: not stated)


@dataclass(slots=True)
class Port:
    device: str
    name: str
    kind: str


@dataclass(slots=True)
class Cable:
    id: int
    a_device: str
    a_port: str
    b_device: str | None  # None: the cable is plugged in at one end only
    b_port: str | None
    kind: str


def default_ports(kind: str, net: int = 0, psu: int = 0, outlets: int = 0) -> list[tuple[str, str]]:
    """The ports a new device gets. Switches number their ports from 1, a patch panel has `N-front` and `N-back` pairs, others
    have eth0, eth1, ...; power supplies are psu0, psu1, ...; PDU outlets are out1, out2, ..."""
    ports: list[tuple[str, str]] = []
    if kind == "patch":
        for i in range(1, net + 1):
            ports += [(f"{i}-front", "net"), (f"{i}-back", "net")]
    elif kind == "switch":
        ports += [(str(i), "net") for i in range(1, net + 1)]
    else:
        ports += [(f"eth{i}", "net") for i in range(net)]
    ports += [(f"psu{i}", "power_in") for i in range(psu)]
    ports += [(f"out{i}", "power_out") for i in range(1, outlets + 1)]
    return ports


class Model:
    def __init__(self) -> None:
        self.racks: dict[str, Rack] = {}
        self.devices: dict[str, Device] = {}
        self.ports: dict[tuple[str, str], Port] = {}
        self.cables: dict[int, Cable] = {}
        self.next_cable = 1

    def __len__(self) -> int:
        return len(self.devices)

    def add_rack(self, name: str, units: int, power_w: int) -> Rack:
        check_name("a rack", name)
        if name in self.racks:
            raise ModelError(f"rack '{name}' already exists")
        if units < 1 or power_w < 1:
            raise ModelError(f"rack {name}: units and power_w must be positive")
        rack = Rack(name, units, power_w)
        self.racks[name] = rack
        return rack

    def add_device(
        self,
        name: str,
        rack: str,
        u: int,
        height: int,
        kind: str,
        nameplate_w: int = 0,
        *,
        feed: str = "",
        capacity_w: int = 0,
        ports: list[tuple[str, str]] | None = None,
    ) -> Device:
        check_name("a device", name)
        if name in self.devices:
            raise ModelError(f"device '{name}' already exists")
        if rack not in self.racks:
            raise ModelError(f"device '{name}': no such rack '{rack}'")
        if kind not in KINDS:
            raise ModelError(f"device '{name}': kind must be one of {', '.join(KINDS)}, got '{kind}'")
        if kind == "pdu":
            if height != 0 or u != 0:
                raise ModelError(f"device '{name}': a PDU is vertical, give u 0 and height 0")
            if feed not in FEEDS:
                raise ModelError(f"device '{name}': a PDU needs a feed, A or B")
        else:
            if height < 1 or u < 0:
                raise ModelError(f"device '{name}': height must be at least 1 and u at least 0")
            if feed:
                raise ModelError(f"device '{name}': only a PDU has a feed")
        if nameplate_w < 0 or capacity_w < 0:
            raise ModelError(f"device '{name}': nameplate_w and capacity_w must not be negative")
        dev = Device(name, rack, u, height, kind, nameplate_w, feed, capacity_w)
        wanted = ports or []
        seen: set[str] = set()
        for pname, pkind in wanted:
            if pkind not in PORT_KINDS:
                raise ModelError(f"device '{name}': port kind must be one of {', '.join(PORT_KINDS)}, got '{pkind}'")
            check_name(f"a port of '{name}'", pname)
            if pname in seen:
                raise ModelError(f"device '{name}': port names must be unique ('{pname}')")
            seen.add(pname)
        self.devices[name] = dev
        for pname, pkind in wanted:
            self.ports[(name, pname)] = Port(name, pname, pkind)
        return dev

    def connect(
        self,
        a_device: str,
        a_port: str,
        b_device: str | None = None,
        b_port: str | None = None,
        *,
        kind: str | None = None,
        cable_id: int | None = None,
    ) -> Cable:
        """A cable from one port to another, or plugged in at one end only (b_device and b_port both None). Its kind is `net`
        when every port it touches is a network port and `power` otherwise, unless given (a wrong kind is a finding, not an error)."""
        if (b_device is None) != (b_port is None):
            raise ModelError("give both the device and the port of the second end, or neither")
        pa = self.ports.get((a_device, a_port))
        if pa is None:
            raise ModelError(f"no port {a_device}:{a_port}")
        kinds = [pa.kind]
        if b_device is not None and b_port is not None:
            pb = self.ports.get((b_device, b_port))
            if pb is None:
                raise ModelError(f"no port {b_device}:{b_port}")
            kinds.append(pb.kind)
        if kind is None:
            kind = "net" if all(k == "net" for k in kinds) else "power"
        if kind not in CABLE_KINDS:
            raise ModelError(f"cable kind must be one of {', '.join(CABLE_KINDS)}, got '{kind}'")
        cid = self.next_cable if cable_id is None else cable_id
        if cid in self.cables:
            raise ModelError(f"cable {cid} already exists")
        cable = Cable(cid, a_device, a_port, b_device, b_port, kind)
        self.cables[cid] = cable
        self.next_cable = max(self.next_cable, cid + 1)
        return cable

    def disconnect(self, cable_id: int) -> Cable:
        cable = self.cables.pop(cable_id, None)
        if cable is None:
            raise ModelError(f"no cable {cable_id}")
        return cable

    def conflicts(self, dev: Device, ignore: str | None = None) -> list[str]:
        """Names of the devices that share a rack unit with `dev` (plain loops: used when one device is added or moved)."""
        if dev.height < 1:
            return []
        lo, hi = dev.u, dev.u + dev.height - 1
        out = []
        for other in self.devices.values():
            if other.name in (dev.name, ignore) or other.rack != dev.rack or other.height < 1:
                continue
            if other.u <= hi and lo <= other.u + other.height - 1:
                out.append(other.name)
        return sorted(out)


# ------------------------------------------------------------------------------------------------ import from capacity files


def from_capacity_files(facility: str | Path, inventory: str | Path) -> Model:
    """A model from the two files of the dc-capacity-planner project: facility.json (racks) and inventory.csv (devices). Only
    the devices still installed are taken; their kind comes from the name prefix (sw- switch, stor- storage, otherwise server)."""
    try:
        fac = json.loads(Path(facility).read_text(encoding="utf-8"))
        racks = fac["racks"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ModelError(f"cannot read the facility file {facility}: {exc}") from exc
    m = Model()
    for r in racks:
        try:
            m.add_rack(str(r["name"]), int(r["units"]), round(float(r["power_kw"]) * 1000))
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelError(f"{facility}: a rack is not valid: {exc}") from exc
    try:
        fh = open(inventory, encoding="utf-8", newline="")  # noqa: SIM115
    except OSError as exc:
        raise ModelError(f"cannot read {inventory}: {exc}") from exc
    with fh:
        reader = csv.DictReader(fh)
        need = {"name", "rack", "u", "height", "nameplate_w", "removed"}
        if reader.fieldnames is None or not need <= set(reader.fieldnames):
            raise ModelError(f"{inventory}: the header must have {', '.join(sorted(need))}")
        for line, row in enumerate(reader, start=2):
            if row["removed"].strip():
                continue
            name = row["name"]
            kind = "switch" if name.startswith("sw-") else "storage" if name.startswith("stor-") else "server"
            try:
                m.add_device(
                    name,
                    row["rack"],
                    int(row["u"]),
                    int(row["height"]),
                    kind,
                    round(float(row["nameplate_w"])),
                    ports=default_ports(kind, net=2, psu=2),
                )
            except (ValueError, TypeError) as exc:
                raise ModelError(f"{inventory}, line {line}: {exc}") from exc
    return m


def summary_counts(m: Model) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    for d in m.devices.values():
        kinds[d.kind] = kinds.get(d.kind, 0) + 1
    return {
        "racks": len(m.racks),
        "devices": len(m.devices),
        "ports": len(m.ports),
        "cables": len(m.cables),
        "by_kind": dict(sorted(kinds.items())),
    }
