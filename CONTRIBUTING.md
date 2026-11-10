# Contributing

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest --cov
```

No service is needed. `DCIM_TEST_DRAWS` and `DCIM_TEST_SEED` run the same tests with more (or different) random data centers (CI
also uses 150 draws with seed 11).

Rules that keep the project honest:

- **A change to a rule needs both implementations.** Change `check.py` (indexed) and `reference.py` (literal) the same way, update the
  definition in `docs/method.md`, add a hand-computed case to `tests/test_check.py` (it runs through both) and let `dcim verify`
  compare them.
- **A change to the generator needs the truth to stay exact.** `tests/test_generate.py` requires that clean data centers have no
  findings and that the findings of faulty ones equal what was injected; keep it passing on many seeds.
- **Numbers in the README and `docs/analysis.md` come from `docs/report.json` and `docs/bench.json`**, and `tests/test_docs.py` checks
  them. After a change to the generator or the rules, regenerate them (`dcim report --out`, then `tools/run_full.ps1` for the
  benchmark) and update the text where a number moved.
- **Queries are parameterised and names are escaped.** Never build SQL or SVG/HTML from a name by concatenation.
