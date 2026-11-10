"""Compare the indexed checks with the literal ones on a generated data center and on random, deliberately broken ones."""

from __future__ import annotations

import random
from dataclasses import dataclass

from dcimlite import check, reference
from dcimlite.generate import GenParams, generate
from dcimlite.model import KINDS, Model, default_ports
from dcimlite.rules import Finding, keys


@dataclass
class Check:
    name: str
    findings: int
    ok: bool
    detail: str


def compare(a: list[Finding], b: list[Finding]) -> str | None:
    """None if the two lists report the same rule and subject in the same order, otherwise what differs."""
    ka, kb = keys(a), keys(b)
    if ka == kb:
        return None
    only_a = sorted(set(ka) - set(kb))
    only_b = sorted(set(kb) - set(ka))
    return f"indexed only: {only_a[:3]}; literal only: {only_b[:3]}; counts {len(ka)} and {len(kb)}"


def random_model(rng: random.Random) -> Model:
    """Anything the model allows: overlapping devices, devices outside their rack, cables joining any ports (twice, open, to the
    same device, of the wrong kind), PDUs of any capacity."""
    m = Model()
    for i in range(rng.randint(1, 5)):
        m.add_rack(f"R{i}", rng.randint(4, 20), rng.randint(300, 4000))
    racks = list(m.racks)
    for i in range(rng.randint(2, 30)):
        kind = rng.choice(KINDS)
        rack = rng.choice(racks)
        name = f"d{i:02d}"
        if kind == "pdu":
            m.add_device(
                name,
                rack,
                0,
                0,
                "pdu",
                0,
                feed=rng.choice("AB"),
                capacity_w=rng.choice((0, 150, 400, 900, 2500)),
                ports=default_ports("pdu", outlets=rng.randint(0, 5)),
            )
        else:
            ports = default_ports(
                "patch" if kind == "patch" else "server", net=rng.randint(0, 3), psu=rng.randint(0, 3)
            )
            m.add_device(
                name,
                rack,
                rng.randint(0, m.racks[rack].units + 2),
                rng.randint(1, 4),
                kind,
                rng.randint(0, 2000),
                ports=ports,
            )
    ports = sorted(m.ports)
    if ports:
        for _ in range(rng.randint(0, 40)):
            a = rng.choice(ports)
            cable_kind: str | None = rng.choice((None, None, "net", "power"))
            if rng.random() < 0.15:
                m.connect(a[0], a[1], kind=cable_kind)
            else:
                b = (
                    rng.choice(ports)
                    if rng.random() < 0.8
                    else (a[0], rng.choice([p for p in ports if p[0] == a[0]])[1])
                )
                m.connect(a[0], a[1], b[0], b[1], kind=cable_kind)
    return m


def case(name: str, m: Model) -> Check:
    a, b = check.check(m), reference.check(m)
    diff = compare(a, b)
    return Check(name, len(a), diff is None, diff or f"{len(m.devices)} devices, {len(m.cables)} cables")


def verify(draws: int = 25, seed: int = 1) -> list[Check]:
    out = [case("generated data center", generate(GenParams(racks=4, seed=seed))[0])]
    rng = random.Random(seed)
    for i in range(draws):
        out.append(case(f"random model {i + 1}", random_model(rng)))
    return out
