from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from dcimlite.check import check
from dcimlite.db import Store, StoreError
from dcimlite.generate import GenParams, generate
from dcimlite.model import Device, default_ports

from .conftest import dual, small


def clock() -> object:
    n = {"i": 0}

    def tick() -> str:
        n["i"] += 1
        return f"2026-01-01T00:00:{n['i']:02d}Z"

    return tick


@pytest.fixture
def st(tmp_path: Path) -> Iterator[Store]:
    with Store(tmp_path / "d.db", clock=clock(), create=True) as s:  # type: ignore[arg-type]
        yield s


def test_round_trip_keeps_everything(tmp_path: Path) -> None:
    m, _ = generate(GenParams(racks=3, seed=2))
    with Store(tmp_path / "d.db", create=True) as s:
        s.save(m, "generate")
    with Store(tmp_path / "d.db") as s:
        m2 = s.load()
    assert m2.racks == m.racks and m2.devices == m.devices and m2.ports == m.ports and m2.cables == m.cables
    assert [f.subject for f in check(m2)] == [f.subject for f in check(m)]


def test_mutations_are_logged(st: Store) -> None:
    st.add_rack("A", 10, 3000)
    st.add_device(Device("pduA", "A", 0, 0, "pdu", 0, "A", 2000), default_ports("pdu", outlets=2))
    st.add_device(Device("s", "A", 1, 1, "server", 1000), default_ports("server", net=2, psu=1))
    cid = st.connect(("s", "psu0"), ("pduA", "out1"))
    st.move_device("s", None, 3)
    st.disconnect(cid)
    st.remove_device("s")
    actions = [h[2] for h in reversed(st.history(50))]
    assert actions == ["add-rack", "add-device", "add-device", "connect", "move", "disconnect", "remove-device"]
    assert st.history(2)[0][1].startswith("2026-01-01")
    assert "s" not in st.load().devices


def test_refusals(st: Store) -> None:
    st.add_rack("A", 10, 3000)
    st.add_device(Device("a", "A", 1, 4, "server", 0), default_ports("server", net=1, psu=1))
    with pytest.raises(StoreError):
        st.add_rack("A", 10, 1)
    with pytest.raises(StoreError, match="share rack units"):
        st.add_device(Device("b", "A", 3, 2, "server", 0), default_ports("server"))
    with pytest.raises(StoreError):
        st.add_device(Device("b", "A", 9, 3, "server", 0), default_ports("server"))  # out of the rack
    with pytest.raises(StoreError):
        st.add_device(Device("b", "Z", 1, 1, "server", 0), default_ports("server"))
    st.add_device(Device("b", "A", 3, 2, "server", 0), default_ports("server", net=1, psu=1), force=True)
    with pytest.raises(StoreError):
        st.add_device(Device("a", "A", 8, 1, "server", 0), default_ports("server"))  # name taken
    with pytest.raises(StoreError):
        st.move_device("nope", "A", 1)
    with pytest.raises(StoreError):
        st.move_device("a", "Z", 1)
    with pytest.raises(StoreError):
        st.move_device("a", None, 3)  # collides with b
    st.move_device("a", None, 3, force=True)
    with pytest.raises(StoreError):
        st.connect(("a", "nope"), None)
    with pytest.raises(StoreError):
        st.connect(("a", "eth0"), None, kind="rope")
    with pytest.raises(StoreError):
        st.disconnect(99)
    with pytest.raises(StoreError):
        st.remove_device("nope")


def test_removing_a_cabled_device_needs_its_cables_to_go(st: Store) -> None:
    st.add_rack("A", 10, 3000)
    st.add_device(Device("a", "A", 1, 1, "server", 0), default_ports("server", net=1, psu=1))
    st.add_device(Device("b", "A", 2, 1, "server", 0), default_ports("server", net=1, psu=1))
    st.connect(("a", "eth0"), ("b", "eth0"))
    with pytest.raises(StoreError, match="cable"):
        st.remove_device("a")
    st.remove_device("a", with_cables=True)
    assert st.load().cables == {}


def test_moving_a_pdu_is_refused_to_stay_vertical(st: Store) -> None:
    st.add_rack("A", 10, 3000)
    st.add_device(Device("p", "A", 0, 0, "pdu", 0, "A", 100), default_ports("pdu", outlets=1))
    st.move_device("p", "A", 0)
    with pytest.raises(StoreError):
        st.move_device("p", "A", 3)


def test_not_a_dcim_database(tmp_path: Path) -> None:
    p = tmp_path / "x.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE t (a)")
    con.commit()
    con.close()
    with pytest.raises(StoreError):
        Store(p)
    with pytest.raises(StoreError):
        Store(tmp_path / "missing.db", create=False)
    con = sqlite3.connect(tmp_path / "v.db")
    con.execute("PRAGMA user_version = 9")
    con.commit()
    con.close()
    with pytest.raises(StoreError, match="version"):
        Store(tmp_path / "v.db")


def test_queries_are_parameterised(st: Store) -> None:
    st.add_rack("A", 10, 3000)
    evil = "x'); DROP TABLE racks; --"
    st.add_device(Device(evil, "A", 1, 1, "server", 0), default_ports("server"))  # kept as text, never run
    m = st.load()
    assert evil in m.devices and "A" in m.racks


def test_save_replaces_the_contents(st: Store) -> None:
    m = small()
    dual(m, "s", 1, 1)
    st.save(m, "import")
    st.save(small(), "import")
    assert len(st.load().devices) == 2
