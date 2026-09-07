"""Tests for the Phase 4 latency benchmark.

The benchmark is designed to be runnable on any machine, with or
without credentials. These tests focus on:

* Stage count and names match the spec.
* `run_single_pass` returns `None` (not 0) for unavailable stages.
* `aggregate` correctly handles missing values and a mix of N>0
  and N=0 stages.
* `run_benchmark` runs N times and reports the correct sample size.
* The synthetic image is a valid JPEG that Phase 1's loader accepts.
"""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

import facechain.benchmark as benchmark
from facechain.benchmark import (
    DEFAULT_BENCHMARK_SIZE,
    StageTimings,
    aggregate,
    make_synthetic_benchmark_image,
    run_benchmark,
    run_single_pass,
)


# ---------------------------------------------------------------------------
# Synthetic image generator
# ---------------------------------------------------------------------------


def test_synthetic_image_is_a_valid_jpeg():
    data = make_synthetic_benchmark_image()
    assert isinstance(data, bytes)
    assert len(data) > 0
    # Round-trip through PIL to make sure it actually decodes.
    img = Image.open(io.BytesIO(data))
    assert img.format == "JPEG"
    assert img.size == DEFAULT_BENCHMARK_SIZE


def test_synthetic_image_accepts_arbitrary_size():
    data = make_synthetic_benchmark_image(size=(64, 64))
    img = Image.open(io.BytesIO(data))
    assert img.size == (64, 64)


# ---------------------------------------------------------------------------
# run_single_pass
# ---------------------------------------------------------------------------


def test_run_single_pass_returns_a_complete_stage_timings_record():
    timings = run_single_pass(make_synthetic_benchmark_image())
    assert isinstance(timings, StageTimings)
    d = timings.to_dict()
    # Every spec stage must be present, even if the value is None.
    expected_stages = {
        "image_preprocess_ms",
        "face_detection_ms",
        "embedding_ms",
        "reverse_search_ms",
        "candidate_validation_ms",
        "evidence_generation_ms",
        "blockchain_submit_ms",
    }
    assert set(d.keys()) == expected_stages


def test_run_single_pass_preprocess_always_runs():
    timings = run_single_pass(make_synthetic_benchmark_image())
    assert timings.image_preprocess_ms is not None
    assert timings.image_preprocess_ms >= 0.0
    assert timings.evidence_generation_ms is not None
    assert timings.evidence_generation_ms >= 0.0


def test_run_single_pass_blockchain_is_none_without_env(monkeypatch):
    """If blockchain is not configured, blockchain_submit_ms MUST be
    None (never a fabricated 0.0). This is the spec's honesty rule.

    We can't monkeypatch the frozen `Settings` dataclass, so we
    ensure no blockchain env vars are visible in the process for
    the duration of this test by unsetting them.
    """
    import os
    saved = {k: os.environ.pop(k, None) for k in (
        "SEPOLIA_RPC_URL", "BLOCKCHAIN_PRIVATE_KEY", "CONTRACT_ADDRESS",
    )}
    try:
        timings = run_single_pass(make_synthetic_benchmark_image())
        assert timings.blockchain_submit_ms is None
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_run_single_pass_reverse_search_is_none_without_credentials(monkeypatch):
    """If Google credentials are missing, reverse_search_ms is None.

    Same trick as above: unset the env var, run, restore.
    """
    import os
    saved = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    try:
        timings = run_single_pass(make_synthetic_benchmark_image())
        assert timings.reverse_search_ms is None
    finally:
        if saved is not None:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


def test_aggregate_min_avg_max_handles_all_present():
    runs = [
        StageTimings(
            image_preprocess_ms=10.0,
            face_detection_ms=20.0,
            embedding_ms=0.1,
            reverse_search_ms=200.0,
            candidate_validation_ms=0.5,
            evidence_generation_ms=5.0,
            blockchain_submit_ms=300.0,
        )
        for _ in range(3)
    ]
    agg = aggregate(runs)
    pp = agg["image_preprocess_ms"]
    assert pp["min"] == 10.0
    assert pp["avg"] == 10.0
    assert pp["max"] == 10.0
    assert pp["n"] == 3

    fd = agg["face_detection_ms"]
    assert fd["min"] == 20.0
    assert fd["avg"] == 20.0
    assert fd["max"] == 20.0
    assert fd["n"] == 3


def test_aggregate_returns_none_for_missing_stage():
    """If a stage is None in every run, the aggregate must report n=0
    and None for min/avg/max — not 0.0 (which would falsely imply
    the stage was measured and instant)."""
    runs = [
        StageTimings(
            image_preprocess_ms=10.0,
            face_detection_ms=None,
            embedding_ms=None,
            reverse_search_ms=None,
            candidate_validation_ms=0.0,
            evidence_generation_ms=5.0,
            blockchain_submit_ms=None,
        ),
        StageTimings(
            image_preprocess_ms=11.0,
            face_detection_ms=None,
            embedding_ms=None,
            reverse_search_ms=None,
            candidate_validation_ms=0.0,
            evidence_generation_ms=5.0,
            blockchain_submit_ms=None,
        ),
    ]
    agg = aggregate(runs)
    fd = agg["face_detection_ms"]
    assert fd == {"min": None, "avg": None, "max": None, "n": 0}
    pp = agg["image_preprocess_ms"]
    assert pp["min"] == 10.0
    assert pp["max"] == 11.0
    assert pp["avg"] == pytest.approx(10.5, abs=1e-6)
    assert pp["n"] == 2


def test_aggregate_handles_mixed_present_and_missing():
    """Within a single stage, only the present values count toward
    min/avg/max. A stage with one None and one value is reported
    with n=1, not n=2."""
    runs = [
        StageTimings(
            image_preprocess_ms=10.0,
            face_detection_ms=20.0,
            embedding_ms=None,
            reverse_search_ms=None,
            candidate_validation_ms=0.0,
            evidence_generation_ms=5.0,
            blockchain_submit_ms=None,
        ),
        StageTimings(
            image_preprocess_ms=10.0,
            face_detection_ms=None,
            embedding_ms=None,
            reverse_search_ms=None,
            candidate_validation_ms=0.0,
            evidence_generation_ms=5.0,
            blockchain_submit_ms=None,
        ),
    ]
    agg = aggregate(runs)
    fd = agg["face_detection_ms"]
    assert fd["n"] == 1
    assert fd["min"] == 20.0
    assert fd["avg"] == 20.0
    assert fd["max"] == 20.0


# ---------------------------------------------------------------------------
# run_benchmark
# ---------------------------------------------------------------------------


def test_run_benchmark_runs_n_times():
    report = run_benchmark(n=4, image_size=(64, 64))
    assert report.runs == 4
    assert report.image_size == (64, 64)
    # 7 stages, all listed
    assert set(report.stages.keys()) == {
        "image_preprocess_ms",
        "face_detection_ms",
        "embedding_ms",
        "reverse_search_ms",
        "candidate_validation_ms",
        "evidence_generation_ms",
        "blockchain_submit_ms",
    }


def test_run_benchmark_reports_sample_size_in_notes():
    report = run_benchmark(n=3)
    assert any("n=3" in note for note in report.notes)


def test_run_benchmark_to_dict_is_serializable():
    """`to_dict` must produce JSON-serializable output so judges can
    pipe the benchmark result to a file."""
    report = run_benchmark(n=2, image_size=(96, 96))
    as_dict = report.to_dict()
    # Round-trip through json — must not raise.
    json.dumps(as_dict, sort_keys=True)
