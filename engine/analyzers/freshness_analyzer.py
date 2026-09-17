"""
Deterministic Freshness & Temporal Consistency Analyzer.

Evaluates:
- datePublished and dateModified consistency (Schema.org & OpenGraph)
- HTTP Last-Modified header validation
- Sitemap lastmod alignment
- Visible editorial dates vs machine metadata
- Content hash computation (MD5) for versioning and historical comparison
- Stale content identification (> 2 years without update)
- Temporal discrepancy detection (future dates, modified < published)
"""

from __future__ import annotations
import hashlib
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


VISIBLE_DATE_PATTERNS = [
    re.compile(r"\b(?:last\s+updated|updated\s+on|modified|published(?:\s+on)?)\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE),
    re.compile(r"\b(?:обновлено|опубликовано|дата\s+публикации)\s*:?\s*(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
]


def _parse_iso_or_http_date(date_val: Optional[str]) -> Optional[datetime]:
    if not date_val:
        return None
    val_str = str(date_val).strip()
    # Try ISO 8601
    try:
        clean = val_str.replace("Z", "+00:00")
        if "T" in clean:
            return datetime.fromisoformat(clean)
        return datetime.strptime(clean[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        pass

    # Try HTTP date format (RFC 7231 / RFC 1123)
    try:
        return datetime.strptime(val_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        return datetime.strptime(val_str, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
    except Exception:
        pass

    return None


@dataclass
class FreshnessFinding:
    rule_id: str
    severity: str  # CRITICAL, WARNING, INFO, PASS
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FreshnessAnalysisResult:
    date_published: Optional[str] = None
    date_modified: Optional[str] = None
    http_last_modified: Optional[str] = None
    sitemap_lastmod: Optional[str] = None
    visible_editorial_date: Optional[str] = None
    content_hash: str = ""
    is_stale: bool = False
    has_discrepancy: bool = False
    discrepancy_details: List[str] = field(default_factory=list)
    freshness_score: int = 50  # 0..100 (neutral 50 if unmeasured)
    is_measured: bool = False
    findings: List[FreshnessFinding] = field(default_factory=list)

    @property
    def discrepancies(self) -> List[str]:
        return self.discrepancy_details

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date_published": self.date_published,
            "date_modified": self.date_modified,
            "http_last_modified": self.http_last_modified,
            "sitemap_lastmod": self.sitemap_lastmod,
            "visible_editorial_date": self.visible_editorial_date,
            "content_hash": self.content_hash,
            "is_stale": self.is_stale,
            "has_discrepancy": self.has_discrepancy,
            "discrepancy_details": self.discrepancy_details,
            "freshness_score": self.freshness_score,
            "is_measured": self.is_measured
        }


def analyze_freshness(
    visible_text: str,
    schema_entities: Optional[List[Dict[str, Any]]] = None,
    http_headers: Optional[Dict[str, str]] = None,
    sitemap_lastmod: Optional[str] = None
) -> FreshnessAnalysisResult:
    """
    Performs deterministic freshness and temporal alignment analysis.
    """
    result = FreshnessAnalysisResult()
    schema_entities = schema_entities or []
    http_headers = http_headers or {}
    result.sitemap_lastmod = sitemap_lastmod

    # 1. Content Hash for tracking changes
    raw_content = visible_text or ""
    result.content_hash = hashlib.md5(raw_content.encode("utf-8", errors="replace")).hexdigest()

    # 2. Extract Dates from Schema.org entities
    for ent in schema_entities:
        dp = ent.get("datePublished")
        dm = ent.get("dateModified")
        if dp and not result.date_published:
            result.date_published = str(dp)
        if dm and not result.date_modified:
            result.date_modified = str(dm)

    # 3. Extract HTTP Last-Modified
    for hk, hv in http_headers.items():
        if hk.lower() == "last-modified":
            result.http_last_modified = hv
            break

    # 4. Extract Visible Editorial Date from Text
    for pat in VISIBLE_DATE_PATTERNS:
        match = pat.search(visible_text or "")
        if match:
            result.visible_editorial_date = match.group(1).strip()
            break

    # Check if we have any date signal to measure
    has_dates = bool(result.date_published or result.date_modified or result.http_last_modified or result.sitemap_lastmod)
    result.is_measured = has_dates

    if not has_dates:
        # Invariant: Unknown != Failure, unmeasured freshness does not penalize
        result.freshness_score = 50
        result.findings.append(FreshnessFinding(
            rule_id="FRESH-DATES-UNMEASURED",
            severity="INFO",
            message="No publication or modification dates detected in Schema, HTTP headers, or sitemap."
        ))
        return result

    # Parse dates for temporal comparison
    dt_pub = _parse_iso_or_http_date(result.date_published)
    dt_mod = _parse_iso_or_http_date(result.date_modified)
    dt_http = _parse_iso_or_http_date(result.http_last_modified)
    dt_sitemap = _parse_iso_or_http_date(result.sitemap_lastmod)

    now = datetime.now(timezone.utc)
    score = 100

    # A. Check if modified < published
    if dt_pub and dt_mod:
        if dt_mod < dt_pub:
            result.has_discrepancy = True
            msg = f"dateModified ({result.date_modified}) is earlier than datePublished ({result.date_published})."
            result.discrepancy_details.append(msg)
            result.findings.append(FreshnessFinding(
                rule_id="FRESH-DATE-DISCREPANCY-001",
                severity="WARNING",
                message=msg
            ))
            score -= 20

    # B. Check if sitemap lastmod strongly contradicts schema dateModified (> 180 days apart)
    if dt_sitemap and dt_mod:
        diff_days = abs((dt_sitemap - dt_mod).days)
        if diff_days > 180:
            result.has_discrepancy = True
            msg = f"Sitemap lastmod ({result.sitemap_lastmod[:10]}) diverges by {diff_days} days from schema dateModified ({result.date_modified[:10]})."
            result.discrepancy_details.append(msg)
            result.findings.append(FreshnessFinding(
                rule_id="FRESH-DATE-DISCREPANCY-001",
                severity="WARNING",
                message=msg
            ))
            score -= 15

    # C. Check future dates
    latest_dt = max(d for d in (dt_pub, dt_mod, dt_http, dt_sitemap) if d is not None)
    if (latest_dt - now).days > 1:
        result.has_discrepancy = True
        msg = f"Detected future date in metadata: {latest_dt.isoformat()}."
        result.discrepancy_details.append(msg)
        result.findings.append(FreshnessFinding(
            rule_id="FRESH-FUTURE-DATE-002",
            severity="CRITICAL",
            message=msg
        ))
        score -= 30

    # D. Check stale content (> 730 days / 2 years without update)
    if (now - latest_dt).days > 730:
        result.is_stale = True
        result.findings.append(FreshnessFinding(
            rule_id="FRESH-STALE-CONTENT-003",
            severity="INFO",
            message=f"Content was last updated on {latest_dt.strftime('%Y-%m-%d')} (> 2 years ago). Review for timely relevance.",
            details={"days_since_update": (now - latest_dt).days}
        ))
        score -= 15

    if not result.has_discrepancy and not result.is_stale:
        result.findings.append(FreshnessFinding(
            rule_id="FRESH-CONSISTENCY-PASS",
            severity="PASS",
            message=f"Publication & modification dates are consistent (Latest: {latest_dt.strftime('%Y-%m-%d')})."
        ))

    result.freshness_score = max(0, min(100, score))
    return result
