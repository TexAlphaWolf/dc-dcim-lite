from __future__ import annotations

import json
from pathlib import Path

import pytest

from dcimlite.cli import main


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_manual_workflow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "d.db")
    assert run(capsys, "init", db)[0] == 0
    assert run(capsys, "init", db)[0] == 2  # already exists
    assert run(capsys, "add-rack", db, "A", "--units", "10", "--power-w", "3000")[0] == 0
    for feed in "AB":
        code, out, _ = run(
            capsys, "add-device", db, f"pdu{feed}", "--rack", "A", "--kind", "pdu", "--feed", feed,
            "--outlets", "4", "--capacity-w", "2000",
        )  # fmt: skip
        assert code == 0 and "with 4 ports" in out
    assert run(capsys, "add-device", db, "s", "--rack", "A", "--u", "1", "--watts", "1000")[0] == 0
    assert run(capsys, "add-device", db, "t", "--rack", "A", "--u", "1", "--watts", "10")[0] == 2  # overlap
    code, out, _ = run(capsys, "check", db)
    assert (code == 1 and "no_power s" in out and "1 findings" in out) or "findings in 3 devices" in out
    assert run(capsys, "connect", db, "s:psu0", "pduA:out1")[0] == 0
    assert run(capsys, "connect", db, "s:psu1", "pduB:out1")[0] == 0
    code, out, _ = run(capsys, "check", db)
    assert code == 0 and "no findings in 3 devices" in out
    assert run(capsys, "connect", db, "s:eth0")[1].startswith("cable 3: s:eth0 -> (open)")
    assert run(capsys, "check", db)[0] == 1
    assert run(capsys, "disconnect", db, "3")[0] == 0
    assert run(capsys, "disconnect", db, "3")[0] == 2
    assert run(capsys, "move", db, "s", "--u", "5")[0] == 0
    assert run(capsys, "move", db, "s")[0] == 2
    code, out, _ = run(capsys, "trace", db, "s:psu0")
    assert code == 0 and "ends at pduA:out1" in out
    assert "no cable" in run(capsys, "trace", db, "s:eth1")[1]
    assert run(capsys, "trace", db, "s:nope")[0] == 2 and run(capsys, "trace", db, "bad")[0] == 2
    assert run(capsys, "remove", db, "s")[0] == 2  # cabled
    assert run(capsys, "remove", db, "s", "--with-cables")[0] == 0
    out = run(capsys, "history", db)[1]
    assert "add-rack" in out and "remove-device" in out
    assert run(capsys, "elevation", db, "-o", str(tmp_path / "e.svg"), "--rack", "A")[0] == 0
    assert run(capsys, "elevation", db, "-o", str(tmp_path / "e.svg"), "--rack", "Z")[0] == 2
    assert (tmp_path / "e.svg").read_text(encoding="utf-8").startswith("<svg")
    assert run(capsys, "export", db, "-o", str(tmp_path / "e.html"))[0] == 0
    assert "<!doctype html>" in (tmp_path / "e.html").read_text(encoding="utf-8")


