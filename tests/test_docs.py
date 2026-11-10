"""The documentation must say what the measurements say."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from dcimlite import analysis, cli
from dcimlite.generate import GenParams, generate
from dcimlite.report import pct
from dcimlite.rules import RULES

ROOT = Path(__file__).resolve().parent.parent
REPORT = json.loads((ROOT / "docs" / "report.json").read_text(encoding="utf-8"))
BENCH = json.loads((ROOT / "docs" / "bench.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")
ANALYSIS = (ROOT / "docs" / "analysis.md").read_text(encoding="utf-8")
METHOD = (ROOT / "docs" / "method.md").read_text(encoding="utf-8")
SUM = BENCH["accuracy"]["summary"]
CHECKS = {c["devices"]: c for c in BENCH["checks"]}
ONE_LINE = re.compile(r"\s+")


def flat(text: str) -> str:
    return ONE_LINE.sub(" ", text.replace("**", ""))


def t(seconds: float) -> str:
    from dcimlite.report import _t

    return _t(seconds)


def test_the_benchmark_is_what_the_text_says_it_is() -> None:
    env = BENCH["environment"]
    assert env["dcimlite"] == "1.0.0" and env["seed"] == 1 and env["repeat"] == 5 and env["cpus"] == 12
    assert env["python"] == "3.14.10"
    assert sorted(CHECKS) == [1015, 10249, 102684, 307349]
    assert BENCH["verification"] == {"checks": 51, "findings": 3407, "ok": True, "bad": 0}
    assert BENCH["accuracy"]["seeds"] == 50 and BENCH["accuracy"]["racks"] == 24
    assert SUM["injected"] == SUM["found"] == 600 and SUM["missed"] == SUM["extra"] == 0
    assert SUM["clean_models"] == 50 and SUM["clean_findings"] == 0


def test_markdown_is_the_render_of_the_json(tmp_path: Path) -> None:
    for name in ("report", "bench"):
        out = tmp_path / f"{name}.md"
        assert cli.main(["render", str(ROOT / "docs" / f"{name}.json"), "-o", str(out)]) == 0
        assert out.read_text(encoding="utf-8") == (ROOT / "docs" / f"{name}.md").read_text(encoding="utf-8")


def test_the_report_is_what_the_demo_gives_today() -> None:
    m, truth = generate(GenParams())
    fresh = json.loads(json.dumps(analysis.build_report(m, truth, cli.DEMO)))
    assert fresh == REPORT


def test_figures_exist() -> None:
    for name in ("report.png", "bench.png"):
        assert (ROOT / "docs" / name).stat().st_size > 10_000
    assert (ROOT / "docs" / "elevation.svg").read_text(encoding="utf-8").startswith("<svg")


@pytest.mark.parametrize("name", ["README.md", "docs/analysis.md"])
def test_no_scaffold_left(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert not re.search(
        r"work in progress|TODO|TBD|lorem|measurements pending|provisional|pre-measurement", text, re.I
    )


@pytest.mark.parametrize("name", ["README.md", "docs/analysis.md", "docs/architecture.md", "docs/method.md"])
def test_local_links_resolve(name: str) -> None:
    path = ROOT / name
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://")):
            continue
        assert (path.parent / target).exists(), f"{name}: {target}"


def test_the_real_output_blocks_are_the_real_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert cli.main(["report"]) == 0
    block = re.search(r"`dcim report` \(the demo data center\):\n\n```text\n(.*?)```", README, re.S)
    assert block and block.group(1) == capsys.readouterr().out
    d = tmp_path / "dc"
    assert cli.main(["generate", str(d), "--racks", "6", "--seed", "3"]) == 0
    capsys.readouterr()
    assert cli.main(["check", str(d / "dcim.db"), "--truth", str(d / "truth.json")]) == 1
    block = re.search(r"`dcim check` on `dcim generate dc --racks 6 --seed 3`:\n\n```text\n(.*?)```", README, re.S)
    assert block and block.group(1) == capsys.readouterr().out
    assert cli.main(["trace", str(d / "dcim.db"), "R02-srv-2u-01:eth1"]) == 0
    block = re.search(r"`dcim trace dc/dcim.db R02-srv-2u-01:eth1`[^\n]*:\n\n```text\n(.*?)```", README, re.S)
    assert block and block.group(1) == capsys.readouterr().out


def test_the_readme_numbers_are_the_measurements() -> None:
    s = REPORT["summary"]
    top = CHECKS[307349]
    must = [
        f"{s['racks']} racks with {s['devices']} devices, {s['ports']:,} ports and {s['cables']:,} cables",
        "600 faults, 600 reported, 0 missed, 0 reports that are not an injected fault",
        "(50 of 50 had 0 findings before any fault went in)",
        "51 comparisons (a generated data center and 50 random broken ones): 3,407 findings, all equal",
        f"Checking {top['devices']:,} devices ({top['ports'] / 1e6:.1f} million ports, {top['cables'] / 1e6:.1f} million cables) "
        f"takes {top['seconds']:.2f} s; {CHECKS[10249]['devices']:,} take {t(CHECKS[10249]['seconds'])}",
        f"({1e6 * CHECKS[1015]['seconds'] / 1015:.1f} us to {1e6 * top['seconds'] / top['devices']:.1f} us)",
        "Saving 102,684 devices takes 7.0 s and loading them 4.3 s (130.6 MB), against 1.29 s to check",
        f"{BENCH['environment']['cpus']} CPUs and Python {BENCH['environment']['python']}",
    ]
    text = flat(README)
    for m in must:
        assert flat(m) in text, m
    lit = {r["devices"]: r for r in BENCH["literal"]}
    ratios = [lit[n]["literal"] / lit[n]["indexed"] for n in lit]
    assert f"{min(ratios):.1f} to {max(ratios):.1f} times faster" in README
    assert f"{t(lit[1015]['indexed'])} against {t(lit[1015]['literal'])}" in README


def test_the_demo_claims() -> None:
    by_name = {r["name"]: r for r in REPORT["racks"]}
    assert REPORT["findings"]["total"] == REPORT["accuracy"]["injected"] == REPORT["accuracy"]["found"] == 12
    assert REPORT["accuracy"]["extra"] == [] and REPORT["accuracy"]["missed"] == []
    assert {r for r, n in REPORT["findings"]["by_rule"].items() if n} == {
        "double_connected",
        "open_cable",
        "kind_mismatch",
        "no_power",
        "single_feed",
        "same_feed",
        "rack_power",
        "failover_overload",
    }
    for rack, share in (("R12", 1.090), ("R14", 1.119)):
        r = by_name[rack]
        assert r["allocated_w"] / r["power_w"] == pytest.approx(share, abs=0.0005)
    assert (by_name["R12"]["allocated_w"], by_name["R14"]["allocated_w"]) == (13083, 13428)
    faulty = {f["rack"] for f in REPORT["accuracy"]["faults"]}
    clean = [r for r in REPORT["racks"] if r["name"] not in faulty]
    assert len(clean) == 12
    normal = [p["normal_w"] for r in clean for p in r["pdus"]]
    alone = [p["failover_w"] for r in clean for p in r["pdus"]]
    assert (min(normal), max(normal), min(alone), max(alone)) == (3556, 4318, 7117, 8643)
    shares = [r["allocated_w"] / r["power_w"] for r in REPORT["racks"] if r["name"] not in ("R12", "R14")]
    assert (min(shares), max(shares)) == (pytest.approx(0.567, abs=0.0005), pytest.approx(0.720, abs=0.0005))
    pdu = {p["name"]: p for p in by_name["R21"]["pdus"]}["R21-pduA"]
    assert (pdu["capacity_w"], pdu["normal_w"], pdu["failover_w"]) == (5864, 3907, 7822)
    kinds = REPORT["summary"]["by_kind"]
    assert kinds == {"patch": 24, "pdu": 48, "server": 319, "storage": 57, "switch": 25}


def test_the_analysis_tables() -> None:
    for rule, row in SUM["rules"].items():
        assert f"| {rule} | {row['injected']} | {row['found']} | {row['missed']} | {row['extra']} |" in ANALYSIS, rule
    assert set(SUM["rules"]) == set(RULES)
    for rule, row in REPORT["accuracy"]["rules"].items():
        if row["injected"]:
            assert f"| {rule} | {row['injected']} | {row['found']} | {row['missed']} | {row['extra']} |" in ANALYSIS
    for n, c in CHECKS.items():
        row = f"| {n:,} | {c['racks']:,} | {t(c['seconds'])} | {n / c['seconds']:,.0f} | {1e6 * c['seconds'] / n:.1f} us |"
        assert row in ANALYSIS, row
    for r in BENCH["literal"]:
        row = f"| {r['devices']:,} | {t(r['indexed'])} | {t(r['literal'])} | {r['literal'] / r['indexed']:.1f}x |"
        assert row in ANALYSIS, row
    for d in BENCH["database"]:
        row = f"| {d['devices']:,} | {d['cables']:,} | {t(d['save'])} | {t(d['load'])} | {d['bytes'] / 1e6:.1f} MB |"
        assert row in ANALYSIS, row
    first, top = CHECKS[1015], CHECKS[307349]
    assert (
        f"{top['devices'] / first['devices']:.0f}-fold growth costs {top['seconds'] / first['seconds']:.0f} times"
        in ANALYSIS
    )
    big = BENCH["database"][2]
    assert f"{big['bytes'] / big['devices'] / 1000:.2f} kB a device" in ANALYSIS
    assert f"{pct(SUM['recall'])}" == "100.0%"


def test_the_rules_in_the_method_are_the_rules_of_the_code() -> None:
    for rule in RULES:
        assert f"| `{rule}` |" in METHOD, rule
    order = [METHOD.index(f"| `{rule}` |") for rule in RULES]
    assert order == sorted(order)


def _json_types(x: Any) -> Any:  # pragma: no cover - helper kept for readability of failures
    return x
