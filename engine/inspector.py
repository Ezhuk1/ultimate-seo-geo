"""
Ultimate SEO/GEO Autonomous Inspection Engine CLI & Runner.

Usage:
  python -m engine.inspector https://example.com
  python -m engine.inspector path/to/page.html --format markdown
  python -m engine.inspector https://example.com --format json --output audit.json
"""

from __future__ import annotations
import sys
import os
import argparse
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List

from .analyzers.http_analyzer import analyze_target_http
from .analyzers.html_analyzer import analyze_target_html
from .analyzers.robots_simulator import parse_robots_txt, simulate_ai_crawlers
from .analyzers.schema_analyzer import analyze_json_ld, validate_schema_snippet
from .analyzers.content_analyzer import analyze_content
from .analyzers.sitemap_analyzer import parse_sitemap_xml, SitemapAnalysisResult
from .ledger import (
    LedgerBuilder,
    EvidenceLedger,
    EXPECTED_BASELINE_SIGNALS,
    CONFIDENCE_VERIFIED,
    CONFIDENCE_HEURISTIC,
    CONFIDENCE_UNVERIFIABLE,
    STATUS_PASS,
    STATUS_WARNING,
    STATUS_CRITICAL,
    STATUS_INFO,
    STATUS_NOT_MEASURED,
)
from .scoring import calculate_scores, ScoreBreakdown


