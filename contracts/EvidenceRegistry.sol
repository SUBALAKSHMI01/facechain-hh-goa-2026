// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EvidenceRegistry — FaceChain Phase 3 on-chain evidence commitments.
/// @notice Stores SHA-256-derived bytes32 commitments to FaceChain evidence
///         files. Only commitments go on-chain; the evidence file itself
///         stays off-chain (see README's Security / Privacy section).
///
///         The contract does NOT verify that the underlying reverse-search
///         result, face model, or social-media post is authentic — it
///         simply records that a particular evidenceHash was anchored at
///         a particular block timestamp, by a particular submitter.
contract EvidenceRegistry {
    struct Evidence {
        bytes32 evidenceHash;
        bytes32 sourceHash;
        uint256 timestamp;
        address submitter;
    }

    /// @dev evidenceHash => Evidence record. Timestamp == 0 means "never anchored".
    mapping(bytes32 => Evidence) public evidenceRecords;

    event EvidenceRegistered(
        bytes32 indexed evidenceHash,
        bytes32 indexed sourceHash,
        uint256 timestamp,
        address indexed submitter
    );

    /// @notice Anchor an evidence commitment. Reverts if already registered.
    /// @param evidenceHash SHA-256 of the canonical FaceChain evidence.json.
    /// @param sourceHash   SHA-256 of the normalized top social-media URL.
    function registerEvidence(
        bytes32 evidenceHash,
        bytes32 sourceHash
    ) external {
        require(
            evidenceRecords[evidenceHash].timestamp == 0,
            "Evidence already registered"
        );

        evidenceRecords[evidenceHash] = Evidence({
            evidenceHash: evidenceHash,
            sourceHash: sourceHash,
            timestamp: block.timestamp,
            submitter: msg.sender
        });

        emit EvidenceRegistered(
            evidenceHash,
            sourceHash,
            block.timestamp,
            msg.sender
        );
    }

    /// @notice Read an anchored record. Returns zeroed values if not anchored.
    function getEvidence(
        bytes32 evidenceHash
    ) external view returns (
        bytes32 evidenceHashOut,
        bytes32 sourceHashOut,
        uint256 timestampOut,
        address submitterOut
    ) {
        Evidence memory e = evidenceRecords[evidenceHash];
        return (e.evidenceHash, e.sourceHash, e.timestamp, e.submitter);
    }
}
