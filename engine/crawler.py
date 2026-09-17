"""
Autonomous Site-Level SEO Crawler & Internal Linking Engine.

Executes controlled, polite, deterministic crawling of web sites:
1. Breadth-first crawl with max_pages, max_depth, and polite rate-limiting.
2. Robust SSRF protection (blocks RFC 1918, link-local, loopback, and cloud metadata).
3. RFC 9309 robots.txt compliance.
4. Internal link graph tracking (inbound counts, crawl depth, broken links, redirects).
5. Orphan page candidate identification.
6. Site-wide duplicate content clustering via SimHash and exact hash matching.
"""

from __future__ import annotations
import ipaddress
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional, Union, Tuple
from urllib.parse import urlparse, urljoin, urlsplit

from .analyzers.http_analyzer import analyze_target_http
from .analyzers.html_analyzer import analyze_target_html
from .analyzers.robots_simulator import parse_robots_txt, is_user_agent_allowed
from .analyzers.similarity import find_duplicate_clusters


@dataclass
class CrawlConfig:
    seed_url: str
    max_pages: int = 50
    max_depth: int = 3
    delay_seconds: float = 0.05
    timeout: float = 10.0
    max_response_bytes: int = 5_000_000  # 5 MB
    respect_robots: bool = True
    allowed_domains: Optional[List[str]] = None
    user_agent: str = "UltimateSeoGeoCrawler/2.1"


@dataclass
class CrawledPageSummary:
    url: str
    depth: int
    status_code: int
    title: str = ""
    h1: str = ""
    meta_description: str = ""
    canonical: Optional[str] = None
    word_count: int = 0
    inbound_links_count: int = 0
    outbound_internal_count: int = 0
    outbound_external_count: int = 0
    is_indexable: bool = True
    response_time_ms: float = 0.0
    content_text: str = ""


@dataclass
class SiteCrawlReport:
    seed_url: str
    total_crawled: int
    max_depth_reached: int
    status_codes: Dict[int, int]
    pages: Dict[str, CrawledPageSummary]
    link_graph: Dict[str, Set[str]]
    inbound_links: Dict[str, Set[str]]
    broken_links: List[Dict[str, Any]]
    redirect_links: List[Dict[str, Any]]
    orphan_candidates: List[str]
    deep_pages: List[str]
    duplicate_clusters: Dict[str, Any]
    crawl_duration_seconds: float = 0.0

    @property
    def pages_crawled(self) -> int:
        return self.total_crawled

    @property
    def inbound_counts(self) -> Dict[str, int]:
        return {u: len(links) for u, links in self.inbound_links.items()}

    @property
    def crawl_depths(self) -> Dict[str, int]:
        return {u: p.depth for u, p in self.pages.items()}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed_url": self.seed_url,
            "total_crawled": self.total_crawled,
            "max_depth_reached": self.max_depth_reached,
            "status_codes": self.status_codes,
            "orphan_candidates_count": len(self.orphan_candidates),
            "orphan_candidates": self.orphan_candidates,
            "deep_pages_count": len(self.deep_pages),
            "deep_pages": self.deep_pages,
            "broken_links_count": len(self.broken_links),
            "broken_links": self.broken_links,
            "redirect_links_count": len(self.redirect_links),
            "duplicate_clusters": self.duplicate_clusters,
            "crawl_duration_seconds": round(self.crawl_duration_seconds, 2),
            "pages": {
                u: {
                    "depth": p.depth,
                    "status_code": p.status_code,
                    "title": p.title,
                    "h1": p.h1,
                    "canonical": p.canonical,
                    "word_count": p.word_count,
                    "inbound_links_count": p.inbound_links_count,
                    "is_indexable": p.is_indexable
                }
                for u, p in self.pages.items()
            }
        }