def run_inspection(
    target: str,
    custom_robots_txt: Optional[str] = None,
    custom_sitemap_xml: Optional[str] = None,
    timeout: float = 15.0
) -> tuple[EvidenceLedger, ScoreBreakdown]:
    """
    Executes full deterministic audit on URL or local file and returns ledger + score.
    """
    builder = LedgerBuilder(target_url=target)

    # 1. Fetch / Read Target via HTTP/File Analyzer
    http_res = analyze_target_http(target, timeout=timeout)
    status_code = http_res["status_code"]
    headers = http_res["headers"]
    body_text = http_res["raw_content"]
    response_time_ms = http_res["response_time_ms"]
    robots_content: Optional[str] = custom_robots_txt
    sitemap_content: Optional[str] = custom_sitemap_xml

    if http_res["error"] and status_code == 0:
        builder.set_raw(status_code, headers, body_text, response_time_ms)
        builder.add_signal("http_status_code", "HTTP Status Code", status_code, unit="code")
        builder.add_evidence(
            rule_id="TECH-HTTP-000",
            category="technical",
            title="HTTP Target Reachability",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=http_res["error"],
            expected=200,
            message=f"Failed to fetch target URL: {http_res['error']}"
        )
        builder.add_finding(
            rule_id="TECH-HTTP-000",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Target URL Unreachable",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=["Verify network connectivity, DNS resolution, and target host availability."],
            impact_estimate="Complete loss of crawlability and indexation."
        )
        ledger = builder.build(expected_baseline=EXPECTED_BASELINE_SIGNALS)
        return ledger, calculate_scores(ledger)

    if status_code >= 400:
        builder.set_raw(status_code, headers, body_text, response_time_ms)
        builder.add_signal("http_status_code", "HTTP Status Code", status_code, unit="code")
        builder.add_signal("http_response_time_ms", "Response Time", response_time_ms, unit="ms")
        builder.add_evidence(
            rule_id="TECH-HTTP-STATUS-000",
            category="technical",
            title="HTTP Response Status",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=status_code,
            expected="200 OK",
            message=f"HTTP error status {status_code} returned. Search engines and AI crawlers will not index error documents."
        )
        builder.add_finding(
            rule_id="TECH-HTTP-STATUS-000",
            category="technical",
            severity=STATUS_CRITICAL,
            title=f"HTTP {status_code} Error Response",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=[
                f"Investigate web server routing and logs to resolve HTTP {status_code}.",
                "Ensure target URL returns HTTP 200 OK for search crawlers."
            ],
            impact_estimate="Complete de-indexing and crawling failure across all search and generative engines."
        )
        ledger = builder.build(expected_baseline=EXPECTED_BASELINE_SIGNALS)
        return ledger, calculate_scores(ledger)

    # Attempt to fetch robots.txt if target is remote and not provided
    robots_5xx_detected = False
    if not http_res["is_local"] and not robots_content:
        parsed = urlparse(http_res.get("final_url", target))
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rob_res = analyze_target_http(robots_url, timeout=timeout)
        if rob_res["status_code"] == 200 and rob_res["raw_content"]:
            robots_content = rob_res["raw_content"]
        elif rob_res["status_code"] >= 500:
            robots_5xx_detected = True

    builder.set_raw(status_code, headers, body_text, response_time_ms, robots_content)

    # 2. HTML Inspection
    html_data = analyze_target_html(body_text, base_url=target)

    # 3. Schema Inspection
    schema_data = analyze_json_ld(html_data["json_ld_raw_blocks"])

    # 4. Content & GEO Inspection
    content_text = (
        html_data.get("main_text")
        if html_data.get("main_text") and len(html_data["main_text"].split()) >= 30
        else html_data.get("visible_text", html_data.get("visible_text_preview", ""))
    )
    content_data = analyze_content(
        content_text,
        headings=html_data["headings"].get("outline", [])
    )

    # 5. Robots & Sitemap Inspection
    final_url = http_res.get("final_url", target)
    parsed_target = urlparse(final_url)
    target_path = parsed_target.path or "/"

    robots_sim: Optional[Dict[str, Any]] = None
    sitemap_candidate_urls: List[str] = []
    if robots_content:
        robots_ast = parse_robots_txt(robots_content)
        robots_sim = simulate_ai_crawlers(robots_ast, target_path=target_path)
        if robots_ast.sitemaps:
            sitemap_candidate_urls.extend(robots_ast.sitemaps)

    # Attempt to fetch sitemap if remote and not provided
    sitemap_res: Optional[SitemapAnalysisResult] = None
    if not sitemap_content and not http_res["is_local"]:
        if not sitemap_candidate_urls:
            sitemap_candidate_urls.append(f"{parsed_target.scheme}://{parsed_target.netloc}/sitemap.xml")
        for sm_url in sitemap_candidate_urls[:1]:
            sm_res = analyze_target_http(sm_url, timeout=timeout)
            if sm_res["status_code"] == 200 and sm_res["raw_content"]:
                sitemap_content = sm_res["raw_content"]
                sitemap_res = parse_sitemap_xml(
                    sitemap_content,
                    sitemap_url=sm_url,
                    target_url=final_url,
                    base_domain=parsed_target.netloc,
                    status_code=sm_res["status_code"]
                )
                break
    elif sitemap_content:
        sitemap_res = parse_sitemap_xml(
            sitemap_content,
            sitemap_url="https://example.com/sitemap.xml",
            target_url=final_url,
            base_domain=parsed_target.netloc or "example.com",
            status_code=200
        )

    # 6. Record Signals
    builder.add_signal("http_status_code", "HTTP Status Code", status_code, unit="code")
    builder.add_signal("http_response_time_ms", "Response Time", response_time_ms, unit="ms")
    builder.add_signal("html_title_length", "Title Character Length", html_data["title"]["length"], unit="chars")
    builder.add_signal("html_meta_desc_length", "Meta Description Length", html_data["meta_description"]["length"], unit="chars")
    builder.add_signal("html_h1_count", "H1 Headings Count", html_data["headings"]["h1_count"], unit="count")
    builder.add_signal("html_canonical_present", "Canonical URL Present", html_data["canonical"]["present"])
    builder.add_signal("html_images_total", "Total Images", html_data["images"]["total_count"], unit="count")
    builder.add_signal("html_images_missing_alt", "Images Missing Alt", html_data["images"]["missing_alt"], unit="count")
    builder.add_signal("schema_scripts_count", "JSON-LD Scripts Count", schema_data.total_scripts, unit="count")
    builder.add_signal("schema_entity_count", "Schema Entities Count", len(schema_data.entities), unit="count")
    builder.add_signal("schema_has_unified_graph", "Schema Unified @graph Used", schema_data.has_unified_graph)
    builder.add_signal("content_total_words", "Visible Word Count", content_data.total_words, unit="words")
    builder.add_signal("robots_txt_present", "Robots.txt Present", robots_content is not None)
    if sitemap_res:
        builder.add_signal("sitemap_present", "XML Sitemap Present", sitemap_res.present)
        builder.add_signal("sitemap_total_urls", "Sitemap URL Count", sitemap_res.total_urls, unit="count")
        builder.add_signal("sitemap_target_in_sitemap", "Target URL in Sitemap", sitemap_res.target_in_sitemap)

    # Unmeasured Field Signal (Crucial for Invariant Demonstration)
    builder.add_signal(
        signal_id="cwv_real_user_lcp_p75",
        name="Core Web Vitals Real-User LCP (P75)",
        value=None,
        is_measured=False,
        unit="ms",
        source="CrUX API (Unmeasured - Requires Field Dataset / API key)"
    )

    # 7. Evaluate Rules -> EVIDENCE & FINDINGS

    # TECH-CANONICAL-001
    canonical_val = html_data["canonical"]["value"]
    canonical_count = html_data["canonical"].get("count", 1 if canonical_val else 0)

    if not canonical_val:
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Canonical Link Element",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed="None",
            expected="Self-referencing canonical URL in <link rel='canonical'>",
            message="Missing canonical tag. Recommended to consolidate ranking signals and prevent duplicate content."
        )
        builder.add_finding(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            severity=STATUS_WARNING,
            title="Missing Canonical Tag",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=[
                f"Add `<link rel=\"canonical\" href=\"{target}\" />` to the `<head>` section.",
                "Ensure self-referencing canonical URL uses absolute HTTPS format."
            ],
            impact_estimate="Search engines may index duplicate parameter variants or protocol mirrors separately."
        )
    elif canonical_count > 1:
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Canonical Link Element",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{canonical_count} canonical tags found",
            expected="Exactly 1 canonical tag per document",
            message="Multiple canonical tags detected. Search engines ignore conflicting canonical tags."
        )
        builder.add_finding(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Multiple Canonical Tags Detected",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=["Remove duplicate `<link rel='canonical'>` tags, leaving only one single canonical URL."],
            impact_estimate="Search engines will discard canonical hints and pick an arbitrary URL."
        )
    elif not canonical_val.startswith(("http://", "https://")):
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Canonical Link Element",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=canonical_val,
            expected="Absolute HTTPS URL (e.g. https://example.com/path)",
            message=f"Canonical URL '{canonical_val}' is relative. While RFC 6596 Section 3 permits relative IRIs, absolute HTTPS URLs are strongly recommended by search engines to prevent cross-host ambiguity."
        )
        builder.add_finding(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            severity=STATUS_WARNING,
            title="Relative Canonical URL",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=[f"Change relative canonical '{canonical_val}' to an absolute HTTPS URL."],
            impact_estimate="Relative canonical URLs can lead to crawling ambiguity across domain aliases and protocols."
        )
    elif "#" in canonical_val:
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Canonical Link Element",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=canonical_val,
            expected="Canonical URL without fragment identifiers (#)",
            message="Canonical URL contains a URL fragment (#). Search engines index documents without fragments."
        )
        builder.add_finding(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            severity=STATUS_WARNING,
            title="Canonical URL Contains Fragment",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Remove the fragment identifier (#...) from the canonical URL."],
            impact_estimate="URL fragments in canonicals are ignored by crawlers and can cause normalization failure."
        )
    elif canonical_val.startswith("http://"):
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Canonical Link Element",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=canonical_val,
            expected="Secure HTTPS canonical URL",
            message="Canonical URL specifies insecure HTTP instead of HTTPS."
        )
        builder.add_finding(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            severity=STATUS_WARNING,
            title="Insecure HTTP Canonical URL",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Upgrade canonical link to use https://."],
            impact_estimate="Directs crawlers to an unencrypted version of the document."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Canonical Link Element",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=canonical_val,
            expected="Absolute HTTPS URL",
            message="Canonical tag present and absolute."
        )

    # TECH-TITLE-003
    t_len = html_data["title"]["length"]
    title_text = html_data["title"]["value"]
    if t_len == 0:
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=0,
            expected="30-65 characters",
            message="Page has no <title> tag."
        )
        builder.add_finding(
            rule_id="TECH-TITLE-003",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Missing Title Tag",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=["Add a concise descriptive `<title>` (50-60 chars) with primary entity and brand."],
            impact_estimate="Direct loss of search engine snippet generation and LLM query matching."
        )
    elif t_len < 30 or t_len > 65:
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{t_len} chars ('{title_text}')",
            expected="30-65 characters",
            message=f"Title length ({t_len} chars) is outside optimal 30-65 character display window."
        )
        builder.add_finding(
            rule_id="TECH-TITLE-003",
            category="technical",
            severity=STATUS_WARNING,
            title="Suboptimal Title Length",
            confidence=CONFIDENCE_HEURISTIC,
            action_priority="P2_MEDIUM",
            remediation_steps=[f"Adjust title from {t_len} characters to 50-60 characters."],
            impact_estimate="Risk of SERP pixel truncation or weak entity grounding."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{t_len} chars ('{title_text}')",
            expected="30-65 characters",
            message="Title length is within ideal limits (30-65 chars)."
        )

    # TECH-META-DESC-004
    d_len = html_data["meta_description"]["length"]
    if d_len == 0:
        builder.add_evidence(
            rule_id="TECH-META-DESC-004",
            category="technical",
            title="Meta Description",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=0,
            expected="100-165 characters",
            message="Missing meta description tag."
        )
        builder.add_finding(
            rule_id="TECH-META-DESC-004",
            category="technical",
            severity=STATUS_WARNING,
            title="Missing Meta Description",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Add a `<meta name=\"description\" content=\"...\">` summarizing core value proposition (120-160 chars)."],
            impact_estimate="Search engines will auto-generate snippets from arbitrary on-page text."
        )
    elif d_len < 100 or d_len > 165:
        builder.add_evidence(
            rule_id="TECH-META-DESC-004",
            category="technical",
            title="Meta Description",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{d_len} chars",
            expected="100-165 characters",
            message=f"Meta description length ({d_len} chars) is outside optimal 100-165 window."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-META-DESC-004",
            category="technical",
            title="Meta Description",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{d_len} chars",
            expected="100-165 characters",
            message="Meta description length is optimal (100-165 chars)."
        )

    # TECH-H1-OUTLINE-005
    h1_count = html_data["headings"]["h1_count"]
    if h1_count != 1:
        builder.add_evidence(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            title="H1 Heading Count",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=h1_count,
            expected="Exactly 1 H1 heading",
            message=f"Page has {h1_count} <h1> elements (expected exactly 1 for clear semantic outline)."
        )
        builder.add_finding(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            severity=STATUS_WARNING,
            title="Multiple or Missing H1 Headings",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Refactor headings so that there is strictly one <h1> representing the primary page entity."],
            impact_estimate="Weakens document hierarchical outline for AI section extractors."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            title="H1 Heading Count",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=1,
            expected="Exactly 1 H1 heading",
            message="Single H1 heading present."
        )

    # TECH-CSR-SHELL-008: Client-Side Rendering (CSR) Empty Shell
    csr_info = html_data.get("csr_detection", {})
    builder.add_signal("html_is_csr_shell", "Client-Side Rendering (CSR) Empty Shell Detected", csr_info.get("is_csr_shell", False))
    if csr_info.get("is_csr_shell", False):
        mounts_str = ", ".join(csr_info.get("mount_elements", [])) or "JS bundle container"
        w_count = csr_info.get("visible_word_count", 0)
        builder.add_evidence(
            rule_id="TECH-CSR-SHELL-008",
            category="technical",
            title="Client-Side Rendering (CSR) Empty Shell Invisibility",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"CSR mount [{mounts_str}] with only {w_count} visible word(s)",
            expected="Server-rendered semantic HTML payload",
            message="Empty Client-Side Rendering (CSR) shell detected. Fast AI search crawlers (GPTBot, ClaudeBot, PerplexityBot) do NOT execute client-side JavaScript. This page is completely invisible to AI search engines."
        )
        builder.add_finding(
            rule_id="TECH-CSR-SHELL-008",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Client-Side Rendering (CSR) Empty Shell Invisibility",
            confidence=CONFIDENCE_HEURISTIC,
            action_priority="P0_BLOCKER",
            remediation_steps=[
                "Implement Server-Side Rendering (SSR) via Next.js, Nuxt, Astro, or Remix so that HTML and Schema.org are delivered in the initial HTTP wire response.",
                "Verify crawlability with 'curl -s <URL>' - if main content is missing in the curl response, AI search engines will not index it."
            ],
            impact_estimate="Total invisibility and de-indexing from AI search models (GPTBot, ClaudeBot, PerplexityBot, CCBot)."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-CSR-SHELL-008",
            category="technical",
            title="Client-Side Rendering (CSR) Empty Shell Invisibility",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="Semantic content present in initial HTML payload",
            expected="Server-rendered semantic HTML payload",
            message="Initial HTML payload contains readable semantic content (not an empty CSR shell)."
        )

    # TECH-VIEWPORT-006: Mobile Responsive Viewport
    vp_data = html_data.get("viewport", {})
    builder.add_signal("html_viewport_present", "Viewport Meta Tag Present", vp_data.get("present", False))
    if not vp_data.get("present"):
        builder.add_evidence(
            rule_id="TECH-VIEWPORT-006",
            category="technical",
            title="Mobile Responsive Viewport",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed="None",
            expected="<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            message="Missing responsive viewport meta tag. Impairs mobile indexing and mobile usability scoring."
        )
        builder.add_finding(
            rule_id="TECH-VIEWPORT-006",
            category="technical",
            severity=STATUS_WARNING,
            title="Missing Viewport Meta Tag",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Add `<meta name='viewport' content='width=device-width, initial-scale=1.0'>` inside the `<head>` section."],
            impact_estimate="Prevents search engines from validating mobile responsiveness, degrading mobile rank."
        )
    elif not vp_data.get("has_width_device", True):
        builder.add_evidence(
            rule_id="TECH-VIEWPORT-006",
            category="technical",
            title="Mobile Responsive Viewport",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=vp_data.get("value", ""),
            expected="width=device-width in viewport declaration",
            message="Viewport meta tag missing width=device-width directive."
        )
        builder.add_finding(
            rule_id="TECH-VIEWPORT-006",
            category="technical",
            severity=STATUS_WARNING,
            title="Suboptimal Viewport Configuration",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Update viewport tag to `<meta name='viewport' content='width=device-width, initial-scale=1.0'>`."],
            impact_estimate="Pages may render in desktop scale mode on mobile screens."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-VIEWPORT-006",
            category="technical",
            title="Mobile Responsive Viewport",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=vp_data.get("value", ""),
            expected="width=device-width, initial-scale=1.0",
            message="Responsive viewport tag properly configured."
        )

    # TECH-NOINDEX-009: Indexation Directives (Meta Robots / X-Robots-Tag)
    robots_meta = html_data.get("meta_robots", {})
    x_robots_directives = http_res.get("x_robots_directives", [])
    x_bot_directives = http_res.get("x_robots_bot_directives", {})

    global_noindex = robots_meta.get("is_noindex", False) or ("noindex" in x_robots_directives) or ("none" in x_robots_directives)
    blocked_bots = [bot for bot, dirs in x_bot_directives.items() if any(d in ("noindex", "none") for d in dirs)]

    if global_noindex:
        src = "X-Robots-Tag HTTP header" if ("noindex" in x_robots_directives or "none" in x_robots_directives) else "<meta name='robots' content='noindex'>"
        builder.add_evidence(
            rule_id="TECH-NOINDEX-009",
            category="technical",
            title="Indexation Directives (noindex)",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"noindex detected via {src}",
            expected="Permit indexing on public search landing pages",
            message=f"Page is explicitly blocked from search and generative engine indexation via global noindex directive in {src}."
        )
        builder.add_finding(
            rule_id="TECH-NOINDEX-009",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Page Blocked from Indexation (noindex detected)",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=[
                f"Remove 'noindex' from {src} if this page is intended to be found in search or cited by AI models.",
                "Ensure staging or development noindex configurations are not leaking into production."
            ],
            impact_estimate="Total exclusion from search indexation and AI answer generation."
        )
    elif blocked_bots:
        is_crit = any(b in ("googlebot", "bingbot") for b in blocked_bots)
        builder.add_evidence(
            rule_id="TECH-NOINDEX-009",
            category="technical",
            title="Bot-Scoped Indexation Directives (noindex)",
            status=STATUS_CRITICAL if is_crit else STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"Scoped noindex for {', '.join(blocked_bots)} in X-Robots-Tag",
            expected="Permit indexing for search engines",
            message=f"Targeted crawlers ({', '.join(blocked_bots)}) are blocked from indexing via bot-scoped X-Robots-Tag directive."
        )
        builder.add_finding(
            rule_id="TECH-NOINDEX-009",
            category="technical",
            severity=STATUS_CRITICAL if is_crit else STATUS_WARNING,
            title="Bot-Scoped Noindex Directive Detected",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER" if is_crit else "P1_HIGH",
            remediation_steps=[f"Remove scoped noindex directive for {', '.join(blocked_bots)} from X-Robots-Tag header."],
            impact_estimate=f"Crawlers {', '.join(blocked_bots)} will not index this page."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-NOINDEX-009",
            category="technical",
            title="Indexation Directives (noindex)",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="No noindex directives present",
            expected="Indexable public status",
            message="Document is indexable (no noindex found in meta robots or X-Robots-Tag)."
        )

    # TECH-IMG-ALT-010: Image Accessibility & Alternative Text
    img_data = html_data.get("images", {})
    missing_alt = img_data.get("missing_alt", 0)
    total_imgs = img_data.get("total_count", 0)
    if total_imgs > 0 and missing_alt > 0:
        builder.add_evidence(
            rule_id="TECH-IMG-ALT-010",
            category="technical",
            title="Image Accessibility & Alt Text",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{missing_alt} of {total_imgs} image(s) missing alt attribute",
            expected="All images declare alt attribute (informative text or alt='' for decorative graphics)",
            message=f"{missing_alt} image(s) lack an alt attribute entirely."
        )
        builder.add_finding(
            rule_id="TECH-IMG-ALT-010",
            category="technical",
            severity=STATUS_WARNING,
            title="Images Missing Alt Attribute",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=[
                "Add descriptive `alt='...'` text describing informational images.",
                "Use `alt=''` for purely decorative graphics so screen readers and crawlers can skip them cleanly."
            ],
            impact_estimate="Degrades accessibility compliance and image search ranking."
        )
    elif total_imgs > 0:
        builder.add_evidence(
            rule_id="TECH-IMG-ALT-010",
            category="technical",
            title="Image Accessibility & Alt Text",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"All {total_imgs} images have alt attributes defined",
            expected="All images have alt attribute",
            message="All images have alt attributes defined."
        )

    # TECH-ROBOTS-AI-002: Robots.txt Crawler Access & RFC 9309 Rules
    if robots_5xx_detected:
        builder.add_evidence(
            rule_id="TECH-ROBOTS-AI-002",
            category="technical",
            title="Robots.txt Availability (RFC 9309 5xx Block)",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed="HTTP 5xx error on robots.txt",
            expected="HTTP 200 or 404 for robots.txt",
            message="robots.txt returned a 5xx server error. Per RFC 9309 section 2.3.1.2, search engines treat 5xx errors on robots.txt as a complete crawl block."
        )
        builder.add_finding(
            rule_id="TECH-ROBOTS-AI-002",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Robots.txt 5xx Server Error",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=[
                "Fix web server configuration serving /robots.txt.",
                "Per RFC 9309, all crawling is suspended when robots.txt returns 5xx server errors."
            ],
            impact_estimate="Complete halt of crawling and indexation by search engines and AI bots."
        )
    elif robots_sim:
        blocked_search = [b for b, res in robots_sim.items() if b in ("Googlebot", "Bingbot") and not res.get("target_allowed", res["root_allowed"])]
        blocked_ai_search = [b for b, res in robots_sim.items() if b in ("OAI-SearchBot", "PerplexityBot", "ClaudeBot", "ChatGPT-User") and not res.get("target_allowed", res["root_allowed"])]
        blocked_ai_training = [b for b, res in robots_sim.items() if b in ("GPTBot", "Google-Extended", "Bytespider", "Amazonbot", "CCBot", "Diffbot") and not res.get("target_allowed", res["root_allowed"])]

        if blocked_search:
            builder.add_evidence(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                title="Search Engine Access (Googlebot / Bingbot)",
                status=STATUS_CRITICAL,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Blocked search crawlers on '{target_path}': {', '.join(blocked_search)}",
                expected="Unrestricted crawling for search engines",
                message=f"Primary search engine crawlers ({', '.join(blocked_search)}) are blocked from indexing '{target_path}'."
            )
            builder.add_finding(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                severity=STATUS_CRITICAL,
                title="Search Engine Crawlers Blocked in Robots.txt",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P0_BLOCKER",
                remediation_steps=[f"Allow User-agent: {b} in robots.txt for public routes." for b in blocked_search],
                impact_estimate="Complete loss of organic search visibility and indexing."
            )

        if blocked_ai_search:
            builder.add_evidence(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                title="AI Search Crawler Access",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Blocked AI search engines on '{target_path}': {', '.join(blocked_ai_search)}",
                expected="Permit AI search engine indexers (OAI-SearchBot, PerplexityBot)",
                message=f"AI search engines ({', '.join(blocked_ai_search)}) are blocked from accessing '{target_path}'."
            )
            builder.add_finding(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                severity=STATUS_WARNING,
                title="AI Search Engines Disallowed in Robots.txt",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P1_HIGH",
                remediation_steps=[
                    "Allow User-agent: OAI-SearchBot and PerplexityBot in robots.txt if ChatGPT Search and Perplexity citations are desired.",
                    "Ensure private administrative paths remain protected while allowing public content."
                ],
                impact_estimate="Zero citations in ChatGPT Search, Perplexity, and conversational search answers."
            )

        if blocked_ai_training and not blocked_search and not blocked_ai_search:
            builder.add_evidence(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                title="AI Model Training Crawlers",
                status=STATUS_INFO,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Disallowed AI training bots: {', '.join(blocked_ai_training)}",
                expected="Policy-dependent",
                message=f"Model training scrapers ({', '.join(blocked_ai_training)}) are disallowed. Note: This blocks LLM pre-training corpora ingestion without necessarily blocking live AI search engines."
            )

        if not blocked_search and not blocked_ai_search:
            builder.add_evidence(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                title="Robots.txt AI Crawler Access",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"All major search and retrieval crawlers allowed access to '{target_path}'",
                expected="Allow search crawlers",
                message="Robots.txt permits primary search and AI retrieval engines."
            )
    else:
        builder.add_evidence(
            rule_id="TECH-ROBOTS-AI-002",
            category="technical",
            title="Robots.txt AI Crawler Access",
            status=STATUS_INFO,
            confidence=CONFIDENCE_HEURISTIC,
            observed="No robots.txt detected",
            expected="Accessible robots.txt",
            message="No robots.txt detected (defaults to full allow per RFC 9309)."
        )

    # TECH-SITEMAP-011: XML Sitemap Validation
    if sitemap_res:
        if sitemap_res.errors:
            builder.add_evidence(
                rule_id="TECH-SITEMAP-011",
                category="technical",
                title="XML Sitemap Syntax and Consistency",
                status=STATUS_CRITICAL,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{len(sitemap_res.errors)} error(s): {', '.join(sitemap_res.errors[:2])}",
                expected="Valid XML sitemap with absolute URLs",
                message=f"Sitemap has structural errors: {'; '.join(sitemap_res.errors[:3])}"
            )
            builder.add_finding(
                rule_id="TECH-SITEMAP-011",
                category="technical",
                severity=STATUS_CRITICAL,
                title="XML Sitemap Structural Errors",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P0_BLOCKER",
                remediation_steps=[
                    "Ensure all sitemap URLs are absolute HTTPS URLs matching the target host.",
                    "Fix XML syntax errors to allow search crawlers to parse the sitemap index."
                ],
                impact_estimate="Crawlers cannot discover or verify URLs listed in corrupted sitemap files."
            )
        elif sitemap_res.warnings:
            builder.add_evidence(
                rule_id="TECH-SITEMAP-011",
                category="technical",
                title="XML Sitemap Syntax and Consistency",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{len(sitemap_res.warnings)} warning(s): {', '.join(sitemap_res.warnings[:2])}",
                expected="Clean HTTPS URLs with valid lastmod dates",
                message=f"Sitemap warnings: {'; '.join(sitemap_res.warnings[:3])}"
            )
            builder.add_finding(
                rule_id="TECH-SITEMAP-011",
                category="technical",
                severity=STATUS_WARNING,
                title="XML Sitemap Quality Issues",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=["Remove duplicate or insecure HTTP URLs and fix unparseable lastmod dates."],
                impact_estimate="Suboptimal crawl budget allocation and delayed fresh content discovery."
            )
        else:
            builder.add_evidence(
                rule_id="TECH-SITEMAP-011",
                category="technical",
                title="XML Sitemap Syntax and Consistency",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Valid sitemap with {sitemap_res.total_urls} URLs",
                expected="Valid XML sitemap",
                message="XML sitemap is syntactically valid and properly configured."
            )
    elif not http_res["is_local"]:
        builder.add_evidence(
            rule_id="TECH-SITEMAP-011",
            category="technical",
            title="XML Sitemap Syntax and Consistency",
            status=STATUS_INFO,
            confidence=CONFIDENCE_HEURISTIC,
            observed="No XML sitemap detected",
            expected="Discoverable XML sitemap",
            message="No XML sitemap detected at standard locations or referenced in robots.txt."
        )

    # SCHEMA EVIDENCE
    for sf in schema_data.findings:
        builder.add_evidence(
            rule_id=sf.rule_id,
            category="schema",
            title=f"Schema: {sf.rule_id}",
            status=sf.severity,
            confidence=CONFIDENCE_VERIFIED,
            observed=sf.details,
            expected="Valid Schema.org AST and @graph",
            message=sf.message
        )
        builder.add_finding(
            rule_id=sf.rule_id,
            category="schema",
            severity=sf.severity,
            title=f"Schema Issue: {sf.rule_id}",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER" if sf.severity == STATUS_CRITICAL else "P2_MEDIUM",
            remediation_steps=[sf.message],
            impact_estimate="Rich snippets degradation and failure of Knowledge Graph entity linking."
        )

    has_graph_defect = any(
        sf.rule_id == "SCHEMA-GRAPH-INTERCONNECT-002"
        for sf in schema_data.findings
        if sf.severity in (STATUS_CRITICAL, STATUS_WARNING)
    )
    if not has_graph_defect and schema_data.entities:
        builder.add_evidence(
            rule_id="SCHEMA-GRAPH-INTERCONNECT-002",
            category="schema",
            title="Schema.org Architecture",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{len(schema_data.entities)} entities parsed cleanly",
            expected="Valid interconnected @graph",
            message="Schema entities are structurally sound and verified."
        )

    # CONTENT & GEO EVIDENCE
    for cf in content_data.findings:
        builder.add_evidence(
            rule_id=cf.rule_id,
            category="geo",
            title=f"GEO: {cf.rule_id}",
            status=cf.severity,
            confidence=CONFIDENCE_HEURISTIC,
            observed=cf.details,
            expected="Compliant content architecture for RAG/LLM extraction",
            message=cf.message
        )
        builder.add_finding(
            rule_id=cf.rule_id,
            category="geo",
            severity=cf.severity,
            title=f"GEO Content Issue: {cf.rule_id}",
            confidence=CONFIDENCE_HEURISTIC,
            action_priority="P2_MEDIUM",
            remediation_steps=[cf.message],
            impact_estimate="Reduced citation frequency in LLM synthesis."
        )

    if content_data.opening_has_direct_answer:
        builder.add_evidence(
            rule_id="GEO-ANSWER-FRONTLOAD-001",
            category="geo",
            title="Direct Answer Frontloading",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed=content_data.opening_snippet[:100],
            expected="Direct answer / entity definition in first 60 words",
            message="Content opening successfully frontloads direct answer."
        )

    if content_data.monolithic_chunks_count == 0 and content_data.total_chunks > 0:
        builder.add_evidence(
            rule_id="GEO-ADAPTIVE-CHUNKING-002",
            category="geo",
            title="Adaptive Passage Chunking",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{content_data.total_chunks} chunk(s) all within size limits",
            expected="Passages chunked cleanly with semantic headings",
            message="Content sections are well-proportioned for vector chunking."
        )

    if content_data.pronoun_lead_count <= 2:
        builder.add_evidence(
            rule_id="GEO-COREFERENCE-INDEPENDENCE-003",
            category="geo",
            title="Coreference Independence",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{content_data.pronoun_lead_count} pronoun leads detected",
            expected="Self-contained entity grounding per section",
            message="Passages exhibit strong coreference independence."
        )

    # UNMEASURED FIELD EVIDENCE (Demonstrates strict "Unknown != Failure" invariant)
    builder.add_evidence(
        rule_id="PERF-CWV-FIELD-007",
        category="performance",
        title="Core Web Vitals Real-User Field Metrics (CrUX)",
        status=STATUS_NOT_MEASURED,
        confidence=CONFIDENCE_UNVERIFIABLE,
        observed="No CrUX field API token provided",
        expected="75th percentile LCP < 2.5s, INP < 200ms, CLS < 0.1",
        message="Real-user field performance is NOT MEASURED. In accordance with Evidence Ledger invariants, this unmeasured hypothesis carries 0 penalty."
    )

    ledger = builder.build(expected_baseline=EXPECTED_BASELINE_SIGNALS)
    scores = calculate_scores(ledger)
    return ledger, scores


