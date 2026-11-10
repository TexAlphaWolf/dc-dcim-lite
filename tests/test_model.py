from __future__ import annotations

from pathlib import Path

import pytest

from dcimlite.model import Model, ModelError, allocated_w, default_ports, from_capacity_files, summary_counts

from .conftest import dual, small


def test_allocated_is_eighty_percent_in_whole_watts() -> None:
    assert allocated_w(1000) == 800 and allocated_w(350) == 280 and allocated_w(333) == 266 and allocated_w(0) == 0


def test_default_ports() -> None:
    assert default_ports("server", net=2, psu=2) == [
        ("eth0", "net"),
        ("eth1", "net"),
        ("psu0", "power_in"),
        ("psu1", "power_in"),
    ]
    assert default_ports("switch", net=3) == [("1", "net"), ("2", "net"), ("3", "net")]
    assert default_ports("patch", net=2) == [
        ("1-front", "net"),
        ("1-back", "net"),
        ("2-front", "net"),
        ("2-back", "net"),
    ]
    assert default_ports("pdu", outlets=2) == [("out1", "power_out"), ("out2", "power_out")]


def test_racks() -> None:
    m = Model()
    m.add_rack("A", 42, 8000)
    for bad in (
        ("A", 42, 8000),
        ("B", 0, 100),
        ("C", 10, 0),
        (" D", 10, 100),
        ("E:1", 10, 100),
        ("F|2", 10, 100),
        ("", 1, 1),
    ):
        with pytest.raises(ModelError):
            m.add_rack(*bad)


def test_devices_are_checked() -> None:
    m = small()
    m.add_device("s", "A", 1, 2, "server", 500)
    cases = [
        ("s", "A", 1, 1, "server", 0),  # exists
        ("x", "Z", 1, 1, "server", 0),  # no such rack
        ("x", "A", 1, 1, "toaster", 0),
        ("x", "A", 1, 0, "server", 0),  # height
        ("x", "A", -1, 1, "server", 0),
        ("x", "A", 1, 1, "server", -5),
        ("x:y", "A", 1, 1, "server", 0),
    ]
    for name, rack, u, h, kind, w in cases:
        with pytest.raises(ModelError):
            m.add_device(name, rack, u, h, kind, w)
    with pytest.raises(ModelError):
        m.add_device("p", "A", 1, 0, "pdu", 0, feed="A")  # a PDU is vertical
    with pytest.raises(ModelError):
        m.add_device("p", "A", 0, 0, "pdu", 0)  # a PDU needs a feed
    with pytest.raises(ModelError):
        m.add_device("x", "A", 1, 1, "server", 0, feed="A")  # only a PDU has a feed
    with pytest.raises(ModelError):
        m.add_device("x", "A", 1, 1, "server", 0, ports=[("a", "net"), ("a", "net")])
    with pytest.raises(ModelError):
        m.add_device("x", "A", 1, 1, "server", 0, ports=[("a", "wifi")])
    with pytest.raises(ModelError):
        m.add_device("x", "A", 1, 1, "server", 0, ports=[("a:b", "net")])
    assert "x" not in m.devices and ("x", "a") not in m.ports


def test_geometry_mistakes_are_allowed_in_the_model() -> None:
    m = small()
    m.add_device("a", "A", 1, 4, "server", 0)
    m.add_device("b", "A", 3, 4, "server", 0)  # overlaps: a finding, not an error
    m.add_device("c", "A", 9, 5, "server", 0)  # sticks out of the rack
    assert len(m.devices) == 5


def test_conflicts() -> None:
    m = small()
    m.add_device("a", "A", 2, 3, "server", 0)  # units 2-4
    from dcimlite.model import Device

    assert m.conflicts(Device("n", "A", 4, 2, "server", 0)) == ["a"]
    assert m.conflicts(Device("n", "A", 5, 2, "server", 0)) == []
    assert m.conflicts(Device("n", "A", 1, 1, "server", 0)) == []
    assert m.conflicts(Device("n", "A", 1, 1, "server", 0), ignore="a") == []
    assert m.conflicts(Device("a", "A", 2, 3, "server", 0)) == []  # itself does not count
    assert m.conflicts(Device("p", "A", 0, 0, "pdu", 0)) == []


