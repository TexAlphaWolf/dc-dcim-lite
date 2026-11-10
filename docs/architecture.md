# Architecture

```
            cli.py  ────────────────────────────────────────────────────────┐
              │                                                              │
   ┌──────────┼───────────┬───────────┬───────────┬──────────┐              │
   ▼          ▼           ▼           ▼           ▼          ▼              ▼
 db.py     check.py   reference.py  trace.py  elevation.py  htmlexport.py  generate.py
 (SQLite)  (indexed)  (literal)                (SVG)        (HTML)         (+ truth)
   │          │           │           │           │          │              │
   └──────────┴─────┬─────┴───────────┴───────────┴──────────┴──────────────┘
                    ▼
               model.py + rules.py        verify.py, score.py, analysis.py, report.py, bench.py
```

| Module | Role |
|---|---|
| `model.py` | The in-memory model (racks, devices, ports, cables), the names it accepts, allocated power, the default ports of a device, and the import from the files of dc-capacity-planner. It refuses only references to things that do not exist |
| `rules.py` | The 12 rules, their order and the `Finding` tuple |
| `check.py` | The indexed implementation: a sweep per rack with an active list for overlaps, a dictionary of port use, loads per PDU |
| `reference.py` | The literal implementation: all pairs in a rack, cable ends looked up in tables, written to be obviously right |
| `trace.py` | Follows a cable through patch panels |
| `db.py` | SQLite: four tables with foreign keys and CHECK constraints, a `user_version`, and a log of every change. Queries are parameterised; the clock is injectable so the log is testable |
| `generate.py` | A consistent data center by construction, then injected faults and the list of what was injected |
| `verify.py`, `score.py` | Random broken models and the comparison of the two implementations; the score of findings against the injected list |
| `elevation.py`, `htmlexport.py` | Hand-written SVG elevations and a static HTML page; every name is escaped |
| `analysis.py`, `report.py`, `bench.py` | The report (JSON, Markdown, figure) and the benchmark |
| `cli.py` | The command line |

## Decisions

- **The model accepts mistakes.** Overlaps, devices above the top of the rack and cables on the wrong ports can be recorded, because
  the checks exist to find them. The store's commands (`add-device`, `move`) refuse an overlap or a device that does not fit unless
  `--force` is given, which is the everyday guard; the model underneath stays permissive.
- **Whole watts.** Allocated power is `nameplate * 4 // 5` and a device's share on a PDU is `allocated // k`, so every sum is an
  integer and the two implementations cannot disagree by rounding.
- **The data lives in SQLite and is checked in memory.** A check loads the model once. This keeps the rules in plain Python where
  both implementations can be read side by side, at the price shown in [`analysis.md`](analysis.md): loading is slower than checking.
- **The report is rebuilt from its JSON.** `dcim render` produces the Markdown and the figure from `report.json` or `bench.json`
  alone, and a test checks that the files in `docs/` are exactly that render.
- **No network, no service.** The program reads a database or files and writes files; the Docker image runs without network, with a
  read-only root and no capabilities.
