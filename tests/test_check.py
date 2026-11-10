"""Hand-computed cases. Every case goes through both implementations (`found` insists they agree)."""

from __future__ import annotations

from dcimlite.model import default_ports

from .conftest import both, dual, found, plug, server, small


def test_a_consistent_rack_has_no_finding() -> None:
    m = small()
    dual(m, "s1", 1, 1)
    dual(m, "s2", 2, 2, height=2)
    assert both(m) == []


def test_overlap_reports_every_pair_not_only_neighbours() -> None:
    m = small()
    server(m, "a", 1, 4)  # units 1-4
    server(m, "b", 3, 4)  # 3-6: overlaps a
    server(m, "c", 4, 1)  # 4: overlaps a and b
    server(m, "d", 7, 1)  # 7: touches nobody
    assert {x for x in found(m) if x[0] == "overlap"} == {("overlap", "a|b"), ("overlap", "a|c"), ("overlap", "b|c")}


def test_adjacent_devices_do_not_overlap() -> None:
    m = small()
    server(m, "a", 1, 2)
    server(m, "b", 3, 2)
    assert not any(r == "overlap" for r, _ in found(m))


def test_devices_in_other_racks_and_pdus_do_not_overlap() -> None:
    m = small()
    m.add_rack("B", 10, 3000)
    server(m, "a", 1, 3)
    m.add_device("b", "B", 1, 3, "server", 0)
    assert not any(r == "overlap" for r, _ in found(m))  # the PDUs of rack A sit at u 0, height 0


def test_out_of_rack() -> None:
    m = small()
    server(m, "top", 9, 2, watts=0)  # units 9-10: fits
    server(m, "over", 10, 2, watts=0)  # 10-11: sticks out
    server(m, "under", 0, 1, watts=0)  # unit 0
    f = found(m)
    assert ("out_of_rack", "over") in f and ("out_of_rack", "under") in f and ("out_of_rack", "top") not in f
    assert ("overlap", "over|top") in f  # sharing unit 10


def test_double_connected_port() -> None:
    m = small()
    server(m, "a", 1)
    server(m, "b", 2)
    server(m, "c", 3)
    m.connect("a", "eth0", "b", "eth0")
    m.connect("c", "eth0", "b", "eth0")  # b:eth0 now has two cables
    assert ("double_connected", "b:eth0") in found(m)
    assert not any(s == "a:eth0" for r, s in found(m) if r == "double_connected")


def test_open_cable_and_kinds() -> None:
    m = small()
    server(m, "a", 1)
    c1 = m.connect("a", "eth0")  # a network cable plugged in at one end: open, but of a suitable kind
    c2 = m.connect("a", "eth1", kind="power")  # a power cable on a network port: open and wrong
    f = found(m)
    assert ("open_cable", f"cable:{c1.id}") in f and ("open_cable", f"cable:{c2.id}") in f
    assert ("kind_mismatch", f"cable:{c1.id}") not in f and ("kind_mismatch", f"cable:{c2.id}") in f


def test_kind_mismatch_combinations() -> None:
    m = small()
    server(m, "a", 1)
    server(m, "b", 2)
    ok_net = m.connect("a", "eth0", "b", "eth0")
    net_on_power = m.connect("a", "eth1", "A-pduA", "out1", kind="net")
    power_in_to_in = m.connect("a", "psu0", "b", "psu0")  # two inputs
    ok_power = m.connect("a", "psu1", "A-pduA", "out2")
    power_on_net = m.connect("b", "eth1", "A-pduA", "out3", kind="power")
    f = {s for r, s in found(m) if r == "kind_mismatch"}
    assert f == {f"cable:{net_on_power.id}", f"cable:{power_in_to_in.id}", f"cable:{power_on_net.id}"}
    assert f"cable:{ok_net.id}" not in f and f"cable:{ok_power.id}" not in f


def test_self_loop() -> None:
    m = small()
    server(m, "a", 1)
    c = m.connect("a", "eth0", "a", "eth1")
    assert ("self_loop", f"cable:{c.id}") in found(m)