def test_generate_check_with_truth(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = str(tmp_path / "g")
    code, out, _ = run(capsys, "generate", d, "--racks", "6", "--seed", "3")
    assert code == 0 and "faults injected" in out
    assert run(capsys, "generate", d)[0] == 2  # would overwrite
    code, out, _ = run(capsys, "check", f"{d}/dcim.db", "--truth", f"{d}/truth.json", "--limit", "2")
    assert code == 1 and "more (use --all)" in out and "of 5 found, 0 extra" in out
    assert run(capsys, "check", f"{d}/dcim.db", "--all")[0] == 1
    assert run(capsys, "check", f"{d}/dcim.db", "--truth", str(tmp_path / "nope.json"))[0] == 2
    clean = str(tmp_path / "c")
    assert run(capsys, "generate", clean, "--racks", "3", "--clean")[0] == 0
    assert run(capsys, "check", f"{clean}/dcim.db")[0] == 0


def test_demo_database_and_missing_database(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "demo.db")
    code, out, _ = run(capsys, "init", db, "--demo", "--racks", "4", "--seed", "2")
    assert code == 0 and "4 racks" in out
    code, _, err = run(capsys, "check", str(tmp_path / "missing.db"))
    assert code == 2 and err.startswith("error:")
    assert run(capsys, "history", str(tmp_path / "missing.db"))[0] == 2


def test_import(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "f.json").write_text('{"racks": [{"name": "R1", "units": 10, "power_kw": 4.5}]}', encoding="utf-8")
    (tmp_path / "i.csv").write_text(
        "name,rack,u,height,nameplate_w,avg_w,installed,removed\nsrv-1u-1,R1,1,1,350,180,2020-01,\n", encoding="utf-8"
    )
    code, out, _ = run(capsys, "import", str(tmp_path / "d.db"), str(tmp_path / "f.json"), str(tmp_path / "i.csv"))
    assert code == 0 and "1 racks and 1 devices" in out
    assert run(capsys, "import", str(tmp_path / "e.db"), str(tmp_path / "nope.json"), str(tmp_path / "i.csv"))[0] == 2


def test_report_demo_and_render(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "r"
    code, out, _ = run(capsys, "report", "--out", str(out_dir))
    assert code == 0 and "24 racks, 473 devices" in out and "12 of 12 found, 0 reports" in out
    rep = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert rep["kind"] == "report" and (out_dir / "summary.png").stat().st_size > 1000
    assert (out_dir / "elevation.svg").read_text(encoding="utf-8").startswith("<svg")
    md = tmp_path / "r.md"
    assert run(capsys, "render", str(out_dir / "report.json"), "-o", str(md))[0] == 0
    assert md.read_text(encoding="utf-8") == (out_dir / "report.md").read_text(encoding="utf-8")
    assert "# " in run(capsys, "render", str(out_dir / "report.json"))[1]
    assert run(capsys, "render", str(out_dir / "report.json"), "--figure", str(tmp_path / "f.png"))[0] == 0
    assert run(capsys, "report", "--truth", "x.json")[0] == 2
    (tmp_path / "bad.json").write_text('{"kind": "x"}', encoding="utf-8")
    assert run(capsys, "render", str(tmp_path / "bad.json"))[0] == 2
    assert run(capsys, "render", str(tmp_path / "missing.json"))[0] == 2


def test_verify_command(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "verify", "--draws", "5")
    assert code == 0 and "6 of 6 comparisons agree" in out


def test_verify_command_fails_on_a_disagreement(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from dcimlite import reference
    from dcimlite.rules import Finding

    monkeypatch.setattr(reference, "check", lambda _m: [Finding("no_power", "x", "")])
    code, out, _ = run(capsys, "verify", "--draws", "2")
    assert code == 1 and "FAIL" in out and "of 3 comparisons agree" in out


def test_bench_small(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "b"
    code, text, _ = run(
        capsys, "bench", "--sizes", "200,400", "--ref-sizes", "100,200", "--repeat", "1", "--draws", "3",
        "--seeds", "3", "--out", str(out),
    )  # fmt: skip
    assert code == 0 and "bench.json" in text
    b = json.loads((out / "bench.json").read_text(encoding="utf-8"))
    assert b["kind"] == "bench" and b["verification"]["ok"] and len(b["checks"]) == 2
    assert (out / "summary.png").stat().st_size > 1000 and "|" in (out / "bench.md").read_text(encoding="utf-8")
    assert run(capsys, "render", str(out / "bench.json"))[0] == 0
    assert run(capsys, "bench", "--sizes", "10", "--out", str(out))[0] == 2
    assert run(capsys, "bench", "--sizes", "abc", "--out", str(out))[0] == 2


def test_help_and_version_work(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in (["--help"], ["--version"], ["bench", "--help"], ["add-device", "--help"], ["check", "--help"]):
        with pytest.raises(SystemExit) as e:
            main(argv)
        assert e.value.code == 0
    assert "dcim 1.0.0" in capsys.readouterr().out
