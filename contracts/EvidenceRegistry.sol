// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EvidenceRegistry (Phase 2 placeholder)
/// @notice NOT IMPLEMENTED IN PHASE 1. This is a structural placeholder
///         only, showing where the on-chain evidence-hash registry will
///         live once blockchain anchoring is built. Do not deploy.
contract EvidenceRegistry {
    // Phase 2: will store evidenceHash => (submitter, blockTimestamp)
    // and expose an anchor(bytes32 evidenceHash) function plus a
    // read-only lookup. Intentionally left unimplemented for Phase 1.
}
