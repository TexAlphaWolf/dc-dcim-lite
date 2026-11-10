"""How fast the checks are, how many injected faults they find, and that the two implementations still agree."""

from __future__ import annotations

import os
import platform
import statistics
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dcimlite import __version__, check, reference, score, verify
from dcimlite.db import Store
from dcimlite.generate import GenParams, generate
from dcimlite.model import Model

DEVICES_PER_RACK = 19.7  # what the generator builds on average (servers, a switch, a patch panel and two PDUs)
DB_MAX = 100_000  # the largest size the SQLite timings are made for


def timed(fn: Callable[[], object], repeat: int) -> float:
    runs = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return statistics.median(runs)


def model_of(devices: int, seed: int) -> Model:
    return generate(GenParams(racks=max(2, round(devices / DEVICES_PER_RACK)), seed=seed), faults=False)[0]


def sweep(seeds: int, racks: int = 24) -> dict[str, Any]:
    """Build data centers with seeds 1..seeds, inject faults, run the checks and score them against what was injected."""
    cases = []
    clean_findings = 0
    for seed in range(1, seeds + 1):
        g = GenParams(racks=racks, seed=seed)
        clean_findings += len(check.check(generate(g, faults=False)[0]))
        m, truth = generate(g)
        cases.append(score.score(check.check(m), truth))
    return {"seeds": seeds, "racks": racks, "summary": score.summarize(cases, clean_findings, seeds)}


def run_bench(
    sizes: list[int],
    repeat: int,
    seed: int,
    draws: int,
    command: str,
    ref_sizes: list[int],
    seeds: int = 50,
    progress: Callable[[str], None] = lambda _m: None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    progress("checking time by size")
    checks = []
    database = []
    for n in sizes:
        m = model_of(n, seed)
        checks.append(
            {
                "devices": len(m.devices),
                "racks": len(m.racks),
                "ports": len(m.ports),
                "cables": len(m.cables),
                "seconds": timed(lambda m=m: check.check(m), repeat),  # type: ignore[misc]
            }
        )
        if n <= DB_MAX:
            progress(f"SQLite save and load at about {n:,} devices")
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "dcim.db"
                runs = min(repeat, 3)
                saves, loads = [], []
                for _ in range(runs):
                    path.unlink(missing_ok=True)
                    store = Store(path)
                    a = time.perf_counter()
                    store.save(m, "bench")
                    b = time.perf_counter()
                    store.load()
                    c = time.perf_counter()
                    store.close()
                    saves.append(b - a)
                    loads.append(c - b)
                database.append(
                    {
                        "devices": len(m.devices),
                        "cables": len(m.cables),
                        "save": statistics.median(saves),
                        "load": statistics.median(loads),
                        "bytes": path.stat().st_size,
                    }
                )
    progress("literal implementation on the same data centers")
    literal = []
    for n in ref_sizes:
        m = model_of(n, seed)
        literal.append(
            {
                "devices": len(m.devices),
                "indexed": timed(lambda m=m: check.check(m), repeat),  # type: ignore[misc]
                "literal": timed(lambda m=m: reference.check(m), min(repeat, 3)),  # type: ignore[misc]
            }
        )
    progress(f"faults found over {seeds} data centers")
    accuracy = sweep(seeds)
    progress(f"agreement with the literal implementation on {draws} random broken data centers")
    results = verify.verify(draws, seed)
    return {
        "kind": "bench",
        "environment": {
            "dcimlite": __version__,
            "python": platform.python_version(),
            "system": f"{platform.system()} {platform.machine()}",
            "cpus": os.cpu_count(),
            "seed": seed,
            "repeat": repeat,
            "command": command,
            "seconds": round(time.perf_counter() - t0, 1),
        },
        "checks": checks,
        "literal": literal,
        "database": database,
        "accuracy": accuracy,
        "verification": {
            "checks": len(results),
            "findings": sum(r.findings for r in results),
            "ok": all(r.ok for r in results),
            "bad": sum(1 for r in results if not r.ok),
        },
    }
