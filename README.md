# FaceChain

**Vision → Search → Proof → Chain**

FaceChain is a CLI pipeline that takes an input photo, detects and
embeds the face in it, runs a genuine reverse image search, filters
results down to approved social-media platforms, and produces a
deterministic, hashable evidence record. A later phase will anchor
that evidence hash on Ethereum Sepolia for independent verification.

## Current status: Phase 1 only

This repository currently implements **Phase 1** of the full pipeline:

```
INPUT IMAGE
  → image validation / normalization
  → SCRFD face detection (InsightFace, buffalo_l)
  → ArcFace face embedding (512-D)
  → Google Cloud Vision Web Detection (reverse image search)
  → social-media candidate filtering
  → deterministic evidence.json
  → SHA-256 evidence hash
```

**Not implemented yet** (Phase 2+):
- Candidate re-verification (comparing the input face against faces
  found in candidate matches)
- Confidence scoring (`FACE_WEIGHT` / `IMAGE_WEIGHT` / `SEARCH_WEIGHT`
  are read from config but not yet consumed)
- Ethereum Sepolia anchoring (`facechain/blockchain/` is placeholder
  interfaces only — nothing in it connects to any network)
- `EvidenceRegistry.sol` deployment

Blockchain functionality is **not** implemented in this phase. Do not
expect `facechain/blockchain/*` or `contracts/EvidenceRegistry.sol` to
do anything — they raise `NotImplementedError` on purpose.

## Requirements

- Python 3.11 or 3.12
- A Google Cloud project with the **Cloud Vision API** enabled and a
  service-account JSON key (for the reverse-image-search step)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

InsightFace will download the `buffalo_l` model bundle to
`~/.insightface/` the first time it runs.

## Google Cloud Vision setup

1. Create (or use) a Google Cloud project.
2. Enable the **Cloud Vision API** for that project.
3. Create a service account with Vision API access and download its
   JSON key.
4. Copy `.env.example` to `.env` and point
   `GOOGLE_APPLICATION_CREDENTIALS` at that key file:

```bash
cp .env.example .env
# then edit .env:
# GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
```

Never commit `.env` or the credential JSON file — both are already
listed in `.gitignore`.

## Environment variables

| Variable | Required for Phase 1 | Purpose |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes | Google Cloud Vision auth |
| `SERPAPI_KEY` | No | Reserved for a future/alternate search provider |
| `FACE_WEIGHT`, `IMAGE_WEIGHT`, `SEARCH_WEIGHT` | No (read, unused) | Phase 2 confidence engine |
| `FACE_MATCH_THRESHOLD`, `FINAL_MATCH_THRESHOLD` | No (read, unused) | Phase 2 confidence engine |

## Running Phase 1

```bash
python main.py analyze path/to/photo.jpg
```

This will:
1. Validate the image and compute its SHA-256 and pHash.
2. Detect exactly one face (SCRFD) and produce its 512-D ArcFace embedding.
3. Send the image to Google Cloud Vision Web Detection.
4. Filter results down to `x.com`, `twitter.com`, `reddit.com`,
   `instagram.com`, `facebook.com`, `linkedin.com`, `threads.net`.
5. Write `artifacts/evidence/evidence.json`.
6. Print its canonical SHA-256 evidence hash.

If no face, more than one face, an invalid image, or a reverse-search
failure occurs, the CLI reports the specific problem — it never
fabricates a successful result.

## Running tests

```bash
pytest tests/ -v
```

Phase 1 tests do not require live Google Cloud credentials — they
cover hashing, cosine similarity, canonical JSON / evidence-hash
determinism, URL normalization, and social-domain filtering directly.

## Known limitations (Phase 1)

- Requires exactly one detected face per image; multi-face and no-face
  images are rejected with a clear error rather than guessed at.
- Reverse image search relies entirely on what Google Cloud Vision
  Web Detection actually returns — no candidate is invented, assumed,
  or hardcoded, and an empty result set is reported as such.
- No face-similarity re-verification of candidate matches yet — a
  "social candidate" here means *the URL came back from Google's web
  detection and its domain is on the approved list*, not that the
  face in it has been confirmed to match.
- No confidence score is computed yet (`confidence` is always `null`
  in evidence.json).
- No blockchain anchoring — evidence hashes are computed locally only.