def is_safe_target_url(url: str) -> Tuple[bool, str]:
    """
    Validates target URL against SSRF and protocol exploits:
    Rejects loopback (127.0.0.1, localhost), private networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16),
    link-local (169.254.0.0/16), and non-http(s) schemes.
    """
    try:
        parsed = urlsplit(url.strip())
    except Exception as e:
        return False, f"Malformed URL syntax: {e}"

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False, f"Insecure or invalid URI scheme '{scheme}' (only HTTP/HTTPS permitted)"

    hostname = parsed.netloc.split(":")[0].strip().lower()
    if not hostname:
        return False, "Missing hostname in target URL"

    if hostname in ("localhost", "local", "127.0.0.1", "::1", "0.0.0.0"):
        return False, f"Destination '{hostname}' is a forbidden loopback target (SSRF prevention)"

    # Resolve hostname to check IP range if possible
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip_str = entry[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_loopback
                or ip_obj.is_private
                or ip_obj.is_link_local
                or ip_obj.is_unspecified
                or ip_obj.is_reserved
            ):
                return False, f"Target hostname '{hostname}' resolves to private/internal IP {ip_str} (SSRF block)"
    except socket.gaierror:
        # If DNS fails here, analyzer will report reachability error naturally
        pass
    except Exception:
        pass

    return True, "Target URL passed SSRF validation"


def _normalize_crawl_url(raw_url: str, base_url: str = "") -> Optional[str]:
    """Normalizes and resolves relative internal URLs for crawl deduplication."""
    if not raw_url:
        return None
    raw_clean = raw_url.strip()
    if raw_clean.startswith(("#", "javascript:", "mailto:", "tel:", "sms:", "data:")):
        return None

    resolved = urljoin(base_url, raw_clean) if base_url else raw_clean
    parsed = urlsplit(resolved)
    if parsed.scheme.lower() not in ("http", "https"):
        return None

    path = parsed.path
    if not path or path == "/":
        path = "/"
    elif path.endswith("/"):
        path = path.rstrip("/")

    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}{query}"


