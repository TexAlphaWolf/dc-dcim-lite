"""A synthetic data center that is consistent by construction, and faults injected into it at known places.

Every rack has a patch panel and a top-of-rack switch at the bottom, two vertical PDUs (feed A and feed B), servers and storage
stacked above them, and its top four units left free. Servers draw from both PDUs and connect to the switch and to the patch
panel; the patch panels go back to a core switch in the first rack. Nothing is wrong in it. The injected faults are the twelve
mistakes the checks look for; the truth lists what each one should make the checks report.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from dcimlite.model import Model, allocated_w, default_ports

MIX = (
    ("srv-1u", "server", 1, 350, 0.55),
    ("srv-2u", "server", 2, 750, 0.20),
    ("stor-2u", "storage", 2, 600, 0.15),
    ("gpu-4u", "server", 4, 2000, 0.10),
)
OUTLETS = 48
TOR_PORTS = 48
PATCH_POSITIONS = 24
FREE_TOP = 4
FAULT_KINDS = (
    "overlap",
    "out_of_rack",
    "double_connected",
    "open_cable",
    "kind_mismatch",
    "self_loop",
    "no_power",
    "single_feed",
    "same_feed",
    "rack_power",
    "pdu_overload",
    "failover_overload",
)


@dataclass(frozen=True)
class GenParams:
    racks: int = 24
    seed: int = 1
    units: int = 42
    rack_power_w: int = 12_000
    pdu_capacity_w: int = 16_000
    max_alloc_share: float = 0.7  # of the rack power, when the rack is filled
    max_faults_per_kind: int = 2  # each kind is injected 0 to this many times


@dataclass
class Fault:
    kind: str
    subject: str  # what the checks should report (the subject of the finding)
    rack: str
    detail: str


@dataclass
class Truth:
    seed: int
    racks: int
    faults: list[Fault] = field(default_factory=list)

    def expected(self) -> set[tuple[str, str]]:
        return {(f.kind, f.subject) for f in self.faults}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Truth:
        return cls(int(d["seed"]), int(d["racks"]), [Fault(**f) for f in d["faults"]])


# ---------------------------------------------------------------------------------------------------------------- clean


def build_clean(g: GenParams) -> Model:
    rng = random.Random(g.seed)
    m = Model()
    names = [f"R{i:02d}" if g.racks < 100 else f"R{i:05d}" for i in range(1, g.racks + 1)]
    for n in names:
        m.add_rack(n, g.units, g.rack_power_w)
    weights = [w for *_, w in MIX]
    positions: dict[str, int] = {}  # rack -> next free patch position

    # first pass: the devices of every rack, so the core switch knows how many ports it needs
    layout: dict[str, list[str]] = {}
    for n in names:
        for feed in ("A", "B"):
            m.add_device(
                f"{n}-pdu{feed}",
                n,
                0,
                0,
                "pdu",
                0,
                feed=feed,
                capacity_w=g.pdu_capacity_w,
                ports=default_ports("pdu", outlets=OUTLETS),
            )
        m.add_device(f"{n}-tor", n, 1, 1, "switch", 150, ports=default_ports("switch", net=TOR_PORTS, psu=2))
        m.add_device(f"{n}-patch", n, 2, 1, "patch", 0, ports=default_ports("patch", net=PATCH_POSITIONS))
        alloc = allocated_w(150)
        limit = g.max_alloc_share * g.rack_power_w
        u = 3
        top_usable = g.units - FREE_TOP
        k = 0
        layout[n] = []
        while True:
            label, kind, height, plate, _ = rng.choices(MIX, weights)[0]
            plate = round(plate * rng.uniform(0.9, 1.1))
            gap = 1 if rng.random() < 0.12 else 0
            if u + gap + height - 1 > top_usable or alloc + allocated_w(plate) > limit:
                break
            u += gap
            k += 1
            name = f"{n}-{label}-{k:02d}"
            m.add_device(name, n, u, height, kind, plate, ports=default_ports(kind, net=4, psu=2))
            layout[n].append(name)
            alloc += allocated_w(plate)
            u += height
        positions[n] = 0

    core_ports = PATCH_POSITIONS * len(names) + len(names)
    core_rack = names[0]
    occupied = {
        x for d in m.devices.values() if d.rack == core_rack and d.height > 0 for x in range(d.u, d.u + d.height)
    }
    u = next(x for x in range(3, g.units - FREE_TOP + 1) if x not in occupied)
    m.add_device("core-01", core_rack, u, 1, "switch", 400, ports=default_ports("switch", net=core_ports, psu=2))
    next_core = 1

    def out_index(rack: str) -> int:
        positions[rack] += 1
        return positions[rack]

    for n in names:
        members = [f"{n}-tor", *layout[n]] + (["core-01"] if n == core_rack else [])
        for dev in members:
            i = out_index(n)
            m.connect(dev, "psu0", f"{n}-pduA", f"out{i}")
            m.connect(dev, "psu1", f"{n}-pduB", f"out{i}")
        for j, dev in enumerate(layout[n], start=1):
            m.connect(dev, "eth0", f"{n}-tor", str(j))
            if j <= PATCH_POSITIONS:
                m.connect(dev, "eth1", f"{n}-patch", f"{j}-front")
        for j in range(1, min(len(layout[n]), PATCH_POSITIONS) + 1):
            m.connect(f"{n}-patch", f"{j}-back", "core-01", str(next_core))
            next_core += 1
        m.connect(f"{n}-tor", str(TOR_PORTS), "core-01", str(next_core))
        next_core += 1
    return m


# -------------------------------------------------------------------------------------------------------------- faults


class _Injector:
    def __init__(self, m: Model, g: GenParams, rng: random.Random) -> None:
        self.m, self.g, self.rng = m, g, rng
        self.touched: set[str] = {next(iter(m.racks))}  # the first rack holds the core switch: leave it alone
        self.faults: list[Fault] = []

    def rack(self) -> str | None:
        free = [r for r in self.m.racks if r not in self.touched]
        if not free:
            return None
        r = self.rng.choice(free)
        self.touched.add(r)
        return r

    def servers(self, rack: str) -> list[str]:
        return sorted(d.name for d in self.m.devices.values() if d.rack == rack and d.kind in ("server", "storage"))

    def cable_at(self, dev: str, port: str) -> int:
        for c in self.m.cables.values():
            if (c.a_device, c.a_port) == (dev, port) or (c.b_device, c.b_port) == (dev, port):
                return c.id
        raise KeyError((dev, port))

    def add(self, kind: str, subject: str, rack: str, detail: str) -> None:
        self.faults.append(Fault(kind, subject, rack, detail))

    def inject(self, kind: str) -> bool:
        rack = self.rack()
        if rack is None:
            return False
        ok = getattr(self, f"_{kind}")(rack)
        if not ok:
            self.touched.discard(rack)
        return bool(ok)

    # geometry
    def _overlap(self, rack: str) -> bool:
        by_height: dict[int, list[str]] = {}
        for n in self.servers(rack):
            by_height.setdefault(self.m.devices[n].height, []).append(n)
        pairs = [v for v in by_height.values() if len(v) >= 2]
        if not pairs:
            return False
        d, e = self.rng.sample(self.rng.choice(pairs), 2)
        self.m.devices[d].u = self.m.devices[e].u
        a, b = sorted((d, e))
        self.add("overlap", f"{a}|{b}", rack, f"{d} moved onto the units of {e}")
        return True

    def _out_of_rack(self, rack: str) -> bool:
        names = self.servers(rack)
        if not names:
            return False
        d = self.m.devices[self.rng.choice(names)]
        d.u = self.g.units - d.height + 2  # the top unit sticks out by one
        self.add("out_of_rack", d.name, rack, f"{d.name} moved to units {d.u}-{d.u + d.height - 1} of {self.g.units}")
        return True

    # cables
    def _free(self, dev: str, port: str) -> bool:
        return not any(
            (c.a_device, c.a_port) == (dev, port) or (c.b_device, c.b_port) == (dev, port)
            for c in self.m.cables.values()
        )

    def _double_connected(self, rack: str) -> bool:
        names = self.servers(rack)
        if len(names) < 2:
            return False
        s1, s2 = self.rng.sample(names, 2)
        self.m.connect(s2, "eth2", s1, "eth0")
        self.add("double_connected", f"{s1}:eth0", rack, f"{s2}:eth2 also plugged into {s1}:eth0")
        return True

    def _open_cable(self, rack: str) -> bool:
        names = self.servers(rack)
        if not names:
            return False
        c = self.m.connect(self.rng.choice(names), "eth3")
        self.add("open_cable", f"cable:{c.id}", rack, f"cable {c.id} plugged in at one end")
        return True

    def _kind_mismatch(self, rack: str) -> bool:
        names = self.servers(rack)
        if not names:
            return False
        s = self.rng.choice(names)
        c = self.m.connect(s, "eth2", f"{rack}-pduA", f"out{OUTLETS}", kind="net")
        self.add("kind_mismatch", f"cable:{c.id}", rack, f"network cable {c.id} from {s}:eth2 to a PDU outlet")
        return True

    def _self_loop(self, rack: str) -> bool:
        names = self.servers(rack)
        if not names:
            return False
        s = self.rng.choice(names)
        c = self.m.connect(s, "eth2", s, "eth3")
        self.add("self_loop", f"cable:{c.id}", rack, f"cable {c.id} from {s}:eth2 to {s}:eth3")
        return True

    # power
    def _no_power(self, rack: str) -> bool:
        names = self.servers(rack)
        if not names:
            return False
        s = self.rng.choice(names)
        for p in ("psu0", "psu1"):
            self.m.disconnect(self.cable_at(s, p))
        self.add("no_power", s, rack, f"both power cables of {s} removed")
        return True

    def _single_feed(self, rack: str) -> bool:
        names = self.servers(rack)
        if not names:
            return False
        s = self.rng.choice(names)
        self.m.disconnect(self.cable_at(s, "psu1"))
        self.add("single_feed", s, rack, f"the feed B cable of {s} removed")
        return True

    def _same_feed(self, rack: str) -> bool:
        names = self.servers(rack)
        if not names:
            return False
        s = self.rng.choice(names)
        cable = self.m.cables[self.cable_at(s, "psu1")]
        cable.b_device, cable.b_port = f"{rack}-pduA", f"out{OUTLETS - 1}"
        self.add("same_feed", s, rack, f"psu1 of {s} moved from feed B to feed A")
        return True

    # rack level
    def _devices_of(self, rack: str) -> list[str]:
        return sorted(d.name for d in self.m.devices.values() if d.rack == rack and d.kind != "pdu")

    def _rack_power(self, rack: str) -> bool:
        names = self.servers(rack)
        if not names:
            return False
        total = sum(allocated_w(self.m.devices[n].nameplate_w) for n in self._devices_of(rack))
        s = self.m.devices[self.rng.choice(names)]
        target = round(self.g.rack_power_w * self.rng.uniform(1.05, 1.25))
        rest = total - allocated_w(s.nameplate_w)
        s.nameplate_w = math.ceil((target - rest) * 5 / 4)
        self.add(
            "rack_power", rack, rack, f"{s.name} raised to {s.nameplate_w} W: {total} -> about {target} W allocated"
        )
        return True

    def _loads(self, rack: str) -> tuple[int, int]:
        """(the load a PDU carries when every device shares its draw equally, the load it carries alone), from the clean layout."""
        shares = [allocated_w(self.m.devices[n].nameplate_w) for n in self._devices_of(rack)]
        return sum(a // 2 for a in shares), sum(shares)

    def _pdu_overload(self, rack: str) -> bool:
        shared, _ = self._loads(rack)
        self.m.devices[f"{rack}-pduA"].capacity_w = int(shared * 0.9)
        self.add(
            "pdu_overload", f"{rack}-pduA", rack, f"capacity of {rack}-pduA lowered below its normal load of {shared} W"
        )
        return True

    def _failover_overload(self, rack: str) -> bool:
        shared, alone = self._loads(rack)
        cap = shared + (alone - shared) // 2
        self.m.devices[f"{rack}-pduA"].capacity_w = cap
        self.add(
            "failover_overload",
            f"{rack}-pduA",
            rack,
            f"capacity of {rack}-pduA ({cap} W) is below the {alone} W it would carry alone",
        )
        return True


def generate(g: GenParams | None = None, faults: bool = True) -> tuple[Model, Truth]:
    g = g or GenParams()
    m = build_clean(g)
    truth = Truth(g.seed, g.racks)
    if not faults:
        return m, truth
    rng = random.Random(g.seed * 7919 + 13)
    inj = _Injector(m, g, rng)
    plan = [k for k in FAULT_KINDS for _ in range(rng.randint(0, g.max_faults_per_kind))]
    rng.shuffle(plan)
    for kind in plan:
        inj.inject(kind)
    truth.faults = inj.faults
    return m, truth
