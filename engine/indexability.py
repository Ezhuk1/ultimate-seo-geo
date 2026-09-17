"""
Indexability Matrix Evaluation Engine.

Provides an 8-vector indexability assessment for web documents:
1. HTTP Status (200 / 3xx / 4xx / 5xx)
2. Canonical Tag Relationship (self / other / missing / invalid)
3. Meta Robots Directive (index / noindex)
4. X-Robots-Tag HTTP Header (index / noindex)
5. Robots.txt Crawler Authorization (allowed / blocked)
6. XML Sitemap Inclusion (included / missing / unknown)
7. Internal Link Connectivity (linked / orphan candidate)
8. Initial Rendered Content Presence (present / missing)

Computes a holistic Indexability Verdict:
- INDEXABLE: Document is accessible and indexable across all vectors.
- BLOCKED: Critical blocker prevents indexing (HTTP error, noindex, robots disallow, empty CSR).
- AMBIGUOUS: Conflicting signals (canonical to other URL, redirect, orphan candidate, header mismatch).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from urllib.parse import urlsplit


VERDICT_INDEXABLE = "INDEXABLE"
VERDICT_BLOCKED = "BLOCKED"
VERDICT_AMBIGUOUS = "AMBIGUOUS"


@dataclass
class IndexabilityMatrix:
    target_url: str
    http_status_code: int
    http_status_label: str
    canonical_status: str  # "self", "other", "missing", "invalid"
    canonical_url: Optional[str]
    meta_robots_status: str  # "index", "noindex"
    x_robots_status: str  # "index", "noindex"
    robots_txt_status: str  # "allowed", "blocked"
    sitemap_status: str  # "included", "missing", "unknown"
    internal_links_status: str  # "linked", "orphan candidate"
    rendered_content_status: str  # "present", "missing"
    verdict: str  # "INDEXABLE", "BLOCKED", "AMBIGUOUS"
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        blockers = []
        if self.http_status_code >= 400:
            blockers.append(f"HTTP {self.http_status_code}")
        if self.meta_robots_status == "noindex":
            blockers.append("meta robots noindex")
        if self.x_robots_status == "noindex":
            blockers.append("X-Robots-Tag noindex")
        if self.robots_txt_status == "blocked":
            blockers.append("robots.txt disallow")
        if self.rendered_content_status in ("missing", "soft_404"):
            blockers.append(f"rendered content {self.rendered_content_status}")

        conf_score = 100 if self.verdict == VERDICT_INDEXABLE else (0 if self.verdict == VERDICT_BLOCKED else 50)
        return {
            "target_url": self.target_url,
            "verdict": self.verdict,
            "confidence_score": conf_score,
            "blockers": blockers,
            "reasons": self.reasons,
            "vectors": {
                "http_status": {"status": self.http_status_label, "detail": f"Status code {self.http_status_code}"},
                "canonical": {"status": self.canonical_status, "detail": self.canonical_url or "None"},
                "meta_robots": {"status": self.meta_robots_status, "detail": f"Directive: {self.meta_robots_status}"},
                "x_robots_tag": {"status": self.x_robots_status, "detail": f"Header: {self.x_robots_status}"},
                "robots_txt": {"status": self.robots_txt_status, "detail": f"Search bots: {self.robots_txt_status}"},
                "sitemap": {"status": self.sitemap_status, "detail": f"Target in sitemap: {self.sitemap_status}"},
                "internal_links": {"status": self.internal_links_status, "detail": f"Connectivity: {self.internal_links_status}"},
                "rendered_content": {"status": self.rendered_content_status, "detail": f"Initial HTML: {self.rendered_content_status}"}
            }
        }


def _normalize_for_url_compare(url: str) -> str:
    parsed = urlsplit(url.strip())
    netloc = parsed.netloc.lower().split(":")[0]
    path = parsed.path.rstrip("/") if parsed.path not in ("", "/") else "/"
    return f"{parsed.scheme.lower()}://{netloc}{path}"


def evaluate_indexability_matrix(
    target_url: str,
    http_res: Dict[str, Any],
    html_data: Dict[str, Any],
    robots_simulation: Optional[Dict[str, Any]] = None,
    sitemap_res: Optional[Any] = None
) -> IndexabilityMatrix:
    """
    Evaluates 8 key indexation vectors and returns a consolidated IndexabilityMatrix.
    """
    reasons: List[str] = []
    is_blocked = False
    is_ambiguous = False

    # 1. HTTP Status
    code = http_res.get("status_code", 0)
    status_label = "200 OK" if code == 200 else f"HTTP {code}"
    if code >= 400:
        status_label = f"HTTP {code} Client/Server Error"
        is_blocked = True
        reasons.append(f"HTTP status code {code} prevents indexing.")
    elif 300 <= code < 400 or (http_res.get("redirect_chain") and len(http_res["redirect_chain"]) > 0):
        status_label = f"HTTP {code} Redirect"
        is_ambiguous = True
        reasons.append("Target URL redirects to a different destination.")

    # 2. Canonical Status
    canon_info = html_data.get("canonical", {})
    canon_val = canon_info.get("value")
    canon_count = canon_info.get("count", 0)
    in_body = canon_info.get("in_body", False)

    if canon_count > 1 or in_body:
        canonical_status = "invalid"
        is_ambiguous = True
        reasons.append("Canonical declaration is invalid (multiple tags or placed in body).")
    elif not canon_val:
        canonical_status = "missing"
        if "?" in target_url:
            is_ambiguous = True
            reasons.append("Missing canonical tag on parameter URL creates duplicate content ambiguity.")
    else:
        norm_target = _normalize_for_url_compare(target_url)
        norm_canon = _normalize_for_url_compare(canon_val)
        if norm_target == norm_canon:
            canonical_status = "self"
        else:
            canonical_status = "other"
            is_ambiguous = True
            reasons.append(f"Canonical points to a different destination: {canon_val}")

    # 3. Meta Robots
    meta_rob = html_data.get("meta_robots", {})
    if meta_rob.get("is_noindex"):
        meta_robots_status = "noindex"
        is_blocked = True
        reasons.append("Meta robots specifies 'noindex'.")
    else:
        meta_robots_status = "index"

    # 4. X-Robots-Tag
    x_dirs = http_res.get("x_robots_directives", [])
    x_bot_dirs = http_res.get("x_robots_bot_directives", {})
    has_x_noindex = "noindex" in x_dirs or "none" in x_dirs or any("noindex" in d for d in x_bot_dirs.values())
    if has_x_noindex:
        x_robots_status = "noindex"
        is_blocked = True
        reasons.append("X-Robots-Tag HTTP header specifies 'noindex'.")
    else:
        x_robots_status = "index"

    # 5. Robots.txt Access
    robots_blocked = False
    if robots_simulation:
        for bot in ("Googlebot", "Bingbot"):
            if bot in robots_simulation:
                if not robots_simulation[bot].get("target_allowed", True):
                    robots_blocked = True
                    break
    if robots_blocked:
        robots_txt_status = "blocked"
        is_blocked = True
        reasons.append("Robots.txt blocks search engine crawlers from target route.")
    else:
        robots_txt_status = "allowed"

    # 6. Sitemap Inclusion
    if sitemap_res is None or not getattr(sitemap_res, "present", False):
        sitemap_status = "unknown"
    elif getattr(sitemap_res, "target_in_sitemap", False):
        sitemap_status = "included"
    else:
        sitemap_status = "missing"

    # 7. Internal Links
    links_info = html_data.get("links", {})
    internal_count = links_info.get("internal_count", 0)
    if internal_count > 0:
        internal_links_status = "linked"
    else:
        internal_links_status = "orphan candidate"
        if not http_res.get("is_local", False):
            is_ambiguous = True
            reasons.append("No internal outbound links detected; candidate orphan page.")

    # 8. Rendered Content Presence
    csr_info = html_data.get("csr_detection", {})
    words = html_data.get("word_count", 0)
    is_challenge = http_res.get("is_challenge_page", False)
    if http_res.get("is_soft_404", False):
        rendered_content_status = "soft_404"
        is_blocked = True
        reasons.append("Soft 404 error detected: server returns HTTP 200 for missing content.")
    elif csr_info.get("is_csr_shell") and not is_challenge:
        rendered_content_status = "missing"
        is_blocked = True
        reasons.append("Initial HTML payload is an empty CSR shell without rendered text.")
    elif words == 0 and not is_challenge:
        rendered_content_status = "missing"
        is_ambiguous = True
        reasons.append("HTML document contains zero readable text.")
    else:
        rendered_content_status = "present"

    # Determine Verdict
    if is_blocked:
        verdict = VERDICT_BLOCKED
    elif is_ambiguous:
        verdict = VERDICT_AMBIGUOUS
    else:
        verdict = VERDICT_INDEXABLE

    if not reasons:
        reasons.append("All primary indexability signals clear (HTTP 200, self-canonical, allowed in robots, index directive, rendered content).")

    return IndexabilityMatrix(
        target_url=target_url,
        http_status_code=code,
        http_status_label=status_label,
        canonical_status=canonical_status,
        canonical_url=canon_val,
        meta_robots_status=meta_robots_status,
        x_robots_status=x_robots_status,
        robots_txt_status=robots_txt_status,
        sitemap_status=sitemap_status,
        internal_links_status=internal_links_status,
        rendered_content_status=rendered_content_status,
        verdict=verdict,
        reasons=reasons
    )