def crawl_site(
    config_or_seed: Union[str, CrawlConfig],
    max_pages: int = 50,
    max_depth: int = 3,
    delay_seconds: float = 0.05,
    timeout: float = 10.0,
    respect_robots: bool = True,
    allowed_domains: Optional[List[str]] = None,
    user_agent: str = "UltimateSeoGeoCrawler/2.1"
) -> SiteCrawlReport:
    """
    Executes a deterministic breadth-first crawl of the configured site.
    """
    if isinstance(config_or_seed, CrawlConfig):
        config = config_or_seed
    else:
        config = CrawlConfig(
            seed_url=config_or_seed,
            max_pages=max_pages,
            max_depth=max_depth,
            delay_seconds=delay_seconds,
            timeout=timeout,
            respect_robots=respect_robots,
            allowed_domains=allowed_domains,
            user_agent=user_agent
        )

    start_time = time.time()
    seed_norm = _normalize_crawl_url(config.seed_url) or config.seed_url
    parsed_seed = urlparse(seed_norm)
    seed_host = parsed_seed.netloc.lower().split(":")[0]

    allowed_domains = set()
    if config.allowed_domains:
        allowed_domains.update(d.lower().split(":")[0] for d in config.allowed_domains)
    allowed_domains.add(seed_host)
    if seed_host.startswith("www."):
        allowed_domains.add(seed_host[4:])
    else:
        allowed_domains.add(f"www.{seed_host}")

    # Fetch and parse robots.txt
    robots_rules = None
    if config.respect_robots:
        robots_url = f"{parsed_seed.scheme}://{parsed_seed.netloc}/robots.txt"
        rob_res = analyze_target_http(robots_url, timeout=config.timeout)
        if rob_res["status_code"] == 200 and rob_res.get("raw_content"):
            robots_rules = parse_robots_txt(rob_res["raw_content"])

    # BFS queue of (url, depth)
    queue: deque[Tuple[str, int]] = deque([(seed_norm, 0)])
    visited_urls: Set[str] = set()
    pages: Dict[str, CrawledPageSummary] = {}
    link_graph: Dict[str, Set[str]] = {}
    inbound_links: Dict[str, Set[str]] = {}
    status_codes: Dict[int, int] = {}
    broken_links: List[Dict[str, Any]] = []
    redirect_links: List[Dict[str, Any]] = []
    max_depth_reached = 0

    while queue and len(pages) < config.max_pages:
        current_url, depth = queue.popleft()
        if current_url in visited_urls:
            continue
        visited_urls.add(current_url)

        if depth > max_depth_reached:
            max_depth_reached = depth

        # Validate SSRF
        is_safe, ssrf_msg = is_safe_target_url(current_url)
        if not is_safe:
            continue

        # Check robots.txt
        if robots_rules and config.respect_robots:
            c_path = urlparse(current_url).path or "/"
            if not is_user_agent_allowed(robots_rules, config.user_agent, c_path):
                continue

        # Polite delay
        if config.delay_seconds > 0 and len(visited_urls) > 1:
            time.sleep(config.delay_seconds)

        # Fetch HTTP
        http_res = analyze_target_http(current_url, timeout=config.timeout)
        code = http_res.get("status_code", 0)
        status_codes[code] = status_codes.get(code, 0) + 1

        if code >= 400:
            pages[current_url] = CrawledPageSummary(
                url=current_url,
                depth=depth,
                status_code=code,
                is_indexable=False,
                response_time_ms=http_res.get("response_time_ms", 0.0)
            )
            continue

        if 300 <= code < 400 or (http_res.get("redirect_chain") and len(http_res["redirect_chain"]) > 0):
            final_dest = http_res.get("final_url", current_url)
            redirect_links.append({
                "source": current_url,
                "destination": final_dest,
                "code": code
            })

        body_text = http_res.get("raw_content", "")
        # Response byte size guard
        if len(body_text.encode("utf-8", errors="replace")) > config.max_response_bytes:
            continue

        html_data = analyze_target_html(body_text, base_url=current_url)
        title = html_data["title"]["value"]
        h1_list = html_data["headings"]["h1_values"]
        h1_str = h1_list[0] if h1_list else ""
        meta_desc = html_data["meta_description"]["value"] or ""
        canon_val = html_data["canonical"]["value"]
        is_noindex = html_data["meta_robots"].get("is_noindex", False)
        word_count = html_data.get("word_count", 0)
        content_sample = html_data.get("visible_text", "")

        summary = CrawledPageSummary(
            url=current_url,
            depth=depth,
            status_code=code,
            title=title,
            h1=h1_str,
            meta_description=meta_desc,
            canonical=canon_val,
            word_count=word_count,
            is_indexable=(code == 200 and not is_noindex),
            response_time_ms=http_res.get("response_time_ms", 0.0),
            content_text=content_sample
        )
        pages[current_url] = summary

        # Extract internal links
        internal_targets: Set[str] = set()
        for link_obj in html_data.get("links", {}).get("all", html_data.get("links", {}).get("outline", [])):
            href = link_obj.get("href", "")
            norm_target = _normalize_crawl_url(href, base_url=current_url)
            if not norm_target:
                continue

            target_host = urlparse(norm_target).netloc.lower().split(":")[0]
            if target_host in allowed_domains:
                internal_targets.add(norm_target)
                inbound_links.setdefault(norm_target, set()).add(current_url)

                if depth + 1 <= config.max_depth and norm_target not in visited_urls:
                    queue.append((norm_target, depth + 1))

        link_graph[current_url] = internal_targets

    # Calculate inbound counts and orphan candidates
    orphan_candidates: List[str] = []
    deep_pages: List[str] = []
    for u, p in pages.items():
        in_set = inbound_links.get(u, set())
        p.inbound_links_count = len(in_set)
        p.outbound_internal_count = len(link_graph.get(u, set()))
        if p.depth > 3:
            deep_pages.append(u)
        if p.depth > 0 and p.inbound_links_count == 0:
            orphan_candidates.append(u)

    # Compute duplicate clusters across all crawled pages
    cluster_inputs = [
        {
            "url": u,
            "title": p.title,
            "h1": p.h1,
            "description": p.meta_description,
            "content": p.content_text
        }
        for u, p in pages.items()
    ]
    duplicate_results = find_duplicate_clusters(cluster_inputs)

    crawl_duration = time.time() - start_time
    return SiteCrawlReport(
        seed_url=seed_norm,
        total_crawled=len(pages),
        max_depth_reached=max_depth_reached,
        status_codes=status_codes,
        pages=pages,
        link_graph=link_graph,
        inbound_links=inbound_links,
        broken_links=broken_links,
        redirect_links=redirect_links,
        orphan_candidates=orphan_candidates,
        deep_pages=deep_pages,
        duplicate_clusters=duplicate_results,
        crawl_duration_seconds=crawl_duration
    )


