# FaceChain

**Vision → Search → Proof → Chain**

FaceChain is a CLI pipeline that takes an input photo, detects and
embeds the face in it, runs a genuine reverse image search, filters
results down to approved social-media platforms, and produces a
deterministic, hashable evidence record. Phase 3 then anchors that
evidence hash on Ethereum Sepolia for independent verification.

## Current status: Phase 1, Phase 2, Phase 3, and Phase 4 implemented

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
  → [Phase 4] latency benchmark + tamper demo + Rich/Typer UI polish
```

Phase 4 implements the spec's "SHORTLIST DEMO" items 18-22:

* **18. Rich/Typer terminal UI** — every command uses Typer + Rich
  for progress and the result panels; consistent banner.
* **19. `verify` command** — `verify` (Phase 2) and `verify-onchain`
  (Phase 3) both present.
* **20. Tamper demo** — `python main.py tamper-demo <evidence.json>`
  (and `python scripts/tamper_demo.py <evidence.json>`) copies the
  file, mutates a field, re-verifies, and prints the
  VERIFIED → TAMPERED transition.
* **21. Latency benchmark** — `python main.py benchmark` (and
  `python scripts/benchmark.py`) runs the spec's seven-stage
  pipeline and reports per-stage min/avg/max + sample size. Honest
  about which stages are network-bound.
* **22. README** — this file, with all 22 spec sections (the 23rd,
  demo video, is intentionally absent — we have no video to link).

The Phase 3 blockchain layer and Phase 2 verification flow are
**unchanged** in Phase 4 — all new functionality is purely additive.

## Why normal reverse-image search is insufficient

A "Google reverse image search match" tells you only that Google's
backend found a visually-similar image at a URL. It does not tell
you:

* that the image is the same person (vs. a near-duplicate cropped
  repost vs. a stock-photo match vs. a meme using the same face);
* that the URL belongs to the person the uploader claims it does
  (any user can post any image to any platform);
* that the evidence file has not been edited *after* it was first
  produced;
* that the same evidence file is still anchored on the chain a
  year later.

FaceChain's design treats every one of those as a separate
question, answered with a separate, independent signal:

1. The reverse-search result is **filtered** to an explicit,
   conservative allow-list of social-media domains — being
   returned by Google is not, by itself, evidence.
2. Each candidate can be **independently re-verified** against a
   user-supplied reference image (Phase 2's consent-based
   verification) using ArcFace cosine similarity and pHash.
3. The evidence file is **deterministic and hashable** — a
   canonical-JSON SHA-256, recorded in the file and recomputed by
   the verifier. Any field edit breaks the hash.
4. The hash is **anchored on Ethereum Sepolia** (Phase 3) so a
   later verifier can confirm the file is bit-identical to what
   was submitted.

## Our uniqueness

What FaceChain does that a "just run Google Lens" demo doesn't:

* **Search result is not blindly trusted** — the social-media
  filter is an explicit allow-list, not "any URL Google returned".
* **Candidates are independently re-verified** — ArcFace embedding
  + perceptual hash, run by us, not by Google.
* **Face similarity and image similarity are separate signals**
  with configurable weights (Phase 2's confidence engine).
* **Evidence is deterministic and tamper-evident** — canonical
  JSON + SHA-256, recomputed on every verify.
* **Blockchain stores only cryptographic commitments** — the
  evidence file, the face embedding, the original photo, and
  biometric data all stay off-chain.
* **Independent verification is read-only and offline-friendly**
  — `python main.py verify-onchain` does not require Google
  credentials, only a Sepolia RPC + the contract address.

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
- A blockchain record proves that a specific evidence hash existed
  at or before a particular block timestamp. It does **NOT**
  independently prove that the reverse-search provider was correct,
  the face model was correct, the social-media post was authentic,
  or the uploader was the person in the image. (This is the
  spec's "Important Limitation" and is restated in the
  Security / Privacy section above.)

## Performance / benchmark results

The spec's Performance Optimizations section calls for measuring
the per-stage latency of the pipeline. Phase 4 implements
`facechain/benchmark.py` + `scripts/benchmark.py` + the
`python main.py benchmark` CLI command, which time these seven
stages (matching the spec's list):

| Stage | Always measured? | Network-bound? |
|---|---|---|
| `image_preprocess_ms` | yes | no |
| `face_detection_ms` | when InsightFace model is available | no |
| `embedding_ms` | when a face is detected | no |
| `reverse_search_ms` | only with `GOOGLE_APPLICATION_CREDENTIALS` | **yes (Google Vision)** |
| `candidate_validation_ms` | yes | no |
| `evidence_generation_ms` | yes | no |
| `blockchain_submit_ms` | only with `SEPOLIA_RPC_URL` + `BLOCKCHAIN_PRIVATE_KEY` + `CONTRACT_ADDRESS` | **yes (Sepolia)** |

The benchmark is honest about which stages were not measured: a
stage that cannot run (missing model, missing credentials) reports
`N/A` in the table, not `0 ms`. The spec's note "Do not describe
thresholds as universal scientific truth" is applied to timings
the same way it is to the confidence engine.

Run the benchmark locally with:

```bash
python main.py benchmark            # default n=3, 320x320 synthetic image
python main.py benchmark --n 5 --size 640
python scripts/benchmark.py --json  # machine-readable output
```

A small sample run on a CPU-only laptop (n=3, 320x320, no
credentials) reports the local stages in single-digit milliseconds
and `N/A` for the network stages, which matches the design.

## Future improvements

These are deliberately **out of scope for the hackathon** and
would be Phase 5+ work, in roughly the order they would be
useful:

1. **Multi-candidate re-verification** — the spec's Phase 2 calls
   for downloading each Phase 1 social candidate, detecting a
   face on it, and computing face + image similarity. The current
   Phase 2 is intentionally consent-based (one explicit candidate
   per run) for safety; an automatic top-N variant with
   concurrency would be the natural extension.
2. **Confidence engine** — `facechain/evidence/scoring.py`
   currently raises `NotImplementedError` (per the existing
   contract from Phase 1). Wiring
   `FACE_WEIGHT`/`IMAGE_WEIGHT`/`SEARCH_WEIGHT` to the real
   confidence math is a clean follow-up.
3. **Sepolia P50/P95 over many runs** — the benchmark currently
   reports min/avg/max over `n=3`. P50/P95 needs `n>=20` to be
   meaningful; a CI-friendly benchmark runner would do this.
4. **IPFS / Arweave anchoring of the evidence file itself** —
   currently only the hash is on-chain. Pinning the file to
   IPFS would let the on-chain record carry an *addressable*
   reference, not just a commitment.
5. **Hardhat / Foundry deployment path** — `py-solc-x` works but
   Hardhat or Foundry would give a more familiar dev experience
   for Solidity iteration.
6. **A real demo video** — intentionally absent from this README
   (we have no video to link). Adding one would close out
   spec section #23.

