from __future__ import annotations

import pytest

from dcimlite import check, reference
from dcimlite.generate import GenParams, Truth, generate
from dcimlite.rules import RULES, Finding
from dcimlite.score import score, summarize
from dcimlite.verify import case, compare, random_model, verify

from .conftest import DRAWS, SEED, dual, small


def test_a_clean_data_center_has_no_finding() -> None:
    for seed in range(SEED, SEED + 5):
        m, truth = generate(GenParams(racks=8, seed=seed), faults=False)
        assert check.check(m) == [] and truth.faults == []


def test_every_injected_fault_is_found_and_nothing_else() -> None:
    kinds = set()
    for seed in range(SEED, SEED + 12):
        m, truth = generate(GenParams(racks=12, seed=seed))
        got = {(f.rule, f.subject) for f in check.check(m)}
        assert got == truth.expected(), seed
        kinds |= {f.kind for f in truth.faults}
    assert kinds == set(RULES)  # over these seeds every rule was exercised


def test_generation_is_deterministic() -> None:
    a, ta = generate(GenParams(racks=5, seed=SEED))
    b, tb = generate(GenParams(racks=5, seed=SEED))
    assert a.devices == b.devices and a.cables == b.cables and ta.to_dict() == tb.to_dict()
    c, _ = generate(GenParams(racks=5, seed=SEED + 1))
    assert c.cables != a.cables


def test_faults_stay_out_of_the_first_rack() -> None:
    m, truth = generate(GenParams(racks=6, seed=SEED))
    assert all(f.rack != min(m.racks) for f in truth.faults)


def test_truth_round_trip() -> None:
    _, truth = generate(GenParams(racks=6, seed=SEED))
    assert Truth.from_dict(truth.to_dict()).expected() == truth.expected()


def test_score_counts_found_missed_and_extra() -> None:
    m, truth = generate(GenParams(racks=8, seed=SEED))
    findings = check.check(m)
    s = score(findings, truth)
    assert s["found"] == s["injected"] and s["missed"] == [] and s["extra"] == []
    dropped = [*findings[1:], Finding("overlap", "ghost|ghost2", "")]
    s2 = score(dropped, truth)
    assert s2["found"] == s["injected"] - 1 and len(s2["missed"]) == 1 and s2["extra"] == [("overlap", "ghost|ghost2")]
    total = summarize([s, s2], 0, 2)
    assert total["injected"] == 2 * s["injected"] and total["missed"] == 1 and total["extra"] == 1
    assert 0 < total["recall"] < 1 and 0 < total["precision"] < 1
    assert summarize([], 0, 0)["recall"] is None


def test_the_two_implementations_agree_on_generated_and_random_models() -> None:
    results = verify(DRAWS, SEED)
    assert len(results) == DRAWS + 1 and all(r.ok for r in results), [r for r in results if not r.ok]


def test_random_models_are_not_all_clean() -> None:
    import random

    rng = random.Random(SEED)
    assert any(check.check(random_model(rng)) for _ in range(10))


def test_verify_can_fail() -> None:
    """A deliberately wrong second implementation must be reported, not waved through."""
    m = small()
    dual(m, "s", 1, 1)
    good, bad = check.check(m), [Finding("no_power", "s", "")]
    assert compare(good, good) is None
    msg = compare(good, bad)
    assert msg is not None and "no_power" in msg


def test_case_reports_a_disagreement(monkeypatch: pytest.MonkeyPatch) -> None:
    m = small()
    dual(m, "s", 1, 1)
    monkeypatch.setattr(reference, "check", lambda _m: [Finding("no_power", "s", "")])
    r = case("x", m)
    assert not r.ok and "no_power" in r.detail
