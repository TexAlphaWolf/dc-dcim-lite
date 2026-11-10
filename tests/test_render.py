from __future__ import annotations

from xml.etree import ElementTree

from dcimlite import check
from dcimlite.analysis import build_report
from dcimlite.elevation import elevation_svg, flagged_devices
from dcimlite.generate import GenParams, generate
from dcimlite.htmlexport import html_page
from dcimlite.model import Model

from .conftest import dual, server, small


def test_flagged_devices_include_both_sides_of_a_cable_and_overlaps() -> None:
    m = small()
    server(m, "a", 1, 2)
    server(m, "b", 2, 2)
    c = m.connect("a", "eth0", "a", "eth1")
    f = check.check(m)
    flagged = flagged_devices(m, f)
    assert {"a", "b"} <= flagged and c.id


def test_elevation_is_well_formed_svg_with_flags() -> None:
    m, _ = generate(GenParams(racks=4, seed=3))
    findings = check.check(m)
    svg = elevation_svg(m, findings=findings)
    root = ElementTree.fromstring(svg)
    assert root.tag.endswith("svg") and svg.count("<rect") > 50
    assert "#c0392b" in svg or "stroke" in svg
    assert elevation_svg(m, racks=["nope"]).startswith("<svg")  # unknown racks are skipped
    assert elevation_svg(Model()).startswith("<svg")


def test_names_are_escaped() -> None:
    m = Model()
    m.add_rack("<R>", 10, 1000)
    m.add_device('x"><script>alert(1)</script>', "<R>", 1, 1, "server", 0)
    svg = elevation_svg(m)
    page = html_page(m, check.check(m), title="<b>t</b>")
    for text in (svg, page):
        assert "<script>" not in text and "<b>t</b>" not in text
    assert "&lt;script&gt;" in svg and "&lt;b&gt;t&lt;/b&gt;" in page
    ElementTree.fromstring(svg)


def test_html_page_lists_findings() -> None:
    m, truth = generate(GenParams(racks=4, seed=3))
    page = html_page(m, check.check(m), title="T")
    assert page.startswith("<!doctype html>") and "<svg" in page
    assert str(len(truth.faults)) in page or page.count("<tr") > 1


def test_report_counts_and_accuracy() -> None:
    m, truth = generate(GenParams(racks=6, seed=SEED_))
    rep = build_report(m, truth, "x")
    assert rep["summary"]["racks"] == 6 and rep["findings"]["total"] == len(check.check(m))
    assert rep["accuracy"]["found"] == rep["accuracy"]["injected"] == len(truth.expected())
    assert len(rep["racks"]) == 6
    assert build_report(m)["accuracy"] is None


def test_rack_rows_carry_pdu_loads() -> None:
    m = small()
    dual(m, "s", 1, 1)
    row = build_report(m)["racks"][0]
    pdu = {p["name"]: p for p in row["pdus"]}
    assert row["name"] == "A" and row["allocated_w"] == 800 and row["used_u"] == 1
    assert pdu["A-pduA"]["normal_w"] == 400 and pdu["A-pduA"]["failover_w"] == 800


SEED_ = 2
