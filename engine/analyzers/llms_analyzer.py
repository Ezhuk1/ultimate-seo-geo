"""
Deterministic /llms.txt Analyzer & Generator.

Implements the Answer.AI / Jeremy Howard /llms.txt specification (2024–2026):
- Probes {origin}/llms.txt and {origin}/llms-full.txt
- Validates structure (H1 project title, blockquote summary, sectioned markdown links)
- Provides generator to compile standard-compliant /llms.txt from crawl data
"""

from __future__ import annotations
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from urllib.parse import urlsplit, urlunsplit
from ..security_utils import is_safe_target_url


@dataclass
class LlmsTxtResult:
    is_present: bool = False
    is_valid: bool = False
    status_code: int = 0
    url: str = ""
    title: str = ""
    summary: str = ""
    sections_count: int = 0
    links_count: int = 0
    validation_errors: List[str] = field(default_factory=list)
    raw_content: str = ""


def check_llms_txt(target_url: str, timeout: float = 5.0) -> LlmsTxtResult:
    """
    Probes {origin}/llms.txt and validates its structural compliance.
    """
    res = LlmsTxtResult()
    if not target_url or not target_url.startswith(("http://", "https://")):
        return res

    parts = urlsplit(target_url)
    origin_llms_url = urlunsplit((parts.scheme, parts.netloc, "/llms.txt", "", ""))
    res.url = origin_llms_url

    if not is_safe_target_url(origin_llms_url):
        res.validation_errors.append("Blocked unsafe target URL (SSRF protection).")
        return res

    try:
        req = urllib.request.Request(
            origin_llms_url,
            headers={"User-Agent": "UltimateSeoGeoEngine/3.2.0 (LLM; +https://github.com/Ezhuk1/ultimate-seo-geo)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res.status_code = resp.getcode()
            c_type = resp.headers.get("content-type", "").lower()
            # If server returns HTML instead of text/markdown, it is likely a soft-404 or SPA catch-all
            if "text/html" in c_type:
                res.is_present = False
                res.validation_errors.append("Server returned text/html instead of text/plain or text/markdown (likely soft-404/SPA).")
                return res

            raw = resp.read().decode("utf-8", errors="replace")
            res.raw_content = raw
            res.is_present = True

    except urllib.error.HTTPError as e:
        res.status_code = e.code
        res.is_present = False
        return res
    except Exception as e:
        res.is_present = False
        res.validation_errors.append(f"Network error probing /llms.txt: {str(e)}")
        return res

    # Structural Validation of /llms.txt per standard
    lines = [line.strip() for line in res.raw_content.splitlines()]
    non_empty = [l for l in lines if l]

    if not non_empty:
        res.validation_errors.append("/llms.txt is empty.")
        return res

    # 1. First heading must be H1 (# Project Title)
    h1_match = re.match(r"^#\s+(.+)$", non_empty[0])
    if h1_match:
        res.title = h1_match.group(1).strip()
    else:
        res.validation_errors.append("First non-empty line must be an H1 title (e.g. '# My Project').")

    # 2. Blockquote summary
    for line in non_empty[1:5]:
        if line.startswith(">"):
            res.summary = line.lstrip("> ").strip()
            break

    if not res.summary:
        res.validation_errors.append("Missing blockquote summary (> ...) after H1 title.")

    # 3. Sections & Links
    link_pattern = re.compile(r"-\s+\[([^\]]+)\]\(([^)]+)\)(?::\s*(.+))?")
    for line in lines:
        if line.startswith("## "):
            res.sections_count += 1
        m = link_pattern.search(line)
        if m:
            res.links_count += 1

    if res.links_count == 0:
        res.validation_errors.append("No markdown documentation links found in /llms.txt.")

    res.is_valid = (len(res.validation_errors) == 0 and bool(res.title) and bool(res.summary))
    return res


def generate_llms_txt(
    title: str,
    summary: str,
    pages: List[Dict[str, str]],
    optional_notes: Optional[str] = None
) -> str:
    """
    Generates a standard-compliant /llms.txt file from site crawl or audit data.
    """
    clean_title = title.strip() or "Website"
    clean_summary = summary.strip() or "Comprehensive web service documentation and resources."

    out = [
        f"# {clean_title}",
        "",
        f"> {clean_summary}",
        ""
    ]

    if optional_notes:
        out.append(f"{optional_notes.strip()}")
        out.append("")

    out.append("## Documentation & Key Pages")
    out.append("")

    for page in pages:
        p_title = page.get("title", "").strip() or "Page"
        p_url = page.get("url", "").strip()
        p_desc = page.get("description", "").strip()
        if p_url:
            desc_part = f": {p_desc}" if p_desc else ""
            out.append(f"- [{p_title}]({p_url}){desc_part}")

    out.append("")
    return "\n".join(out)
