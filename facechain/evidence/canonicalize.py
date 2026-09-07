"""Deterministic canonical JSON serialization and evidence hashing.

The same Evidence object must always produce the same canonical JSON
string, and therefore the same SHA-256 hash — that's the whole point
of anchoring it on-chain later. This module is the single place that
performs that serialization so every caller gets identical bytes.
"""

from __future__ import annotations

import json
from typing import Any

from facechain.vision.hashing import sha256_bytes


def canonical_json(data: dict[str, Any]) -> str:
    """Serialize `data` to a canonical JSON string.

    Uses sorted keys and compact separators, matching:
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def evidence_hash(data: dict[str, Any]) -> str:
    """SHA-256 hex digest of the canonical JSON form of `data`."""
    canonical = canonical_json(data)
    return sha256_bytes(canonical.encode("utf-8"))