def test_power_redundancy_rules() -> None:
    m = small()
    dual(m, "ok", 1, 1)
    server(m, "none", 2)
    server(m, "one", 3)
    plug(m, "one", 0, "A", 2)
    server(m, "same", 4)
    plug(m, "same", 0, "A", 3)
    plug(m, "same", 1, "A", 4)  # both inputs on feed A
    f = found(m)
    assert ("no_power", "none") in f and ("single_feed", "one") in f and ("same_feed", "same") in f
    assert not any(s == "ok" for _, s in f)


def test_two_cables_to_the_same_pdu_are_the_same_feed() -> None:
    m = small()
    server(m, "s", 1)
    plug(m, "s", 0, "A", 1)
    plug(m, "s", 1, "A", 2)
    assert ("same_feed", "s") in found(m)


def test_only_powered_kinds_need_power() -> None:
    m = small()
    server(m, "panel", 1, kind="other", watts=0)
    m.add_device("pp", "A", 2, 1, "patch", 0, ports=default_ports("patch", net=2))
    assert found(m) == set()


def test_a_cable_to_a_device_that_is_not_a_pdu_is_not_a_power_connection() -> None:
    m = small()
    server(m, "s", 1)
    server(m, "other", 2, kind="other")
    m.connect("s", "psu0", "other", "psu0")  # input to input: a mismatch
    f = found(m)
    assert ("no_power", "s") in f and ("kind_mismatch", "cable:1") in f


def test_pdu_loads_are_summed_in_whole_watts() -> None:
    # one server of 1000 W (800 allocated) on both feeds: 400 W on each PDU in normal operation, 800 W if one feed is lost
    m = small()
    dual(m, "s", 1, 1)
    pdu = m.devices["A-pduA"]
    pdu.capacity_w = 800
    assert found(m) == set()  # exactly at capacity is fine
    pdu.capacity_w = 799
    assert found(m) == {("failover_overload", "A-pduA")}
    pdu.capacity_w = 400
    assert found(m) == {("failover_overload", "A-pduA")}
    pdu.capacity_w = 399
    assert found(m) == {("pdu_overload", "A-pduA")}  # overloaded already: not also a failover finding
    pdu.capacity_w = 0  # not stated: not checked
    assert found(m) == set()


def test_a_single_fed_device_loads_one_pdu_fully() -> None:
    m = small()
    server(m, "s", 1)
    plug(m, "s", 0, "A", 1)  # 800 W on A, nothing on B
    m.devices["A-pduA"].capacity_w = 799
    assert found(m) == {("single_feed", "s"), ("pdu_overload", "A-pduA")}
    m.devices["A-pduA"].capacity_w = 800
    assert found(m) == {("single_feed", "s")}


def test_shares_round_down() -> None:
    # 1001 W allocates 800; with 3 supplies each carries 800 // 3 = 266 (not 266.67), so feed B carries 2 x 266 = 532
    m = small()
    server(m, "s", 1, watts=1001, psu=3)
    plug(m, "s", 0, "A", 1)
    plug(m, "s", 1, "B", 1)
    plug(m, "s", 2, "B", 2)
    m.devices["A-pduA"].capacity_w = 800
    m.devices["A-pduB"].capacity_w = 800
    assert found(m) == set()
    m.devices["A-pduB"].capacity_w = 532
    assert found(m) == {("failover_overload", "A-pduB")}  # 532 normal fits, 800 failover does not
    m.devices["A-pduB"].capacity_w = 531
    assert found(m) == {("pdu_overload", "A-pduB")}


def test_rack_power_is_the_sum_of_allocations() -> None:
    m = small()
    dual(m, "a", 1, 1, watts=1875)  # 1500 allocated
    dual(m, "b", 2, 2, watts=1875)  # 1500: 3000 in all, exactly the limit
    assert not any(r == "rack_power" for r, _ in found(m))
    dual(m, "c", 3, 3, watts=1)  # 0 allocated (1 * 4 // 5)
    assert not any(r == "rack_power" for r, _ in found(m))
    dual(m, "d", 4, 4, watts=2)  # 1 W more
    assert ("rack_power", "A") in found(m)
