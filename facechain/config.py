"""Central configuration for FaceChain, loaded from environment variables.

All values have sane defaults for Phase 1 so the CLI can run with only
the Google Cloud Vision credential set. Weights/thresholds are defined
now (per the blueprint) even though they are only consumed starting in
Phase 2's confidence engine, so the schema doesn't have to change later.
Phase 3 adds optional Sepolia/contract settings (all default to None so
the rest of the pipeline keeps working without blockchain credentials).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_optional(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- Credentials / external services -----------------------------
    google_application_credentials: str | None = field(
        default_factory=lambda: os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )
    serpapi_key: str | None = field(default_factory=lambda: os.getenv("SERPAPI_KEY"))

    # --- Blockchain (Phase 3 — Sepolia) -------------------------------
    # All four are optional so the rest of the pipeline (Phases 1+2) keeps
    # working without any blockchain credentials. The anchor / verify
    # commands will refuse to run if these aren't set.
    sepolia_rpc_url: str | None = field(
        default_factory=lambda: _get_optional("SEPOLIA_RPC_URL")
    )
    blockchain_private_key: str | None = field(
        default_factory=lambda: _get_optional("BLOCKCHAIN_PRIVATE_KEY")
    )
    contract_address: str | None = field(
        default_factory=lambda: _get_optional("CONTRACT_ADDRESS")
    )
    chain_id: int = field(default_factory=lambda: _get_int("CHAIN_ID", 11155111))

    # --- Confidence engine weights (Phase 2 consumers) -----------------
    face_weight: float = field(default_factory=lambda: _get_float("FACE_WEIGHT", 0.55))
    image_weight: float = field(default_factory=lambda: _get_float("IMAGE_WEIGHT", 0.25))
    search_weight: float = field(default_factory=lambda: _get_float("SEARCH_WEIGHT", 0.20))

    face_match_threshold: float = field(
        default_factory=lambda: _get_float("FACE_MATCH_THRESHOLD", 0.70)
    )
    final_match_threshold: float = field(
        default_factory=lambda: _get_float("FINAL_MATCH_THRESHOLD", 0.75)
    )

    # --- Paths ----------------------------------------------------------
    artifacts_dir: Path = field(default_factory=lambda: Path("artifacts"))
    evidence_dir: Path = field(default_factory=lambda: Path("artifacts/evidence"))
    logs_dir: Path = field(default_factory=lambda: Path("artifacts/logs"))

    # --- InsightFace model -----------------------------------------------
    insightface_model_name: str = "buffalo_l"
    insightface_det_size: tuple[int, int] = (640, 640)

    # --- Image handling ---------------------------------------------------
    max_image_dimension: int = 4096  # resize threshold for processing copy

    def ensure_dirs(self) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