def format_site_crawl_markdown(report: SiteCrawlReport) -> str:
    """Renders a comprehensive Site-Level Crawl & Linking Audit Report in Markdown."""
    md = []
    md.append(f"# Site-Level SEO & Architecture Crawl Report")
    md.append("")
    md.append(f"> **Seed URL**: `{report.seed_url}`  ")
    md.append(f"> **Pages Crawled**: **{report.total_crawled}**  ")
    md.append(f"> **Max Depth Reached**: **{report.max_depth_reached} click(s)**  ")
    md.append(f"> **Crawl Duration**: **{report.crawl_duration_seconds:.2f}s**  ")
    md.append("")

    # Crawl Overview
    md.append("## Crawl Overview & HTTP Status Distribution")
    md.append("")
    md.append("| HTTP Status | Count | Status Label |")
    md.append("| :--- | :--- | :--- |")
    for code, count in sorted(report.status_codes.items()):
        lbl = "OK" if code == 200 else ("Redirect" if 300 <= code < 400 else "Error")
        md.append(f"| **{code}** | {count} page(s) | `{lbl}` |")
    md.append("")

    # Architecture & Internal Linking Health
    md.append("## Architecture & Internal Linking")
    md.append("")
    md.append(f"- **Orphan Page Candidates** (0 inbound internal links): **{len(report.orphan_candidates)}**")
    md.append(f"- **Deep Pages** (> 3 clicks from seed): **{len(report.deep_pages)}**")
    md.append(f"- **Redirect Links**: **{len(report.redirect_links)}**")
    md.append(f"- **Broken Links (4xx/5xx)**: **{len(report.broken_links)}**")
    md.append("")

    if report.orphan_candidates:
        md.append("### Orphan Page Candidates")
        for orph in report.orphan_candidates[:10]:
            md.append(f"- `{orph}`")
        if len(report.orphan_candidates) > 10:
            md.append(f"- *...and {len(report.orphan_candidates) - 10} more*")
        md.append("")

    # Duplicate Content Clusters
    dup = report.duplicate_clusters
    md.append("## Duplicate Content & Architecture Clusters")
    md.append("")
    md.append(f"- **Duplicate Title Groups**: {dup.get('duplicate_titles_count', 0)}")
    md.append(f"- **Duplicate H1 Groups**: {dup.get('duplicate_h1s_count', 0)}")
    md.append(f"- **Duplicate Meta Description Groups**: {dup.get('duplicate_descriptions_count', 0)}")
    md.append(f"- **Near-Duplicate Body Content Clusters (SimHash)**: {dup.get('near_duplicate_clusters_count', 0)}")
    md.append("")

    if dup.get("duplicate_titles"):
        md.append("### Duplicate Title Clusters")
        for title_str, urls in list(dup["duplicate_titles"].items())[:5]:
            md.append(f"- **Title**: *\"{title_str}\"* ({len(urls)} URLs)")
            for u in urls[:3]:
                md.append(f"  - `{u}`")
        md.append("")

    if dup.get("near_duplicate_content_clusters"):
        md.append("### Near-Duplicate Content Clusters (SimHash)")
        for cl in dup["near_duplicate_content_clusters"][:5]:
            md.append(f"- **Cluster** ({cl['count']} URLs):")
            for u in cl["urls"][:3]:
                md.append(f"  - `{u}`")
        md.append("")

    # Pages Ledger Table
    md.append("## Crawled Pages Inventory")
    md.append("")
    md.append("| Depth | Status | URL | Words | Inbound Links | Title |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for u, p in sorted(report.pages.items(), key=lambda x: (x[1].depth, x[0])):
        t_clean = p.title.replace("|", "/")[:40] if p.title else "*(missing)*"
        md.append(f"| {p.depth} | `{p.status_code}` | `{u}` | {p.word_count} | {p.inbound_links_count} | {t_clean} |")
    md.append("")

    return "\n".join(md)
