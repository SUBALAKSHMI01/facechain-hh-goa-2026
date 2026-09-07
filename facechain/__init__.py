"""FaceChain — Vision → Search → Proof → Chain.

Phase 1: image validation, hashing, face detection/embedding,
reverse image search, social filtering, and deterministic evidence
generation.

Phase 2: consent-based candidate verification (one explicitly-
approved candidate compared against a user-supplied reference image).

Phase 3: Ethereum Sepolia anchoring of the evidence hash and
independent on-chain verification (with VERIFIED / TAMPERED /
NOT_ANCHORED outcomes).

Phase 4: shortlist-demo polish — Rich/Typer terminal UI, tamper
demo, latency benchmark, README.
"""

__version__ = "0.4.0-phase4"
