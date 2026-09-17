"""
XML Sitemap Parser and Structural Validator.
Evaluates sitemap availability, XML syntax, URL absoluteness, domain consistency,
lastmod validity, and canonical page presence.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Set, Dict, Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


@dataclass
class SitemapUrlEntry:
    loc: str
    lastmod: Optional[str] = None
    changefreq: Optional[str] = None
    priority: Optional[str] = None


@dataclass
class SitemapAnalysisResult:
    present: bool
    status_code: int
    url: str
    is_valid_xml: bool
    is_sitemap_index: bool
    total_urls: int = 0
    nested_sitemaps: List[str] = field(default_factory=list)
    urls: List[SitemapUrlEntry] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    target_in_sitemap: bool = False
    duplicate_urls: List[str] = field(default_factory=list)
    invalid_urls: List[str] = field(default_factory=list)
    non_https_urls: List[str] = field(default_factory=list)


def _normalize_url_for_compare(u: str) -> str:
    """Normalizes URL for exact presence checks (preserves path and query strings)."""
    parsed = urlparse(u.strip())
    path = parsed.path
    if not path or path == "/":
        path = "/"
    elif path.endswith("/"):
        path = path.rstrip("/")
    query_part = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}{query_part}"


def parse_sitemap_xml(
    xml_content: str,
    sitemap_url: str = "https://example.com/sitemap.xml",
    target_url: Optional[str] = None,
    base_domain: Optional[str] = None,
    status_code: int = 200
) -> SitemapAnalysisResult:
    """
    Parses XML sitemap string, validating structure, URLs, dates, and target presence.
    Handles both <urlset> and <sitemapindex>.
    """
    res = SitemapAnalysisResult(
        present=bool(xml_content.strip()),
        status_code=status_code,
        url=sitemap_url,
        is_valid_xml=False,
        is_sitemap_index=False,
        total_urls=0
    )

    if not xml_content.strip():
        res.errors.append("Empty sitemap content.")
        return res

    try:
        root = ET.fromstring(xml_content)
        res.is_valid_xml = True
    except Exception as e:
        res.errors.append(f"Invalid XML syntax in sitemap: {e}")
        return res

    root_tag = root.tag.split("}")[-1].lower()
    res.is_sitemap_index = (root_tag == "sitemapindex")

    norm_target = _normalize_url_for_compare(target_url) if target_url else None
    seen_locs: Set[str] = set()

    if res.is_sitemap_index:
        for child in root:
            tag = child.tag.split("}")[-1].lower()
            if tag == "sitemap":
                for sub in child:
                    sub_tag = sub.tag.split("}")[-1].lower()
                    if sub_tag == "loc" and sub.text:
                        loc_val = sub.text.strip()
                        res.nested_sitemaps.append(loc_val)
                        if not loc_val.startswith(("http://", "https://")):
                            res.invalid_urls.append(loc_val)
                            res.errors.append(f"Relative URL in nested sitemap: {loc_val}")
        return res

    # Process standard <urlset>
    current_year = datetime.now(timezone.utc).year

    for child in root:
        tag = child.tag.split("}")[-1].lower()
        if tag != "url":
            continue

        loc_val = None
        lastmod_val = None
        freq_val = None
        prio_val = None

        for sub in child:
            sub_tag = sub.tag.split("}")[-1].lower()
            if sub_tag == "loc" and sub.text:
                loc_val = sub.text.strip()
            elif sub_tag == "lastmod" and sub.text:
                lastmod_val = sub.text.strip()
            elif sub_tag == "changefreq" and sub.text:
                freq_val = sub.text.strip()
            elif sub_tag == "priority" and sub.text:
                prio_val = sub.text.strip()

        if not loc_val:
            res.errors.append("Missing <loc> element in <url> entry.")
            continue

        # Check absoluteness
        if not loc_val.startswith(("http://", "https://")):
            res.invalid_urls.append(loc_val)
            res.errors.append(f"Relative URL found in sitemap: '{loc_val}' (must be absolute).")
        else:
            if loc_val.startswith("http://"):
                res.non_https_urls.append(loc_val)
                res.warnings.append(f"Insecure HTTP URL in sitemap: '{loc_val}'.")

            # Check domain matching
            if base_domain:
                loc_netloc = urlparse(loc_val).netloc.lower()
                base_clean = base_domain.lower()
                if not (loc_netloc == base_clean or loc_netloc.endswith("." + base_clean)):
                    res.warnings.append(f"Cross-domain URL in sitemap: '{loc_val}' does not match '{base_domain}'.")

        # Check duplicate
        if loc_val in seen_locs:
            res.duplicate_urls.append(loc_val)
            res.warnings.append(f"Duplicate URL in sitemap: '{loc_val}'.")
        seen_locs.add(loc_val)

        # Check lastmod format if present
        if lastmod_val:
            parsed_dt = None
            clean_lm = lastmod_val.strip()
            try:
                iso_candidate = clean_lm.replace("Z", "+00:00") if clean_lm.endswith("Z") else clean_lm
                parsed_dt = datetime.fromisoformat(iso_candidate)
            except ValueError:
                for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        parsed_dt = datetime.strptime(clean_lm, fmt)
                        break
                    except ValueError:
                        continue

            if parsed_dt is not None:
                if parsed_dt.year > current_year + 1:
                    res.warnings.append(f"Future lastmod date '{lastmod_val}' for '{loc_val}'.")
            else:
                res.warnings.append(f"Unparseable lastmod date format '{lastmod_val}' for '{loc_val}'.")

        entry = SitemapUrlEntry(loc=loc_val, lastmod=lastmod_val, changefreq=freq_val, priority=prio_val)
        res.urls.append(entry)

        # Check target presence
        if norm_target and _normalize_url_for_compare(loc_val) == norm_target:
            res.target_in_sitemap = True

    res.total_urls = len(res.urls)
    return res


def merge_sitemap_results(parent: SitemapAnalysisResult, children: List[SitemapAnalysisResult]) -> SitemapAnalysisResult:
    """
    Merges child sitemap results into a parent sitemap index analysis result.
    """
    merged = SitemapAnalysisResult(
        present=parent.present,
        status_code=parent.status_code,
        url=parent.url,
        is_valid_xml=parent.is_valid_xml,
        is_sitemap_index=parent.is_sitemap_index,
        total_urls=0,
        nested_sitemaps=list(parent.nested_sitemaps),
        urls=list(parent.urls),
        errors=list(parent.errors),
        warnings=list(parent.warnings),
        target_in_sitemap=parent.target_in_sitemap,
        duplicate_urls=list(parent.duplicate_urls),
        invalid_urls=list(parent.invalid_urls),
        non_https_urls=list(parent.non_https_urls),
    )

    for ch in children:
        merged.urls.extend(ch.urls)
        merged.errors.extend(ch.errors)
        merged.warnings.extend(ch.warnings)
        merged.duplicate_urls.extend(ch.duplicate_urls)
        merged.invalid_urls.extend(ch.invalid_urls)
        merged.non_https_urls.extend(ch.non_https_urls)
        if ch.target_in_sitemap:
            merged.target_in_sitemap = True

    merged.total_urls = len(merged.urls)
    return merged
