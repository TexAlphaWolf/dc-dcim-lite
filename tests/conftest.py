from __future__ import annotations

import os

from dcimlite import check, reference
from dcimlite.model import Model, default_ports
from dcimlite.rules import Finding
from dcimlite.verify import compare

SEED = int(os.environ.get("DCIM_TEST_SEED", "1"))
DRAWS = int(os.environ.get("DCIM_TEST_DRAWS", "12"))


def small() -> Model:
    """One rack of 10 U that may draw 3000 W, with a PDU on each feed (2000 W each, 4 outlets)."""
    m = Model()
    m.add_rack("A", 10, 3000)
    for feed in "AB":
        m.add_device(
            f"A-pdu{feed}", "A", 0, 0, "pdu", 0, feed=feed, capacity_w=2000, ports=default_ports("pdu", outlets=4)
        )
    return m


def server(m: Model, name: str, u: int, height: int = 1, watts: int = 1000, psu: int = 2, kind: str = "server") -> None:
    m.add_device(name, "A", u, height, kind, watts, ports=default_ports(kind, net=2, psu=psu))


def plug(m: Model, dev: str, psu: int, feed: str, out: int) -> None:
    m.connect(dev, f"psu{psu}", f"A-pdu{feed}", f"out{out}")


def dual(m: Model, name: str, u: int, out: int, height: int = 1, watts: int = 1000) -> None:
    """A server on both feeds."""
    server(m, name, u, height, watts)
    plug(m, name, 0, "A", out)
    plug(m, name, 1, "B", out)


def both(m: Model) -> list[Finding]:
    """The findings of both implementations, which must agree."""
    a, b = check.check(m), reference.check(m)
    assert compare(a, b) is None, compare(a, b)
    return a


def found(m: Model) -> set[tuple[str, str]]:
    return {(f.rule, f.subject) for f in both(m)}
