from facechain.evidence.canonicalize import canonical_json, evidence_hash
from facechain.evidence.models import (
    Evidence,
    FaceEvidence,
    ImageEvidence,
    SearchEvidence,
)
from facechain.search.normalizer import normalize_hostname, normalize_url
from facechain.search.social_filter import (
    APPROVED_SOCIAL_DOMAINS,
    SocialCandidate,
    filter_social_candidates,
)
from facechain.search.base import ReverseSearchResult, WebMatch


def test_canonical_json_is_deterministic_regardless_of_key_order():
    a = {"b": 1, "a": 2, "c": {"z": 1, "y": 2}}
    b = {"a": 2, "c": {"y": 2, "z": 1}, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_canonical_json_uses_compact_separators():
    data = {"a": 1, "b": 2}
    assert canonical_json(data) == '{"a":1,"b":2}'


def test_evidence_hash_is_deterministic():
    data = {"x": 1, "y": [1, 2, 3]}
    assert evidence_hash(data) == evidence_hash(data)


def test_evidence_hash_changes_with_content():
    assert evidence_hash({"x": 1}) != evidence_hash({"x": 2})


def _sample_evidence() -> Evidence:
    return Evidence(
        image=ImageEvidence(sha256="a" * 64, phash="0" * 16, width=100, height=100),
        face=FaceEvidence(face_count=1, detection_confidence=0.99, embedding_dimensions=512),
        search=SearchEvidence(provider="google_cloud_vision_web_detection", had_results=False),
    )


def test_evidence_model_dump_hash_deterministic_except_timestamp():
    ev1 = _sample_evidence()
    ev2 = _sample_evidence()
    d1 = ev1.model_dump(by_alias=True)
    d2 = ev2.model_dump(by_alias=True)
    # Force identical timestamps to isolate determinism of the rest of the schema
    d1["timestamp"] = "fixed"
    d2["timestamp"] = "fixed"
    assert evidence_hash(d1) == evidence_hash(d2)


def test_normalize_hostname_strips_www_and_lowercases():
    assert normalize_hostname("https://WWW.Instagram.com/user") == "instagram.com"


def test_normalize_hostname_handles_bare_domain():
    assert normalize_hostname("https://x.com/user") == "x.com"


def test_normalize_url_strips_trailing_slash_and_fragment():
    assert normalize_url("https://X.COM/user/#section") == "https://x.com/user"


def test_social_filter_accepts_approved_domains_only():
    result = ReverseSearchResult(
        provider="test",
        pages_with_matching_images=[
            WebMatch(url="https://www.instagram.com/someone", match_type="page_with_matching_images"),
            WebMatch(url="https://example.com/not-social", match_type="page_with_matching_images"),
        ],
    )
    candidates = filter_social_candidates(result)
    assert len(candidates) == 1
    assert candidates[0].platform == "instagram.com"


def test_social_filter_deduplicates_normalized_urls():
    result = ReverseSearchResult(
        provider="test",
        full_matching_images=[
            WebMatch(url="https://twitter.com/user/", match_type="full_matching_image"),
        ],
        pages_with_matching_images=[
            WebMatch(url="https://www.twitter.com/user", match_type="page_with_matching_images"),
        ],
    )
    candidates = filter_social_candidates(result)
    assert len(candidates) == 1


def test_social_filter_rejects_subdomain_lookalikes_not_in_list():
    result = ReverseSearchResult(
        provider="test",
        pages_with_matching_images=[
            WebMatch(url="https://instagram.com.evil.example/x", match_type="page_with_matching_images"),
        ],
    )
    candidates = filter_social_candidates(result)
    assert candidates == []


def test_approved_domains_matches_blueprint_list():
    assert APPROVED_SOCIAL_DOMAINS == frozenset(
        {
            "x.com",
            "twitter.com",
            "reddit.com",
            "instagram.com",
            "facebook.com",
            "linkedin.com",
            "threads.net",
        }
    )
