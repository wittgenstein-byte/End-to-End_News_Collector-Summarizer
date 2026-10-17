"""
core/url_utils.py
─────────────────────────────────────────────────────────────────
SOLID  S — URL canonicalization, cluster fingerprinting, and
           synthesis cache key computation.
GRASP  Information Expert — Pure deterministic functions for
           membership hashing and cache invalidation.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_QUERY_PARAMS: frozenset[str] = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "zanpid",
    "igshid",
    "ref",
    "ref_src",
    "ref_url",
    "reference",
    "_hsenc",
    "_hsmi",
    "mc_eid",
    "mc_cid",
    "spm",
    "from",
    "feature",
})


def canonicalize_url(url: str) -> str:
    """
    Deterministically normalize a web URL for storage, deduplication, and fingerprinting.

    Transformations:
      - Strips leading/trailing whitespace.
      - Normalizes scheme to lowercase (defaults to 'https' if missing).
      - Normalizes hostname to lowercase, removes standard default ports, and strips leading 'www.'.
      - Normalizes path: collapses consecutive slashes, removes trailing slash (except root '/').
      - Strips tracking query parameters (utm_*, fbclid, etc.) and sorts remaining params deterministically.
      - Drops fragments (#...).
    """
    if not url or not isinstance(url, str):
        return ""

    raw = url.strip()
    if not raw:
        return ""

    # Ensure URL has scheme for urlsplit
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "https://" + raw

    try:
        parts = urlsplit(raw)
    except Exception:
        return raw.strip().rstrip("/")

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # Normalize default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Strip 'www.' prefix
    netloc = netloc.removeprefix("www.")

    # Normalize path
    path = parts.path or "/"
    # Collapse multiple consecutive slashes
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Normalize query params
    clean_query = ""
    if parts.query:
        query_pairs = parse_qsl(parts.query, keep_blank_values=True)
        filtered_pairs = [
            (k, v)
            for k, v in query_pairs
            if k.lower() not in _TRACKING_QUERY_PARAMS
            and not k.lower().startswith("utm_")
        ]
        if filtered_pairs:
            # Deterministic sorting by key, then value
            filtered_pairs.sort(key=lambda pair: (pair[0], pair[1]))
            clean_query = urlencode(filtered_pairs)

    return urlunsplit((scheme, netloc, path, clean_query, ""))


def compute_cluster_fingerprint(urls: list[str]) -> str:
    """
    Compute a deterministic 16-character hex fingerprint of the member article set.
    Returns 'fp_empty' if the URL set is empty after canonicalization.
    """
    if not urls:
        return "fp_empty"

    canon_set: set[str] = set()
    for u in urls:
        canon = canonicalize_url(u)
        if canon:
            canon_set.add(canon)

    if not canon_set:
        return "fp_empty"

    sorted_urls = sorted(canon_set)
    payload = "|".join(sorted_urls).encode("utf-8")
    hex_digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"fp_{hex_digest}"


def compute_synthesis_cache_key(
    event_id: str,
    cluster_fingerprint: str,
    articles: list[dict[str, Any]] | None = None,
    prompt_version: str = "v4.0",
) -> str:
    """
    Compute a deterministic 24-character hex synthesis cache key.
    Guarantees invalidation on membership change, article title/summary update,
    or prompt version upgrade.
    """
    # Sort articles deterministically by canonical URL
    def sort_key(a: dict[str, Any]) -> str:
        return canonicalize_url(str(a.get("url", "")))

    sorted_articles = sorted(articles or [], key=sort_key)
    article_digests: list[str] = []
    for a in sorted_articles:
        canon_u = canonicalize_url(str(a.get("url", "")))
        title_str = str(a.get("title", "")).strip()
        summary_str = str(a.get("summary", "")).strip()
        article_digests.append(f"{canon_u}:{title_str}:{summary_str}")

    content_digest = hashlib.sha256("||".join(article_digests).encode("utf-8")).hexdigest()[:16]
    raw_key = f"{event_id}:{cluster_fingerprint}:{content_digest}:{prompt_version}"
    hex_digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
    return f"synth_{hex_digest}"
