"""URL normalization used before social-domain filtering and deduplication."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_hostname(url: str) -> str:
    """Lowercase hostname with a leading 'www.' stripped. Empty string if unparsable."""
    try:
        hostname = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    hostname = hostname.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication purposes:

    - lowercase scheme and host
    - strip 'www.'
    - drop fragment
    - strip a single trailing slash from the path
    """
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    hostname = normalize_hostname(url)
    netloc = hostname
    if parts.port:
        netloc = f"{hostname}:{parts.port}"

    path = parts.path or ""
    if path.endswith("/") and path != "/":
        path = path[:-1]

    return urlunsplit((scheme, netloc, path, parts.query, ""))
