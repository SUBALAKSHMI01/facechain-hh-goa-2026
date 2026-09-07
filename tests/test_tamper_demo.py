"""Tests for the Phase 4 tamper demo.

The demo must:

* Verify an un-modified evidence file as VERIFIED.
* Copy the file (never modify the original).
* Mutate a field on the COPY.
* Re-verify the COPY as TAMPERED.
* Return a TamperDemoResult whose `transitioned_to_tampered()` is True.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import facechain.tamper_demo as tamper_demo
from facechain.tamper_demo import DEFAULT_TAMPERED_FIELD, run_tamper_demo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_valid_evidence(tmp_path: Path) -> Path:
    """Create a minimal but valid evidence file whose
    `evidenceHash` field is consistent with the rest of the body.

    Mirrors how Phase 1's builder actually populates evidence.json.
    """
    from facechain.evidence.canonicalize import evidence_hash

    body = {
        "schemaVersion": "1.0.0-phase1",
        "search": {
            "provider": "google_cloud_vision_web_detection",
            "hadResults": True,
            "socialCandidates": [
                {"url": "https://x.com/example/status/1"},
            ],
        },
    }
    canonical = {k: v for k, v in body.items() if k != "evidenceHash"}
    body["evidenceHash"] = evidence_hash(canonical)
    p = tmp_path / "evidence.json"
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy path: VERIFIED → TAMPERED
# ---------------------------------------------------------------------------


def test_run_tamper_demo_observed_transition(tmp_path):
    src = _write_valid_evidence(tmp_path)
    result = run_tamper_demo(src)

    # Original is un-modified.
    assert result.source_path == src
    assert result.tampered_path != src
    assert result.tampered_path.exists()

    # Before-tamper: VERIFIED. After-tamper: TAMPERED.
    assert result.before_status == "VERIFIED"
    assert result.after_status == "TAMPERED"
    assert result.transitioned_to_tampered() is True

    # Original was never modified — its content matches what we wrote.
    original = json.loads(src.read_text())
    assert "confidence" not in original or original.get("confidence") != result.new_value

    # The COPY is mutated.
    copy = json.loads(result.tampered_path.read_text())
    assert copy.get(result.field) == result.new_value


def test_run_tamper_demo_default_field_is_confidence(tmp_path):
    """Per the spec: modify `confidence`, re-verify, observe TAMPERED."""
    src = _write_valid_evidence(tmp_path)
    result = run_tamper_demo(src)
    assert result.field == DEFAULT_TAMPERED_FIELD
    assert result.field == "confidence"


def test_run_tamper_demo_records_original_value(tmp_path):
    src = _write_valid_evidence(tmp_path)
    result = run_tamper_demo(src)
    # The original file doesn't have `confidence`; that's fine —
    # the demo records the absence as None and replaces with 0.999.
    assert result.original_value is None
    assert result.new_value == 0.999


def test_run_tamper_demo_custom_field_and_value(tmp_path):
    src = _write_valid_evidence(tmp_path)
    result = run_tamper_demo(src, field="schemaVersion", new_value="999.0-evil")
    assert result.field == "schemaVersion"
    assert result.new_value == "999.0-evil"
    assert result.before_status == "VERIFIED"
    assert result.after_status == "TAMPERED"
    assert result.transitioned_to_tampered() is True


# ---------------------------------------------------------------------------
# Original is never modified
# ---------------------------------------------------------------------------


def test_run_tamper_demo_does_not_modify_original(tmp_path):
    src = _write_valid_evidence(tmp_path)
    before_text = src.read_text()
    run_tamper_demo(src)
    after_text = src.read_text()
    assert before_text == after_text


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_run_tamper_demo_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_tamper_demo(tmp_path / "nope.json")


def test_run_tamper_demo_tampered_copy_is_a_sibling_file(tmp_path):
    src = _write_valid_evidence(tmp_path)
    result = run_tamper_demo(src)
    # The tampered file is at <src>.tampered.json — same directory.
    assert result.tampered_path.parent == src.parent
    assert result.tampered_path.name.endswith(".tampered.json")


# ---------------------------------------------------------------------------
# CLI smoke: `python main.py tamper-demo` doesn't crash on a valid file
# (we test the underlying function here; the CLI invocation is exercised
# by manual demo).
# ---------------------------------------------------------------------------


def test_run_tamper_demo_returns_tamper_demo_result_dataclass(tmp_path):
    from facechain.tamper_demo import TamperDemoResult

    src = _write_valid_evidence(tmp_path)
    result = run_tamper_demo(src)
    assert isinstance(result, TamperDemoResult)
    assert result.notes  # there should be at least a 'before/after' note
