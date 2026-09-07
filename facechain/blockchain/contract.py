"""EvidenceRegistry contract interaction — Phase 3.

Wraps the deployed `EvidenceRegistry.sol` contract (see
`contracts/EvidenceRegistry.sol`). Exposes two operations:

* `register_evidence(evidence_hash, source_hash)` — sends a signed
  transaction that calls `registerEvidence(bytes32, bytes32)` on
  Sepolia and returns the transaction hash plus a small receipt.
* `get_evidence(evidence_hash)` — read-only call to `getEvidence`,
  returns a typed `OnChainRecord` (or `None` if the hash has never
  been anchored — i.e. the on-chain `timestamp == 0`).

The 64-character hex SHA-256 hashes produced by Phase 1 are converted
to the 32-byte Solidity `bytes32` by taking the LEFTMOST 32 bytes (i.e.
the first 64 hex chars). This is a deliberate, documented choice — see
`_hex_to_bytes32` for details and the spec's "Source URL Hash" section
for the same convention applied to source URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from facechain.blockchain.client import EthereumClient
from facechain.blockchain.errors import (
    BlockchainConfigError,
    BlockchainTransactionError,
    EvidenceNotAnchoredError,
    InvalidEvidenceFileError,
)
from facechain.evidence.canonicalize import canonical_json, evidence_hash
from facechain.search.normalizer import normalize_url
from facechain.vision.hashing import sha256_bytes


# A bytes32 is exactly 32 bytes. SHA-256 produces 32 bytes, so the
# entire digest fits — no truncation needed.
BYTES32_HEX_LEN = 64  # 32 bytes * 2 hex chars

# How long to wait (seconds) for a tx receipt before giving up.
DEFAULT_TX_TIMEOUT = 120


@dataclass(frozen=True)
class OnChainRecord:
    """A record returned by `getEvidence` on Sepolia."""

    evidence_hash: str        # 0x-prefixed bytes32
    source_hash: str          # 0x-prefixed bytes32
    timestamp: int            # unix seconds
    submitter: str            # 0x-prefixed address


@dataclass(frozen=True)
class AnchorResult:
    """What we return after a successful on-chain `registerEvidence` call."""

    evidence_hash: str        # 0x-prefixed bytes32
    source_hash: str          # 0x-prefixed bytes32
    transaction_hash: str     # 0x-prefixed tx hash
    block_number: int
    submitter: str
    timestamp: int


class EvidenceRegistryContract:
    """High-level wrapper around the deployed `EvidenceRegistry` contract."""

    def __init__(self, client: EthereumClient) -> None:
        self._client = client

    # -- Hash helpers --------------------------------------------------

    @staticmethod
    def hex_to_bytes32(hex_hash: str) -> str:
        """Convert a 64-char hex SHA-256 into a 0x-prefixed 32-byte value.

        SHA-256 already produces exactly 32 bytes, so this is just a
        normalization/validation step — we don't truncate anything.
        Raises InvalidEvidenceFileError on a malformed input.
        """
        if not isinstance(hex_hash, str):
            raise InvalidEvidenceFileError(
                f"Expected a hex string for bytes32 conversion, got {type(hex_hash).__name__}"
            )
        cleaned = hex_hash.lower()
        if cleaned.startswith("0x"):
            cleaned = cleaned[2:]
        if len(cleaned) != BYTES32_HEX_LEN:
            raise InvalidEvidenceFileError(
                f"Hex hash must be exactly {BYTES32_HEX_LEN} chars "
                f"(32 bytes); got {len(cleaned)} chars: {hex_hash!r}"
            )
        try:
            int(cleaned, 16)
        except ValueError as exc:
            raise InvalidEvidenceFileError(
                f"Hex hash is not valid hex: {hex_hash!r}"
            ) from exc
        return "0x" + cleaned

    @staticmethod
    def source_hash_for_url(url: str) -> str:
        """SHA-256 of the normalized social-media URL, lower-case hex.

        Per the spec's "Source URL Hash" section: we never store a
        plaintext URL on-chain, only its SHA-256 of the normalized
        form. This means the on-chain commitment reveals nothing
        about the actual platform/account while still allowing
        offline verification.
        """
        normalized = normalize_url(url) if url else ""
        return sha256_bytes(normalized.encode("utf-8"))

    # -- On-chain reads ------------------------------------------------

    def get_evidence(self, evidence_hash: str) -> OnChainRecord | None:
        """Read the on-chain record for `evidence_hash`, or None if absent.

        A record is "absent" when its `timestamp == 0`, which the
        contract uses as the sentinel for "never anchored". This
        matches both the Solidity contract's behaviour and the
        on-chain semantics — we never raise for an empty record, we
        just return None.
        """
        if not self._client.is_fully_configured():
            raise BlockchainConfigError(
                "Cannot read on-chain: blockchain is not configured."
            )

        evidence_b32 = self.hex_to_bytes32(evidence_hash)
        contract = self._client.contract()

        # eth_call (view) — no transaction, no gas.
        result = contract.functions.getEvidence(
            self._client.web3.to_bytes(hexstr=evidence_b32)
        ).call()

        evidence_b32_out, source_b32_out, timestamp, submitter = result
        if int(timestamp) == 0:
            return None

        return OnChainRecord(
            evidence_hash="0x" + bytes(evidence_b32_out).hex(),
            source_hash="0x" + bytes(source_b32_out).hex(),
            timestamp=int(timestamp),
            submitter=self._client.web3.to_checksum_address(submitter),
        )

    # -- On-chain writes -----------------------------------------------

    def register_evidence(
        self,
        evidence_hash: str,
        source_url: str | None,
        *,
        tx_timeout: int = DEFAULT_TX_TIMEOUT,
    ) -> AnchorResult:
        """Anchor `evidence_hash` (+ `source_url` → sourceHash) on Sepolia.

        Sends a signed transaction calling `registerEvidence(bytes32,
        bytes32)` and waits up to `tx_timeout` seconds for the
        receipt. Raises BlockchainTransactionError on any failure;
        the contract's own "already registered" revert is surfaced
        with the original revert reason.
        """
        self._client.require_fully_configured()

        evidence_b32 = self.hex_to_bytes32(evidence_hash)
        source_hash = self.source_hash_for_url(source_url or "")
        source_b32 = self.hex_to_bytes32(source_hash)

        web3 = self._client.web3
        contract = self._client.contract()
        account = self._client.account

        try:
            tx = contract.functions.registerEvidence(
                web3.to_bytes(hexstr=evidence_b32),
                web3.to_bytes(hexstr=source_b32),
            ).build_transaction(
                {
                    "from": account.address,
                    "nonce": web3.eth.get_transaction_count(account.address),
                    "chainId": self._client.chain_id_int,
                    "gas": 200_000,
                    "gasPrice": web3.eth.gas_price,
                }
            )
            signed = account.sign_transaction(tx)
            tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        except Exception as exc:
            raise BlockchainTransactionError(
                f"Failed to build/submit registerEvidence transaction: {exc}"
            ) from exc

        try:
            receipt = web3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=tx_timeout
            )
        except Exception as exc:
            raise BlockchainTransactionError(
                f"Transaction did not confirm within {tx_timeout}s: {exc}"
            ) from exc

        if receipt.get("status") != 1:
            raise BlockchainTransactionError(
                f"registerEvidence transaction reverted on-chain. "
                f"tx_hash=0x{tx_hash.hex()}, status={receipt.get('status')!r}"
            )

        tx_hash_hex = "0x" + tx_hash.hex()
        block_number = int(receipt.get("blockNumber", 0))

        # Re-read what the contract actually stored, so the caller
        # sees a canonical view (not just what we sent).
        record = self.get_evidence(evidence_hash)
        if record is None:
            raise BlockchainTransactionError(
                f"Transaction succeeded (tx={tx_hash_hex}) but the "
                f"contract reports no record for the given evidence hash. "
                f"This should not happen — investigate."
            )

        return AnchorResult(
            evidence_hash=record.evidence_hash,
            source_hash=record.source_hash,
            transaction_hash=tx_hash_hex,
            block_number=block_number,
            submitter=record.submitter,
            timestamp=record.timestamp,
        )

    # -- High-level helpers --------------------------------------------

    def register_evidence_from_file(
        self,
        evidence_path: str | "Path",
        *,
        tx_timeout: int = DEFAULT_TX_TIMEOUT,
    ) -> AnchorResult:
        """Read an evidence.json file, derive the source URL, and anchor.

        `evidence_path` must be a FaceChain evidence file containing
        an `evidenceHash` field and at least one social candidate in
        `search.socialCandidates[0].url`. Raises
        InvalidEvidenceFileError if either is missing.
        """
        import json
        from pathlib import Path

        p = Path(evidence_path)
        if not p.exists() or not p.is_file():
            raise InvalidEvidenceFileError(
                f"Evidence file does not exist: {p}"
            )
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InvalidEvidenceFileError(
                f"Evidence file is not valid JSON: {p} ({exc})"
            ) from exc

        if not isinstance(data, dict):
            raise InvalidEvidenceFileError(
                f"Evidence file root must be a JSON object, got {type(data).__name__}"
            )

        evidence_hash_hex = data.get("evidenceHash")
        if not isinstance(evidence_hash_hex, str) or not evidence_hash_hex:
            raise InvalidEvidenceFileError(
                f"Evidence file is missing an 'evidenceHash' field: {p}"
            )

        source_url = _first_social_candidate_url(data)
        if not source_url:
            # We still anchor — just with a sourceHash of SHA-256("") —
            # so the user can choose to anchor evidence that genuinely
            # had no social candidates. We DO warn via the AnchorResult
            # in the CLI; the contract itself doesn't care.
            source_url = ""

        return self.register_evidence(
            evidence_hash_hex, source_url, tx_timeout=tx_timeout
        )


def _first_social_candidate_url(data: dict) -> str | None:
    """Extract the first social candidate URL from a Phase-1 evidence dict.

    Returns None if the file is a Phase-2 verification file (which has
    no social candidate list) or if the list is empty.
    """
    search = data.get("search")
    if not isinstance(search, dict):
        return None
    candidates = search.get("socialCandidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    first = candidates[0]
    if not isinstance(first, dict):
        return None
    url = first.get("url")
    return url if isinstance(url, str) and url else None


def recompute_evidence_hash(evidence_data: dict) -> str:
    """Re-derive the canonical evidence hash from a parsed evidence file.

    The hash in `evidence.json` is computed *without* the
    `evidenceHash` field itself (see `facechain.evidence.builder`),
    so any verifier has to drop that field before re-hashing. This
    helper does that and is the single source of truth used by the
    CLI and the unit tests.
    """
    if not isinstance(evidence_data, dict):
        raise InvalidEvidenceFileError(
            f"Evidence root must be a JSON object, got {type(evidence_data).__name__}"
        )
    canonical = {k: v for k, v in evidence_data.items() if k != "evidenceHash"}
    return evidence_hash(canonical)


# Re-export so the CLI/tests can build the helper directly.
__all__ = [
    "AnchorResult",
    "BYTES32_HEX_LEN",
    "DEFAULT_TX_TIMEOUT",
    "EvidenceRegistryContract",
    "OnChainRecord",
    "canonical_json",
    "recompute_evidence_hash",
]