def format_markdown_report(ledger: EvidenceLedger, scores: ScoreBreakdown) -> str:
    """Renders human-readable, executive-level Markdown audit report."""
    md = []
    md.append(f"# Evidence-Driven SEO & GEO Inspection Report (v{ledger.metadata['engine_version']})")
    md.append("")
    md.append(f"> **Target**: `{ledger.metadata['target']}`  ")
    md.append(f"> **Provenance SHA-256**: `{ledger.metadata['provenance_sha256']}`  ")
    md.append(f"> **Inspection Timestamp**: `{ledger.metadata['generated_at']}`  ")
    md.append("")

    # Scorecard
    md.append("## Executive Scorecard")
    md.append("")
    md.append("| Metric | Score / Tier | Evaluation Basis |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Observable Technical Score** | **{scores.observable_technical_score} / 100** ({scores.technical_health_tier}) | Deterministic pass/fail checks strictly from verified payload |")
    md.append(f"| **GEO Readiness Index** | **{scores.geo_readiness_index} / 100** ({scores.geo_maturity_tier}) | Direct answer frontloading, chunking, coreference, Schema graph |")
    md.append(f"| **Observation Coverage** | **{scores.observation_coverage_pct}%** ({ledger.metadata['signals_measured']}/{ledger.metadata['signals_total']} signals) | Empirical completeness of audit scope |")
    md.append("")

    md.append("> [!NOTE]")
    md.append("> **Evidence Ledger Invariant: 'Unknown != Failure'**  ")
    md.append(f"> Exactly {scores.not_measured_count} unmeasured external signal(s) (e.g., CWV CrUX field data) were detected. In compliance with the Evidence Protocol, unmeasured signals carry 0 penalty and are explicitly segregated from verified defects.")
    md.append("")

    # Deductions
    if scores.deductions:
        md.append("### Score Deductions Breakdown")
        md.append("")
        md.append("| Rule ID | Impact | Confidence | Reason |")
        md.append("| :--- | :--- | :--- | :--- |")
        for d in scores.deductions:
            md.append(f"| `{d['rule_id']}` | **{d['penalty']} pts** | `{d['confidence']}` | {d['reason']} |")
        md.append("")

    # Prioritized Action Plan
    md.append("## Prioritized Remediation Action Plan")
    md.append("")
    if not ledger.findings:
        md.append("**[PASS] All observed checks passed! No critical defects or warnings found.**")
    else:
        for fnd in ledger.findings:
            p_badge = fnd.action_priority
            md.append(f"### `[{p_badge}]` {fnd.title} (`{fnd.rule_id}`)")
            md.append(f"- **Severity**: `{fnd.severity}` | **Confidence**: `{fnd.confidence}` | **Category**: `{fnd.category}`")
            md.append(f"- **Impact**: {fnd.impact_estimate}")
            md.append("- **Remediation Steps**:")
            for step in fnd.remediation_steps:
                md.append(f"  1. {step}")
            md.append("")

    # Full Evidence Ledger Table
    md.append("## Complete Evidence Ledger")
    md.append("")
    md.append("| Category | Rule ID | Status | Confidence | Observed Value | Expected Contract |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for ev in ledger.evidence:
        status_badge = (
            "[CRITICAL]" if ev.status == STATUS_CRITICAL
            else ("[WARNING]" if ev.status == STATUS_WARNING
            else ("[PASS]" if ev.status == STATUS_PASS
            else ("[NOT_MEASURED]" if ev.status == STATUS_NOT_MEASURED else "[INFO]")))
        )
        obs_str = str(ev.observed).replace("\n", " ")[:60]
        exp_str = str(ev.expected).replace("\n", " ")[:60]
        md.append(f"| `{ev.category}` | `{ev.rule_id}` | `{status_badge}` | `{ev.confidence}` | {obs_str} | {exp_str} |")
    md.append("")

    return "\n".join(md)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Ultimate SEO & GEO Autonomous Inspection Engine v2.1.0")
    parser.add_argument("target", nargs="?", default=None, help="Target URL (https://...) or local HTML file path")
    parser.add_argument("--validate-schema", nargs="?", const="stdin", default=None, help="Validate standalone Schema.org JSON-LD snippet (file path, raw JSON string, or stdin)")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format (markdown or json)")
    parser.add_argument("--output", help="Optional output file path to write results")
    parser.add_argument("--robots", help="Optional custom robots.txt file or URL")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP request timeout in seconds")

    args = parser.parse_args()

    # Standalone Schema Validation Mode
    if args.validate_schema:
        schema_input = args.validate_schema
        if schema_input in ("stdin", "-"):
            schema_input = sys.stdin.read()
        elif os.path.exists(schema_input):
            with open(schema_input, "r", encoding="utf-8", errors="replace") as f:
                schema_input = f.read()

        is_valid, errors, result = validate_schema_snippet(schema_input)
        if is_valid:
            print(f"[PASS] Schema.org JSON-LD is 100% valid! Parsed {len(result.entities)} entity/entities in unified @graph; price formats, ISO dates, and @id references verified.")
            sys.exit(0)
        else:
            print(f"[FAIL] Schema.org JSON-LD validation failed ({len(errors)} issue(s)):")
            for err in errors:
                print(f"  - {err}")
            sys.exit(1)

    if not args.target:
        parser.error("the following arguments are required: target (or use --validate-schema)")

    custom_robots = None
    if args.robots:
        if os.path.exists(args.robots):
            with open(args.robots, "r", encoding="utf-8", errors="replace") as f:
                custom_robots = f.read()
        else:
            custom_robots = args.robots

    try:
        ledger, scores = run_inspection(args.target, custom_robots_txt=custom_robots, timeout=args.timeout)
    except Exception as exc:
        sys.stderr.write(f"Error executing inspection: {exc}\n")
        sys.exit(1)

    if args.format == "json":
        res_dict = ledger.to_dict()
        res_dict["scores"] = scores.__dict__
        import json
        output_str = json.dumps(res_dict, indent=2, default=str)
    else:
        output_str = format_markdown_report(ledger, scores)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Inspection report saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
