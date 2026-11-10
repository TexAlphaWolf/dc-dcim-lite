"""Command line: init, generate, import, add-rack, add-device, move, remove, connect, disconnect, check, trace, elevation,
export, history, report, verify, bench, render."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dcimlite import __version__, analysis, bench, check, report, verify
from dcimlite.db import Store, StoreError
from dcimlite.elevation import elevation_svg
from dcimlite.generate import GenParams, Truth, generate
from dcimlite.htmlexport import html_page
from dcimlite.model import KINDS, Device, Model, ModelError, default_ports, from_capacity_files
from dcimlite.rules import sort_findings
from dcimlite.score import score
from dcimlite.trace import trace

Error = (ModelError, StoreError, ValueError, OSError)
DEMO = "demo data center (synthetic, 24 racks, seed 1, with injected faults)"


def read_truth(path: str) -> Truth:
    try:
        return Truth.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ModelError(f"cannot read the truth file {path}: {exc}") from exc


def port_arg(text: str) -> tuple[str, str]:
    dev, sep, port = text.partition(":")
    if not sep or not dev or not port:
        raise ModelError(f"'{text}' is not written DEVICE:PORT")
    return dev, port


def open_store(a: argparse.Namespace, create: bool = False) -> Store:
    return Store(a.db, create=create)


def summary_lines(rep: dict[str, Any]) -> list[str]:
    s, f = rep["summary"], rep["findings"]
    lines = [
        f"{rep['source']}: {s['racks']} racks, {s['devices']:,} devices, {s['ports']:,} ports, {s['cables']:,} cables"
    ]
    if f["total"]:
        lines.append(f"{f['total']} findings: " + ", ".join(f"{n} {r}" for r, n in f["by_rule"].items() if n))
    else:
        lines.append("no findings")
    acc = rep["accuracy"]
    if acc:
        lines.append(
            f"against the injected faults: {acc['found']} of {acc['injected']} found, {len(acc['extra'])} reports that are not an injected fault"
        )
    return lines


# ------------------------------------------------------------------------------------------------------------- commands


def cmd_init(a: argparse.Namespace) -> int:
    if Path(a.db).exists():
        raise StoreError(f"{a.db} already exists")
    with Store(a.db, create=True) as st:
        if a.demo:
            m, _ = generate(GenParams(racks=a.racks, seed=a.seed))
            st.save(m, "demo", f"seed {a.seed}")
            print(
                f"created {a.db} with a demo data center: {len(m.racks)} racks, {len(m.devices):,} devices, {len(m.cables):,} cables"
            )
        else:
            st.log("init", a.db)
            st.db.commit()
            print(f"created {a.db}")
    return 0


def cmd_generate(a: argparse.Namespace) -> int:
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "dcim.db").exists() or (out / "truth.json").exists():
        raise StoreError(f"{out / 'dcim.db'} or {out / 'truth.json'} already exists")
    m, truth = generate(GenParams(racks=a.racks, seed=a.seed), faults=not a.clean)
    with Store(out / "dcim.db", create=True) as st:
        st.save(m, "generate", f"seed {a.seed}")
    (out / "truth.json").write_text(json.dumps(truth.to_dict(), indent=1) + "\n", encoding="utf-8")
    print(
        f"written: {out / 'dcim.db'}, {out / 'truth.json'} ({len(m.racks)} racks, {len(m.devices):,} devices, {len(m.cables):,} cables, {len(truth.faults)} faults injected)"
    )
    return 0


def cmd_import(a: argparse.Namespace) -> int:
    m = from_capacity_files(a.facility, a.inventory)
    with Store(a.db, create=True) as st:
        st.save(m, "import", f"{a.facility}, {a.inventory}")
    print(f"imported {len(m.racks)} racks and {len(m.devices):,} devices into {a.db}")
    return 0


def cmd_add_rack(a: argparse.Namespace) -> int:
    with open_store(a) as st:
        st.add_rack(a.name, a.units, a.power_w)
    print(f"added rack {a.name} ({a.units} U, {a.power_w} W)")
    return 0


def cmd_add_device(a: argparse.Namespace) -> int:
    kind = a.kind
    if kind == "pdu":
        height, u = 0, 0
    else:
        height, u = a.height, a.u
    net, psu, outlets = a.net, a.psu, a.outlets
    if kind == "pdu":
        net, psu = 0, 0  # a PDU has outlets only
    else:
        outlets = 0
        if kind == "patch":
            psu = 0  # a patch panel is passive
    ports = default_ports(kind, net=net, psu=psu, outlets=outlets)
    dev = Device(a.name, a.rack, u, height, kind, a.watts, a.feed or "", a.capacity_w)
    with open_store(a) as st:
        st.add_device(dev, ports, force=a.force)
    print(
        f"added {kind} {a.name} to {a.rack}"
        + (f" at units {u}-{u + height - 1}" if height else "")
        + f" with {len(ports)} ports"
    )
    return 0


def cmd_move(a: argparse.Namespace) -> int:
    if a.rack is None and a.u is None:
        raise ModelError("give --rack and/or --u")
    with open_store(a) as st:
        st.move_device(a.name, a.rack, a.u, force=a.force)
    print(f"moved {a.name}")
    return 0


def cmd_remove(a: argparse.Namespace) -> int:
    with open_store(a) as st:
        st.remove_device(a.name, with_cables=a.with_cables)
    print(f"removed {a.name}")
    return 0


def cmd_connect(a: argparse.Namespace) -> int:
    with open_store(a) as st:
        cid = st.connect(port_arg(a.a), port_arg(a.b) if a.b else None, kind=a.kind)
    print(f"cable {cid}: {a.a} -> {a.b or '(open)'}")
    return 0


def cmd_disconnect(a: argparse.Namespace) -> int:
    with open_store(a) as st:
        st.disconnect(a.cable)
    print(f"removed cable {a.cable}")
    return 0


def load_model(a: argparse.Namespace) -> Model:
    with open_store(a) as st:
        return st.load()


def cmd_check(a: argparse.Namespace) -> int:
    m = load_model(a)
    findings = check.check(m)
    for f in findings[: None if a.all else a.limit]:
        print(f"{f.rule} {f.subject}: {f.detail}")
    if not a.all and len(findings) > a.limit:
        print(f"... and {len(findings) - a.limit:,} more (use --all)")
    print(
        f"{len(findings)} findings in {len(m.devices):,} devices"
        if findings
        else f"no findings in {len(m.devices):,} devices"
    )
    if a.truth:
        acc = score(findings, read_truth(a.truth))
        print(f"against the injected faults: {acc['found']} of {acc['injected']} found, {len(acc['extra'])} extra")
    return 1 if findings else 0


def cmd_trace(a: argparse.Namespace) -> int:
    dev, port = port_arg(a.port)
    t = trace(load_model(a), dev, port)
    for line in t.lines():
        print(line)
    if t.end is not None and not t.stopped:
        print(f"ends at {t.end[0]}:{t.end[1]}")
    elif t.stopped:
        print(f"stops: {t.stopped}")
    return 0


def cmd_elevation(a: argparse.Namespace) -> int:
    m = load_model(a)
    findings = check.check(m)
    racks = a.rack or None
    for r in racks or []:
        if r not in m.racks:
            raise ModelError(f"no rack '{r}'")
    Path(a.output).write_text(elevation_svg(m, racks, findings), encoding="utf-8")
    print(f"written: {a.output}")
    return 0


def cmd_export(a: argparse.Namespace) -> int:
    m = load_model(a)
    Path(a.output).write_text(html_page(m, check.check(m), title=Path(a.db).stem), encoding="utf-8")
    print(f"written: {a.output}")
    return 0


def cmd_history(a: argparse.Namespace) -> int:
    with open_store(a) as st:
        rows = st.history(a.limit)
    for _id, at, action, subject, detail in rows:
        print(f"{at}  {action:<14} {subject}" + (f"  ({detail})" if detail else ""))
    if not rows:
        print("no changes recorded")
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    if a.db:
        m, source = load_model(a), a.db
        truth = read_truth(a.truth) if a.truth else None
    else:
        if a.truth:
            raise ModelError("--truth needs the database it belongs to")
        m, truth = generate(GenParams())
        source = DEMO
    rep = analysis.build_report(m, truth, source)
    for line in summary_lines(rep):
        print(line)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
        (out / "report.md").write_text(report.render_report(rep), encoding="utf-8")
        report.report_figure(rep, out / "summary.png")
        (out / "elevation.svg").write_text(
            elevation_svg(m, sorted(m.racks)[:8], sort_findings(check.check(m))), encoding="utf-8"
        )
        print(f"written: {out / 'report.json'}, {out / 'report.md'}, {out / 'summary.png'}, {out / 'elevation.svg'}")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    results = verify.verify(a.draws, a.seed)
    bad = [c for c in results if not c.ok]
    for c in results:
        print(f"{'ok  ' if c.ok else 'FAIL'} {c.name}: {c.findings} findings ({c.detail})")
    print(f"{len(results) - len(bad)} of {len(results)} comparisons agree with the literal implementation")
    return 1 if bad else 0


def cmd_bench(a: argparse.Namespace) -> int:
    sizes = [int(p.replace("_", "")) for p in a.sizes.split(",") if p.strip()]
    ref_sizes = [int(p.replace("_", "")) for p in a.ref_sizes.split(",") if p.strip()]
    if not sizes or any(s < 50 for s in sizes + ref_sizes):
        raise ValueError("--sizes and --ref-sizes need whole numbers of 50 or more")
    result = bench.run_bench(
        sizes, a.repeat, a.seed, a.draws, a.cmdline, ref_sizes, a.seeds, lambda m: print(m, flush=True)
    )
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bench.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    (out / "bench.md").write_text(report.render_bench(result), encoding="utf-8")
    report.bench_figure(result, out / "summary.png")
    print(f"written: {out / 'bench.json'}, {out / 'bench.md'}, {out / 'summary.png'}")
    return 0 if result["verification"]["ok"] else 1


def cmd_render(a: argparse.Namespace) -> int:
    try:
        data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelError(f"cannot read {a.file}: {exc}") from exc
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind not in ("report", "bench"):
        raise ModelError(f"{a.file} is neither a report.json nor a bench.json")
    text = report.render_report(data) if kind == "report" else report.render_bench(data)
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"written: {a.output}")
    else:
        print(text, end="")
    if a.figure:
        (report.report_figure if kind == "report" else report.bench_figure)(data, Path(a.figure))
        print(f"written: {a.figure}")
    return 0


# -------------------------------------------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dcim", description="A small data center infrastructure manager.")
    p.add_argument("--version", action="version", version=f"dcim {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, func: Any, help_: str, db: bool = True) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        if db:
            sp.add_argument("db", help="the database file")
        sp.set_defaults(func=func)
        return sp

    s = add("init", cmd_init, "create an empty database (or one with a demo data center)")
    s.add_argument("--demo", action="store_true", help="fill it with a synthetic data center that has faults in it")
    s.add_argument("--racks", type=int, default=24)
    s.add_argument("--seed", type=int, default=1)

    s = add(
        "generate",
        cmd_generate,
        "write a synthetic data center (dcim.db) and its truth (truth.json) into a directory",
        db=False,
    )
    s.add_argument("output", help="directory to write into")
    s.add_argument("--racks", type=int, default=24)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--clean", action="store_true", help="no faults injected")

    s = add("import", cmd_import, "load the racks and devices of a dc-capacity-planner facility.json and inventory.csv")
    s.add_argument("facility")
    s.add_argument("inventory")

    s = add("add-rack", cmd_add_rack, "add a rack")
    s.add_argument("name")
    s.add_argument("--units", type=int, default=42)
    s.add_argument("--power-w", type=int, default=12000, help="what the rack may draw, in watts")

    s = add("add-device", cmd_add_device, "add a device with its ports")
    s.add_argument("name")
    s.add_argument("--rack", required=True)
    s.add_argument("--u", type=int, default=0, help="lowest unit (not for a PDU)")
    s.add_argument("--height", type=int, default=1, help="units taken (not for a PDU)")
    s.add_argument("--kind", choices=KINDS, default="server")
    s.add_argument("--watts", type=int, default=0, help="nameplate power")
    s.add_argument("--net", type=int, default=2, help="network ports (patch panel: positions)")
    s.add_argument("--psu", type=int, default=2, help="power supplies")
    s.add_argument("--outlets", type=int, default=0, help="outlets (a PDU)")
    s.add_argument("--feed", choices=("A", "B"), help="the feed of a PDU")
    s.add_argument("--capacity-w", type=int, default=0, help="what a PDU can carry")
    s.add_argument(
        "--force", action="store_true", help="record it even if it overlaps another device or does not fit the rack"
    )

    s = add("move", cmd_move, "move a device to another rack or unit")
    s.add_argument("name")
    s.add_argument("--rack")
    s.add_argument("--u", type=int)
    s.add_argument("--force", action="store_true")

    s = add("remove", cmd_remove, "remove a device")
    s.add_argument("name")
    s.add_argument("--with-cables", action="store_true", help="remove its cables too")

    s = add("connect", cmd_connect, "plug a cable between two ports (or into one, to leave the other end open)")
    s.add_argument("a", metavar="DEVICE:PORT")
    s.add_argument("b", metavar="DEVICE:PORT", nargs="?")
    s.add_argument("--kind", choices=("net", "power"))

    s = add("disconnect", cmd_disconnect, "remove a cable")
    s.add_argument("cable", type=int)

    s = add("check", cmd_check, "look for mistakes; exit code 1 if there is any")
    s.add_argument("--truth", help="the truth file of a synthetic data center, to score the findings")
    s.add_argument("--limit", type=int, default=50, help="findings to print")
    s.add_argument("--all", action="store_true", help="print every finding")

    s = add("trace", cmd_trace, "follow a cable from a port to where it ends, through patch panels")
    s.add_argument("port", metavar="DEVICE:PORT")

    s = add("elevation", cmd_elevation, "draw the racks (SVG); devices with a finding are outlined in red")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--rack", action="append", help="draw only this rack (repeat for several)")

    s = add("export", cmd_export, "write a static HTML page: findings, elevations, devices")
    s.add_argument("-o", "--output", required=True)

    s = add("history", cmd_history, "the log of changes, newest first")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("report", help="a report of a data center (the demo without a database)")
    s.add_argument("db", nargs="?")
    s.add_argument("--truth")
    s.add_argument("--out", help="write report.json, report.md, summary.png and elevation.svg here")
    s.set_defaults(func=cmd_report)

    s = add(
        "verify",
        cmd_verify,
        "compare with the literal implementation on random broken data centers; exit 1 on a difference",
        db=False,
    )
    s.add_argument("--draws", type=int, default=25)
    s.add_argument("--seed", type=int, default=1)

    s = add(
        "bench", cmd_bench, "speed, faults found against the truth, agreement with the literal implementation", db=False
    )
    s.add_argument("--sizes", default="1000,10000,100000,300000")
    s.add_argument("--ref-sizes", default="100,300,1000")
    s.add_argument("--repeat", type=int, default=5)
    s.add_argument("--draws", type=int, default=50)
    s.add_argument(
        "--seeds", type=int, default=50, help="synthetic data centers (seeds 1..N) for the faults-found sweep"
    )
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--out", default="dcim-out")

    s = add("render", cmd_render, "rebuild the Markdown (and figure) from report.json or bench.json", db=False)
    s.add_argument("file")
    s.add_argument("-o", "--output")
    s.add_argument("--figure")
    return p


def main(argv: list[str] | None = None) -> int:
    given = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(given)
    args.cmdline = " ".join(given)
    try:
        return int(args.func(args))
    except Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
