# FaceChain

**Vision → Search → Proof → Chain**

FaceChain is a CLI pipeline that takes an input photo, detects and
embeds the face in it, runs a genuine reverse image search, filters
results down to approved social-media platforms, and produces a
deterministic, hashable evidence record. Phase 3 then anchors that
evidence hash on Ethereum Sepolia for independent verification.

## Current status: Phase 1, Phase 2 (consent verification), and Phase 3 (Sepolia anchoring) implemented

```
INPUT IMAGE
  → image validation / normalization
  → SCRFD face detection (InsightFace, buffalo_l)
  → ArcFace face embedding (512-D)
  → Google Cloud Vision Web Detection (reverse image search)
  → social-media candidate filtering
  → deterministic evidence.json
  → SHA-256 evidence hash
  → [Phase 3] anchor evidenceHash + sourceHash on Sepolia
  → [Phase 3] independent verify (VERIFIED / TAMPERED / NOT_ANCHORED)
```

The Phase 3 blockchain layer is purely additive. Phase 1 and Phase 2
behave exactly as before when no blockchain env vars are set.

## Phase 3 — blockchain anchoring

Phase 3 adds:

* A working **`contracts/EvidenceRegistry.sol`** with
  `registerEvidence(bytes32 evidenceHash, bytes32 sourceHash)` and
  `getEvidence(bytes32 evidenceHash)`.
* A `web3.py`-based **`EthereumClient`** that holds the Sepolia
  RPC URL, signing key, and contract address, with an injectable
  `web3=` seam for tests.
* An **`EvidenceRegistryContract`** wrapper that turns a 64-char hex
  SHA-256 into a 32-byte `bytes32`, derives `sourceHash` from the
  normalized top social URL, builds and signs the transaction, waits
  for the receipt, and returns the on-chain `AnchorResult`.
* A read-only **`verifier.verify_evidence_file`** that recomputes the
  canonical evidence hash from a local `evidence.json` and compares
  it against `getEvidence(evidenceHash)` on Sepolia, returning one of
  `VERIFIED`, `TAMPERED`, or `NOT_ANCHORED`.
* A deployer script `python scripts/deploy_contract.py` that compiles
  with `py-solc-x` and deploys, OR you can use Remix (the spec's
  recommended fast path) and paste the address into `.env`.
* Two new CLI commands (additive — the existing `analyze` and
  `verify` commands are unchanged):
  - `python main.py anchor <evidence.json>` — anchor on Sepolia
  - `python main.py verify-onchain <evidence.json>` — verify against Sepolia

### Only commitments go on-chain

The on-chain record is **only**:
- `evidenceHash` (32 bytes)
- `sourceHash` = SHA-256(normalized social URL), 32 bytes
- `block.timestamp`
- `msg.sender`

The evidence file itself, the face embedding, the original photo, and
any biometric data stay off-chain. See `Security / Privacy` below.

## Requirements

- Python 3.11 or 3.12
- A Google Cloud project with the **Cloud Vision API** enabled and a
  service-account JSON key (for the reverse-image-search step)
- For Phase 3: a Sepolia RPC URL, a Sepolia test wallet private key,
  and a deployed `EvidenceRegistry` contract address

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If you also want the in-Python deploy path:

```bash
pip install py-solc-x
```

InsightFace will download the `buffalo_l` model bundle to
`~/.insightface/` the first time it runs.

## Environment variables

| Variable | Required for | Purpose |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Phase 1 | Google Cloud Vision auth |
| `SERPAPI_KEY` | Optional | Reserved future/alternate search provider |
| `FACE_WEIGHT`, `IMAGE_WEIGHT`, `SEARCH_WEIGHT` | Phase 2 | Confidence engine weights (configurable; engineering heuristic) |
| `FACE_MATCH_THRESHOLD`, `FINAL_MATCH_THRESHOLD` | Phase 2 | Match thresholds |
| `SEPOLIA_RPC_URL` | Phase 3 | Sepolia HTTP RPC endpoint |
| `BLOCKCHAIN_PRIVATE_KEY` | Phase 3 | Test-wallet signing key (test ETH only) |
| `CONTRACT_ADDRESS` | Phase 3 | Deployed `EvidenceRegistry` address |
| `CHAIN_ID` | Phase 3 | Defaults to 11155111 (Sepolia) |

## Running Phase 1

```bash
python main.py analyze path/to/photo.jpg
```

Writes `artifacts/evidence/evidence.json` and prints its canonical
SHA-256 evidence hash. If no face, more than one face, an invalid
image, or a reverse-search failure occurs, the CLI reports the
specific problem — it never fabricates a successful result.

## Running Phase 2 (consent verification)

```bash
python main.py verify reference.jpg "https://instagram.com/someone"
```

Compares one explicitly-approved candidate against a user-supplied
reference image and writes `artifacts/evidence/verification.json`.

## Running Phase 3 (blockchain)

After running Phase 1 (or Phase 2) you have an `evidence.json`. First
deploy the contract (Remix is fastest):

1. Open https://remix.ethereum.org
2. Paste `contracts/EvidenceRegistry.sol`, compile with 0.8.20+.
3. Connect MetaMask on Sepolia, deploy, copy the address.
4. Set `CONTRACT_ADDRESS=0x...` in your `.env`.

Or run `python scripts/deploy_contract.py` if you have `py-solc-x`.

Then:

```bash
# Anchor the evidence hash on Sepolia (signed tx)
python main.py anchor artifacts/evidence/evidence.json

# Later (or in a different machine): re-verify
python main.py verify-onchain artifacts/evidence/evidence.json
```

`verify-onchain` will print one of:

```
RESULT  VERIFIED          # local hash == on-chain hash, file intact
RESULT  TAMPERED          # local hash != on-chain, or file was edited
RESULT  NOT_ANCHORED      # no on-chain record for this hash yet
```

A live tamper demo: edit `confidence` (or any other field) in
`artifacts/evidence/evidence.json`, re-run `verify-onchain`, and
observe `TAMPERED`.

## Security / Privacy

The contract records only:
- `evidenceHash` (32-byte SHA-256 of the canonical evidence file)
- `sourceHash` (32-byte SHA-256 of the normalized social URL)
- `block.timestamp`
- `msg.sender`

The evidence file itself, the face embedding, the original photo, and
biometric data **never go on-chain**. The on-chain record proves that
a specific evidence hash existed at or before a particular block
timestamp — it does **not** prove that the reverse-search provider,
the face model, the social-media post, or the uploader were
authentic. This limitation is also stated in the spec.

## Running tests

```bash
pytest tests/ -v
```

Phase 1, Phase 2, and Phase 3 tests do not require live Google
Cloud or Sepolia credentials — Phase 3 tests inject a mock
`web3`/`contract` object so they run offline.

## Known limitations

- Phase 1 requires exactly one detected face per image; multi-face
  and no-face images are rejected with a clear error rather than
  guessed at.
- Reverse image search relies entirely on what Google Cloud Vision
  Web Detection actually returns — no candidate is invented, assumed,
  or hardcoded.
- Phase 2 is consent-based: it does one comparison, not a multi-
  candidate ranking. See `facechain/verification.py` for the
  documented scope.
- Phase 3 only anchors what the spec says to anchor: `evidenceHash`
  + `sourceHash`. Tamper detection is read-only and never modifies
  the evidence file.
- Phase 3 requires a deployed `EvidenceRegistry` and a funded Sepolia
  test wallet to actually submit a transaction; without those env
  vars set, `anchor` / `verify-onchain` exit cleanly with a clear
  "blockchain not configured" error.
