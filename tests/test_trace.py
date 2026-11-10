from __future__ import annotations

import pytest

from dcimlite.model import Model, ModelError, default_ports
from dcimlite.trace import counterpart, trace

from .conftest import server, small


def chain() -> Model:
    m = small()
    server(m, "s", 1)
    server(m, "core", 2)
    m.add_device("pp", "A", 3, 1, "patch", 0, ports=default_ports("patch", net=2))
    m.connect("s", "eth0", "pp", "1-front")
    m.connect("pp", "1-back", "core", "eth0")
    return m


def test_counterpart() -> None:
    assert counterpart("7-front") == "7-back" and counterpart("7-back") == "7-front" and counterpart("eth0") is None


def test_trace_goes_through_a_patch_panel() -> None:
    t = trace(chain(), "s", "eth0")
    assert t.end == ("core", "eth0") and t.stopped == ""
    assert len(t.hops) == 2 and t.lines()[1] == "cable 2: pp:1-back -> core:eth0"


def test_trace_from_the_far_end_gives_the_same_path_reversed() -> None:
    assert trace(chain(), "core", "eth0").end == ("s", "eth0")


def test_trace_of_a_port_without_cable() -> None:
    t = trace(chain(), "s", "eth1")
    assert t.hops == [] and t.end is None and t.stopped == "no cable"


def test_trace_stops_at_an_open_cable_and_an_unplugged_position() -> None:
    m = small()
    server(m, "s", 1)
    m.connect("s", "eth0")
    t = trace(m, "s", "eth0")
    assert t.stopped == "cable plugged in at one end only"
    assert t.lines() == ["cable 1: s:eth0 -> (unplugged)"]
    m2 = small()
    server(m2, "s", 1)
    m2.add_device("pp", "A", 2, 1, "patch", 0, ports=default_ports("patch", net=1))
    m2.connect("s", "eth0", "pp", "1-front")
    t2 = trace(m2, "s", "eth0")
    assert t2.stopped == "unplugged panel position" and t2.end == ("pp", "1-back")


def test_trace_stops_where_a_port_has_two_cables() -> None:
    m = chain()
    server(m, "x", 5)
    m.connect("x", "eth0", "pp", "1-front")
    t = trace(m, "s", "eth0")
    assert t.stopped == "pp:1-front has 2 cables" and t.end == ("pp", "1-front")


def test_trace_does_not_loop() -> None:
    m = small()
    m.add_device("pp", "A", 1, 1, "patch", 0, ports=default_ports("patch", net=2))
    m.connect("pp", "1-back", "pp", "2-front")
    m.connect("pp", "2-back", "pp", "1-front")
    t = trace(m, "pp", "1-back")
    assert t.stopped == "loop" and len(t.hops) == 2


def test_trace_respects_its_limit() -> None:
    m = small()
    m.add_device("pp", "A", 1, 1, "patch", 0, ports=default_ports("patch", net=5))
    for i in range(1, 5):
        m.connect("pp", f"{i}-back", "pp", f"{i + 1}-front")
    t = trace(m, "pp", "1-back", limit=2)
    assert t.stopped == "loop" and len(t.hops) == 2


def test_trace_of_an_unknown_port() -> None:
    with pytest.raises(ModelError):
        trace(chain(), "s", "nope")