def test_connect_infers_the_kind_and_refuses_unknown_ports() -> None:
    m = small()
    dual(m, "s", 1, 1)
    assert {c.kind for c in m.cables.values()} == {"power"}
    c = m.connect("s", "eth0")
    assert c.kind == "net" and c.b_device is None
    d = m.connect("s", "eth1", "s", "eth0", kind="power")
    assert d.kind == "power"
    for args in (("nope", "eth0"), ("s", "nope"), ("s", "eth0", "nope", "x")):
        with pytest.raises(ModelError):
            m.connect(*args)
    with pytest.raises(ModelError):
        m.connect("s", "eth0", "s", None)
    with pytest.raises(ModelError):
        m.connect("s", "eth0", kind="rope")
    with pytest.raises(ModelError):
        m.connect("s", "eth0", cable_id=c.id)
    assert m.disconnect(c.id).id == c.id
    with pytest.raises(ModelError):
        m.disconnect(c.id)


def test_summary_counts() -> None:
    m = small()
    dual(m, "s", 1, 1)
    s = summary_counts(m)
    assert s == {"racks": 1, "devices": 3, "ports": 4 + 4 + 4, "cables": 2, "by_kind": {"pdu": 2, "server": 1}}
    assert len(m) == 3


def test_import_from_capacity_files(tmp_path: Path) -> None:
    fac = tmp_path / "facility.json"
    fac.write_text('{"racks": [{"name": "R1", "units": 10, "power_kw": 4.5}]}', encoding="utf-8")
    inv = tmp_path / "inventory.csv"
    inv.write_text(
        "name,rack,u,height,nameplate_w,avg_w,installed,removed\n"
        "sw-1u-00000,R1,1,1,306.4,138.9,2020-01,\n"
        "stor-2u-00001,R1,2,2,600,320,2020-01,2021-01\n"
        "srv-1u-00002,R1,4,1,349.6,180,2020-02,\n",
        encoding="utf-8",
    )
    m = from_capacity_files(fac, inv)
    assert m.racks["R1"].power_w == 4500
    assert sorted(m.devices) == ["srv-1u-00002", "sw-1u-00000"]  # the removed one is left out
    assert m.devices["sw-1u-00000"].kind == "switch" and m.devices["srv-1u-00002"].nameplate_w == 350
    assert ("srv-1u-00002", "psu1") in m.ports


def test_import_errors(tmp_path: Path) -> None:
    good = tmp_path / "f.json"
    good.write_text('{"racks": [{"name": "R1", "units": 10, "power_kw": 4.5}]}', encoding="utf-8")
    inv = tmp_path / "i.csv"
    inv.write_text(
        "name,rack,u,height,nameplate_w,avg_w,installed,removed\nx,R1,abc,1,10,5,2020-01,\n", encoding="utf-8"
    )
    with pytest.raises(ModelError, match="line 2"):
        from_capacity_files(good, inv)
    inv.write_text("name,rack\n", encoding="utf-8")
    with pytest.raises(ModelError, match="header"):
        from_capacity_files(good, inv)
    for bad_fac in ("not json", '{"racks": [{"name": "R"}]}', '{"nope": 1}'):
        (tmp_path / "b.json").write_text(bad_fac, encoding="utf-8")
        with pytest.raises(ModelError):
            from_capacity_files(tmp_path / "b.json", inv)
    with pytest.raises(ModelError):
        from_capacity_files(tmp_path / "missing.json", inv)
    with pytest.raises(ModelError):
        from_capacity_files(good, tmp_path / "missing.csv")
