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
from .analyzers.eeat_analyzer import analyze_eeat
from .analyzers.freshness_analyzer import analyze_freshness
from .analyzers.security_analyzer import SecurityAnalyzer
from .sarif import format_sarif_json, generate_sarif_report
from .indexability import evaluate_indexability_matrix, VERDICT_CONFLICTED
from .config import EngineConfig
from .experiment import compare_experiments, render_experiment_markdown
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
    STATUS_UNKNOWN,
    STATUS_NOT_APPLICABLE,
    STATUS_NOT_MEASURED,
)
from .scoring import calculate_scores, ScoreBreakdown


def run_inspection(
    target: str,
    custom_robots_txt: Optional[str] = None,
    custom_sitemap_xml: Optional[str] = None,
    timeout: float = 15.0,
    user_agent: Optional[str] = None,
    rendered_html: Optional[str] = None
) -> tuple[EvidenceLedger, ScoreBreakdown]:
    """
    Executes full deterministic audit on URL or local file and returns ledger + score.
    """
    builder = LedgerBuilder(target_url=target)

    # 1. Fetch / Read Target via HTTP/File Analyzer
    http_res = analyze_target_http(target, timeout=timeout, user_agent=user_agent)
    status_code = http_res["status_code"]
    headers = http_res["headers"]
    body_text = http_res["raw_content"]
    response_time_ms = http_res["response_time_ms"]
    robots_content: Optional[str] = custom_robots_txt
    sitemap_content: Optional[str] = custom_sitemap_xml

    if rendered_html:
        if os.path.exists(rendered_html):
            try:
                with open(rendered_html, "r", encoding="utf-8", errors="replace") as rh_f:
                    body_text = rh_f.read()
            except Exception:
                pass
        else:
            body_text = rendered_html

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

    # Prompt injection check on raw web content (OWASP LLM01 Defense)
    sec_findings = SecurityAnalyzer.analyze(body_text)
    if sec_findings:
        for sf in sec_findings:
            builder.add_evidence(
                rule_id="SEC-PROMPT-INJECTION-001",
                category="security",
                title="Web Content Prompt Injection Defense",
                status=STATUS_CRITICAL,
                confidence=CONFIDENCE_VERIFIED,
                observed=sf.snippet,
                expected="Web page content must not contain adversarial prompt injections or system delimiters",
                message=f"Adversarial prompt injection pattern ({sf.pattern_type}) detected in {sf.location}: {sf.snippet}",
                evidence_snippet=sf.snippet,
                tier="Tier D (Industry Security Standard)"
            )
            builder.add_finding(
                rule_id="SEC-PROMPT-INJECTION-001",
                category="security",
                severity=STATUS_CRITICAL,
                title="Prompt Injection Attack Detected in Web Content",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P0_BLOCKER",
                remediation_steps=[
                    "Isolate untrusted page content. Do not pass untrusted markup directly into LLM system prompts.",
                    f"Remove adversarial directive from {sf.location}: '{sf.snippet}'"
                ],
                impact_estimate="Critical risk of LLM prompt manipulation, jailbreak, or forced rating falsification.",
                tier="Tier D (Industry Security Standard)"
            )

    # 2. HTML Inspection
    html_data = analyze_target_html(body_text, base_url=target)

    # 3. Schema Inspection
    schema_data = analyze_json_ld(html_data["json_ld_raw_blocks"])

    # 4. Content & GEO Inspection (Sanitized from Adversarial Payloads)
    content_text = (
        html_data.get("main_text")
        if html_data.get("main_text") and len(html_data["main_text"].split()) >= 30
        else html_data.get("visible_text", html_data.get("visible_text_preview", ""))
    )
    content_text = SecurityAnalyzer.sanitize_for_llm(content_text)
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

    # Expand sitemap index children if present
    if sitemap_res and sitemap_res.is_sitemap_index and sitemap_res.nested_sitemaps and not http_res["is_local"]:
        child_results = []
        for child_sm_url in sitemap_res.nested_sitemaps[:5]:
            c_res = analyze_target_http(child_sm_url, timeout=timeout)
            if c_res["status_code"] == 200 and c_res["raw_content"]:
                c_parsed = parse_sitemap_xml(
                    c_res["raw_content"],
                    sitemap_url=child_sm_url,
                    target_url=final_url,
                    base_domain=parsed_target.netloc,
                    status_code=c_res["status_code"]
                )
                child_results.append(c_parsed)
            sitemap_res = merge_sitemap_results(sitemap_res, child_results)

    # 6. E-E-A-T and Freshness Analysis
    eeat_data = analyze_eeat(
        content_text,
        schema_entities=schema_data.entities,
        links=html_data.get("links", {}).get("all", [])
    )

    freshness_data = analyze_freshness(
        content_text,
        schema_entities=schema_data.entities,
        http_headers=http_res.get("headers", {}),
        sitemap_lastmod=sitemap_res.target_lastmod if sitemap_res else None
    )

    # 7. Record Signals
    builder.add_signal("http_status_code", "HTTP Status Code", status_code, unit="code")
    builder.add_signal("http_response_time_ms", "Response Time", response_time_ms, unit="ms")
    builder.add_signal("html_title_length", "Title Character Length", html_data["title"]["length"], unit="chars")
    builder.add_signal("html_title_count", "Title Tags Count", html_data["title"].get("count", 1 if html_data["title"]["present"] else 0), unit="count")
    builder.add_signal("html_meta_desc_length", "Meta Description Length", html_data["meta_description"]["length"], unit="chars")
    builder.add_signal("html_desc_count", "Meta Description Tags Count", html_data["meta_description"].get("count", 1 if html_data["meta_description"]["present"] else 0), unit="count")
    builder.add_signal("html_h1_count", "H1 Headings Count", html_data["headings"]["h1_count"], unit="count")
    builder.add_signal("html_canonical_present", "Canonical URL Present", html_data["canonical"]["present"])
    builder.add_signal("html_lang", "HTML Document Language", html_data.get("lang"))
    builder.add_signal("html_meta_charset", "Meta Charset Declaration", html_data.get("meta_charset") or http_res.get("detected_charset"))
    builder.add_signal("http_header_canonical", "Header Link Canonical", http_res.get("header_canonical"))
    builder.add_signal("http_redirect_hops", "Redirect Hops", len(http_res.get("redirect_chain", [])), unit="hops")
    builder.add_signal("html_images_total", "Total Images", html_data["images"]["total_count"], unit="count")
    builder.add_signal("html_images_missing_alt", "Images Missing Alt", html_data["images"]["missing_alt"], unit="count")
    builder.add_signal("schema_scripts_count", "JSON-LD Scripts Count", schema_data.total_scripts, unit="count")
    builder.add_signal("schema_entity_count", "Schema Entities Count", len(schema_data.entities), unit="count")
    builder.add_signal("schema_has_unified_graph", "Schema Unified @graph Used", schema_data.has_unified_graph)
    builder.add_signal("content_total_words", "Visible Word Count", content_data.total_words, unit="words")
    builder.add_signal("content_search_intent", "Search Intent", content_data.search_intent)
    builder.add_signal("content_evidence_density_score", "Evidence Density Score", content_data.evidence_density_score, unit="pts")
    builder.add_signal("content_fluff_count", "Fluff Superlatives Count", content_data.fluff_count, unit="count")
    builder.add_signal("eeat_score", "E-E-A-T Trust Score", eeat_data.eeat_score, unit="pts")
    builder.add_signal("freshness_score", "Freshness Score", freshness_data.freshness_score, unit="pts", is_measured=freshness_data.is_measured)
    builder.add_signal("robots_txt_present", "Robots.txt Present", robots_content is not None)

    builder.metadata["eeat_analysis"] = eeat_data.to_dict()
    builder.metadata["freshness_analysis"] = freshness_data.to_dict()
    builder.metadata["schema_verdict"] = {
        "syntax_valid": schema_data.syntax_valid,
        "schema_org_structure": schema_data.schema_org_structure,
        "google_rich_result_eligibility": schema_data.google_rich_result_eligibility,
        "visible_content_consistency": schema_data.visible_content_consistency
    }
    if sitemap_res:
        builder.add_signal("sitemap_present", "XML Sitemap Present", sitemap_res.present)
        builder.add_signal("sitemap_total_urls", "Sitemap URL Count", sitemap_res.total_urls, unit="count")
        builder.add_signal("sitemap_target_in_sitemap", "Target URL in Sitemap", sitemap_res.target_in_sitemap)

    # Week 2 Signals
    builder.add_signal("target_is_https", "Target Protocol HTTPS", final_url.lower().startswith("https://"))
    builder.add_signal("http_hsts_present", "HSTS Header Present", bool(headers.get("strict-transport-security")))
    builder.add_signal("html_insecure_resources_count", "Mixed Insecure Content Count", html_data.get("mixed_content", {}).get("insecure_count", 0), unit="count")
    sec_hdrs_count = sum(1 for h in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy") if h in headers)
    builder.add_signal("http_security_headers_count", "Security Headers Count", sec_hdrs_count, unit="count")
    builder.add_signal("http_cache_control", "Cache-Control Header", headers.get("cache-control"))
    builder.add_signal("http_content_encoding", "Content-Encoding", headers.get("content-encoding"))
    builder.add_signal("html_landmarks_has_main", "HTML5 <main> Landmark Present", html_data.get("landmarks", {}).get("has_main", False))
    builder.add_signal("html_empty_headings_count", "Empty Headings Count", html_data.get("headings", {}).get("empty_count", 0), unit="count")
    builder.add_signal("html_heading_jumps_count", "Heading Hierarchy Jumps Count", html_data.get("headings", {}).get("hierarchy_jumps_count", 0), unit="count")
    builder.add_signal("html_empty_anchors_count", "Empty Links Count", html_data.get("links", {}).get("empty_anchors_count", 0), unit="count")
    builder.add_signal("html_unlabelled_inputs_count", "Unlabelled Form Inputs Count", html_data.get("forms", {}).get("unlabelled_count", 0), unit="count")
    builder.add_signal("http_is_soft_404", "Soft 404 Error Detected", http_res.get("is_soft_404", False))

    # Evaluate 8-Vector Indexability Matrix
    idx_matrix = evaluate_indexability_matrix(
        target_url=final_url,
        http_res=http_res,
        html_data=html_data,
        robots_simulation=robots_sim,
        sitemap_res=sitemap_res
    )
    builder.metadata["indexability_matrix"] = idx_matrix.to_dict()
    builder.metadata["indexability_verdict"] = idx_matrix.verdict

    # TECH-CONFLICTED-INDEX-031: Contradictory indexing signals
    if idx_matrix.verdict == VERDICT_CONFLICTED:
        conf_details = " | ".join(idx_matrix.conflicting_signals)
        builder.add_evidence(
            rule_id="TECH-CONFLICTED-INDEX-031",
            category="technical",
            title="Indexability Signal Conflict",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=conf_details,
            expected="Consistent and uncontradicted crawl/index directives",
            message=f"Contradictory indexability directives detected: {conf_details}",
            tier="Tier A (Protocol / Standard)"
        )
        builder.add_finding(
            rule_id="TECH-CONFLICTED-INDEX-031",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Contradictory Indexability Signals",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=[
                "Resolve contradictory instructions across sitemap, robots.txt, canonical, and meta tags.",
                *[f"Fix conflict: {c}" for c in idx_matrix.conflicting_signals]
            ],
            impact_estimate="Search engines and AI scrapers receive opposing instructions, leading to arbitrary indexing drops or canonical confusion.",
            tier="Tier A (Protocol / Standard)"
        )

    # 7. Evaluate Rules -> EVIDENCE & FINDINGS

    # TECH-CANONICAL-001
    html_can = html_data["canonical"]["value"]
    header_can = http_res.get("header_canonical")
    canonical_val = html_can or header_can
    canonical_count = html_data["canonical"].get("count", 1 if html_can else 0)

    # Check for conflict between HTTP Header and HTML canonical
    if header_can and html_can and header_can.rstrip("/") != html_can.rstrip("/"):
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Conflicting Canonical URLs",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"Header: {header_can} vs HTML: {html_can}",
            expected="Consistent canonical URL across HTTP Header and HTML",
            message=f"Conflicting canonical declarations: HTTP Link header specifies '{header_can}' while HTML specifies '{html_can}'."
        )
        builder.add_finding(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Conflicting Canonical URLs (Header vs HTML)",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=["Align HTTP Link header and HTML <link rel='canonical'> to specify the exact same canonical URL."],
            impact_estimate="Search engines will discard canonical hints due to direct contradiction."
        )
    elif html_data["canonical"].get("in_body", False):
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Canonical Tag Placement",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed="<link rel='canonical'> located in <body>",
            expected="<link rel='canonical'> located strictly inside <head>",
            message="Canonical link tag is located inside <body>. Search engines strictly require canonical tags inside <head> and ignore body tags."
        )
        builder.add_finding(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            severity=STATUS_WARNING,
            title="Canonical Tag Located Outside <head>",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Move <link rel='canonical'> into the document <head> section."],
            impact_estimate="Search engines may ignore canonical declarations outside of <head>."
        )
    elif not canonical_val:
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

    # TECH-CANONICAL-TRAILING-019 & TECH-CANONICAL-WWW-020
    if canonical_val and canonical_val.startswith(("http://", "https://")):
        parsed_can = urlparse(canonical_val)
        can_path = parsed_can.path or "/"
        tgt_path = parsed_target.path or "/"
        if parsed_can.netloc.lower() == parsed_target.netloc.lower() and can_path.rstrip("/") == tgt_path.rstrip("/"):
            if (can_path.endswith("/") and not tgt_path.endswith("/")) or (not can_path.endswith("/") and tgt_path.endswith("/")):
                builder.add_evidence(
                    rule_id="TECH-CANONICAL-TRAILING-019",
                    category="technical",
                    title="Canonical Trailing Slash Consistency",
                    status=STATUS_WARNING,
                    confidence=CONFIDENCE_VERIFIED,
                    observed=f"Requested '{tgt_path}' vs Canonical '{can_path}'",
                    expected="Matching trailing slash convention",
                    message=f"Canonical URL trailing slash mismatch: requested '{tgt_path}' differs from canonical '{can_path}'."
                )
                builder.add_finding(
                    rule_id="TECH-CANONICAL-TRAILING-019",
                    category="technical",
                    severity=STATUS_WARNING,
                    title="Canonical Trailing Slash Mismatch",
                    confidence=CONFIDENCE_VERIFIED,
                    action_priority="P2_MEDIUM",
                    remediation_steps=["Align trailing slash in canonical link with server URL routing policy."],
                    impact_estimate="Causes redundant redirect loops and split indexation signals."
                )
            else:
                builder.add_evidence(
                    rule_id="TECH-CANONICAL-TRAILING-019",
                    category="technical",
                    title="Canonical Trailing Slash Consistency",
                    status=STATUS_PASS,
                    confidence=CONFIDENCE_VERIFIED,
                    observed="Consistent trailing slash",
                    expected="Consistent trailing slash",
                    message="Canonical URL trailing slash matches requested path."
                )
        can_host = parsed_can.netloc.lower().split(":")[0]
        tgt_host = parsed_target.netloc.lower().split(":")[0]
        if can_host and tgt_host:
            if can_host != tgt_host and can_host.replace("www.", "") == tgt_host.replace("www.", ""):
                builder.add_evidence(
                    rule_id="TECH-CANONICAL-WWW-020",
                    category="technical",
                    title="Canonical Host & Subdomain Consistency",
                    status=STATUS_WARNING,
                    confidence=CONFIDENCE_VERIFIED,
                    observed=f"Requested '{tgt_host}' vs Canonical '{can_host}'",
                    expected="Matching canonical host (www vs non-www)",
                    message=f"Canonical hostname mismatch: requested host '{tgt_host}' differs from canonical host '{can_host}'."
                )
                builder.add_finding(
                    rule_id="TECH-CANONICAL-WWW-020",
                    category="technical",
                    severity=STATUS_WARNING,
                    title="Canonical Host WWW/Non-WWW Mismatch",
                    confidence=CONFIDENCE_VERIFIED,
                    action_priority="P1_HIGH",
                    remediation_steps=["Standardize canonical URL domain to match the canonical host (www vs non-www)."],
                    impact_estimate="Splits search index authority between www and naked domain variants."
                )
            elif can_host == tgt_host:
                builder.add_evidence(
                    rule_id="TECH-CANONICAL-WWW-020",
                    category="technical",
                    title="Canonical Host & Subdomain Consistency",
                    status=STATUS_PASS,
                    confidence=CONFIDENCE_VERIFIED,
                    observed=can_host,
                    expected=tgt_host,
                    message="Canonical host matches requested domain."
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
    if h1_count == 0:
        builder.add_evidence(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            title="H1 Heading Count",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=0,
            expected="Exactly 1 H1 heading",
            message="Page has 0 <h1> elements (missing primary topic heading)."
        )
        builder.add_finding(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            severity=STATUS_WARNING,
            title="Missing Primary H1 Heading",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Add a single <h1> heading representing the primary page topic."],
            impact_estimate="Weakens document hierarchical outline for AI section extractors and search engines."
        )
    elif h1_count > 1:
        builder.add_evidence(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            title="H1 Heading Count",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed=h1_count,
            expected="1 H1 heading recommended",
            message=f"Page has {h1_count} <h1> elements. While modern HTML permits multiple H1 elements, a single primary H1 is recommended for optimal outline structure."
        )
        builder.add_finding(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            severity=STATUS_INFO,
            title="Multiple H1 Headings Detected",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P3_LOW",
            remediation_steps=["Consider consolidating headings so that there is strictly one primary <h1>, converting secondary sections to <h2>."],
            impact_estimate="Minor semantic ambiguity; does not directly block indexation."
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
    is_challenge = http_res.get("is_challenge_page", False)
    builder.add_signal("html_is_csr_shell", "Client-Side Rendering (CSR) Empty Shell Detected", csr_info.get("is_csr_shell", False) and not is_challenge)
    if is_challenge:
        builder.add_evidence(
            rule_id="TECH-CSR-SHELL-008",
            category="technical",
            title="Client-Side Rendering (CSR) Empty Shell Invisibility",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="WAF / Cloudflare challenge page intercepted crawl",
            expected="Direct server HTML response",
            message="Inspection encountered a Cloudflare / WAF verification challenge. CSR shell detection skipped."
        )
    elif csr_info.get("is_csr_shell", False):
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
    else:
        builder.add_evidence(
            rule_id="TECH-IMG-ALT-010",
            category="technical",
            title="Image Accessibility & Alt Text",
            status=STATUS_NOT_APPLICABLE,
            confidence=CONFIDENCE_VERIFIED,
            observed="0 images present on page",
            expected="N/A",
            message="No images present on page; image alt text requirement is not applicable."
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

        if not sitemap_res.target_in_sitemap and sitemap_res.total_urls > 0 and not sitemap_res.is_sitemap_index and not http_res["is_local"]:
            builder.add_evidence(
                rule_id="TECH-SITEMAP-011",
                category="technical",
                title="Target URL Inclusion in XML Sitemap",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Target URL '{final_url}' not found in sitemap",
                expected="Target URL included in sitemap.xml",
                message=f"Current target URL '{final_url}' was not found in the XML sitemap ({sitemap_res.total_urls} URLs indexed)."
            )
            builder.add_finding(
                rule_id="TECH-SITEMAP-011",
                category="technical",
                severity=STATUS_WARNING,
                title="Target URL Missing from XML Sitemap",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=[f"Add '{final_url}' to sitemap.xml with updated <lastmod> date."],
                impact_estimate="Search engines may not prioritize crawling or refreshing this unlisted document."
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

    # TECH-LANG-012: HTML Document Language
    html_lang = html_data.get("lang")
    if not html_lang:
        builder.add_evidence(
            rule_id="TECH-LANG-012",
            category="technical",
            title="HTML Language Declaration",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed="None",
            expected="<html lang='...'> attribute",
            message="<html> tag is missing the 'lang' attribute. Search engines and screen readers use this attribute for localization and speech synthesis."
        )
        builder.add_finding(
            rule_id="TECH-LANG-012",
            category="technical",
            severity=STATUS_WARNING,
            title="Missing HTML lang Attribute",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Add a valid lang attribute to the <html> tag (e.g., <html lang='en'> or <html lang='ru'>)."],
            impact_estimate="Impairs language identification, regional targeting, and accessibility tools."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-LANG-012",
            category="technical",
            title="HTML Language Declaration",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"lang='{html_lang}'",
            expected="<html lang='...'> attribute",
            message=f"HTML document declares language: '{html_lang}'."
        )

    # TECH-CHARSET-013: Character Encoding Declaration
    meta_charset = html_data.get("meta_charset") or http_res.get("detected_charset")
    if not meta_charset:
        builder.add_evidence(
            rule_id="TECH-CHARSET-013",
            category="technical",
            title="Character Encoding Declaration",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed="None",
            expected="<meta charset='utf-8'> or HTTP Content-Type charset",
            message="Document lacks an explicit character encoding declaration. May cause mojibake in search snippets."
        )
        builder.add_finding(
            rule_id="TECH-CHARSET-013",
            category="technical",
            severity=STATUS_WARNING,
            title="Missing Character Encoding Declaration",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Add `<meta charset='utf-8'>` as the first tag inside `<head>`."],
            impact_estimate="Risk of text garbling (mojibake) in search snippets and LLM extraction."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-CHARSET-013",
            category="technical",
            title="Character Encoding Declaration",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=meta_charset,
            expected="Explicit charset declaration (e.g. utf-8)",
            message=f"Character encoding declared: {meta_charset}."
        )

    # TECH-TITLE-DUP-014: Single Title Tag Contract
    title_count = html_data["title"].get("count", 1 if html_data["title"]["present"] else 0)
    if title_count > 1:
        builder.add_evidence(
            rule_id="TECH-TITLE-DUP-014",
            category="technical",
            title="Single Title Tag Contract",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{title_count} <title> tags detected",
            expected="Exactly 1 <title> tag",
            message=f"Document contains {title_count} separate <title> tags. Browsers and crawlers exhibit non-deterministic snippet behavior when multiple titles exist."
        )
        builder.add_finding(
            rule_id="TECH-TITLE-DUP-014",
            category="technical",
            severity=STATUS_WARNING,
            title="Duplicate Title Tags Detected",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=["Consolidate multiple <title> tags into a single authoritative title tag in <head>."],
            impact_estimate="Search engines select an unpredictable title variant for search results."
        )
    elif title_count == 1:
        builder.add_evidence(
            rule_id="TECH-TITLE-DUP-014",
            category="technical",
            title="Single Title Tag Contract",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="Single title tag",
            expected="Exactly 1 <title> tag",
            message="Single title tag present in document."
        )

    # TECH-DESC-DUP-015: Single Meta Description Contract
    desc_count = html_data["meta_description"].get("count", 1 if html_data["meta_description"]["present"] else 0)
    if desc_count > 1:
        builder.add_evidence(
            rule_id="TECH-DESC-DUP-015",
            category="technical",
            title="Single Meta Description Contract",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{desc_count} meta description tags detected",
            expected="At most 1 meta description tag",
            message=f"Document contains {desc_count} duplicate meta description tags."
        )
        builder.add_finding(
            rule_id="TECH-DESC-DUP-015",
            category="technical",
            severity=STATUS_WARNING,
            title="Duplicate Meta Description Tags Detected",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Remove extra meta description tags, keeping only one concise description."],
            impact_estimate="Search engines may ignore contradictory description tags."
        )
    elif desc_count == 1:
        builder.add_evidence(
            rule_id="TECH-DESC-DUP-015",
            category="technical",
            title="Single Meta Description Contract",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="Single meta description tag",
            expected="At most 1 meta description tag",
            message="Single meta description tag configured."
        )

    # PERF-TTFB-016: Server Response Time (TTFB)
    if not http_res["is_local"] and response_time_ms > 0:
        if response_time_ms > 1500.0:
            builder.add_evidence(
                rule_id="PERF-TTFB-016",
                category="performance",
                title="Time to First Byte (TTFB)",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{response_time_ms} ms",
                expected="TTFB <= 1500 ms",
                message=f"Server response time ({response_time_ms} ms) exceeds recommended 1500 ms threshold."
            )
            builder.add_finding(
                rule_id="PERF-TTFB-016",
                category="performance",
                severity=STATUS_WARNING,
                title="Slow Server Response Time (TTFB > 1500ms)",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=["Optimize database queries, configure edge CDN caching, or upgrade hosting infrastructure."],
                impact_estimate="Crawl budget exhaustion and higher bounce rate."
            )
        else:
            builder.add_evidence(
                rule_id="PERF-TTFB-016",
                category="performance",
                title="Time to First Byte (TTFB)",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{response_time_ms} ms",
                expected="TTFB <= 1500 ms",
                message=f"Server response time is fast ({response_time_ms} ms)."
            )

    # SOCIAL-OG-017: Open Graph Metadata
    og_data = html_data.get("open_graph", {})
    has_og_title = bool(og_data.get("og:title"))
    has_og_image = bool(og_data.get("og:image"))
    if not (has_og_title and has_og_image):
        builder.add_evidence(
            rule_id="SOCIAL-OG-017",
            category="technical",
            title="Open Graph Metadata",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="Incomplete Open Graph tags" if og_data else "No Open Graph tags",
            expected="og:title and og:image declared",
            message="Document lacks essential Open Graph metadata (og:title, og:image) for rich social media cards."
        )
    else:
        builder.add_evidence(
            rule_id="SOCIAL-OG-017",
            category="technical",
            title="Open Graph Metadata",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="og:title and og:image present",
            expected="og:title and og:image declared",
            message="Essential Open Graph metadata tags are configured."
        )

    # TECH-REDIRECT-018: Redirect Chain Integrity
    chain = http_res.get("redirect_chain", [])
    if len(chain) > 2:
        builder.add_evidence(
            rule_id="TECH-REDIRECT-018",
            category="technical",
            title="Redirect Chain Length",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{len(chain)} redirect hops",
            expected="At most 2 redirect hops",
            message=f"Excessive redirect chain detected ({len(chain)} hops). Can delay crawling and waste crawl budget."
        )
        builder.add_finding(
            rule_id="TECH-REDIRECT-018",
            category="technical",
            severity=STATUS_WARNING,
            title="Excessive Redirect Chain Detected",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Point internal links and canonical references directly to the final destination URL."],
            impact_estimate="Crawl latency and risk of redirect loops or dropped link equity."
        )
    elif any(hop.get("code") == 302 for hop in chain):
        builder.add_evidence(
            rule_id="TECH-REDIRECT-018",
            category="technical",
            title="Redirect Chain Status Integrity",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="Temporary 302 redirect in chain",
            expected="Permanent 301 redirect",
            message="A temporary 302 redirect was detected. Use permanent 301 redirects for permanent site moves."
        )
    elif len(chain) > 0:
        builder.add_evidence(
            rule_id="TECH-REDIRECT-018",
            category="technical",
            title="Redirect Chain Integrity",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{len(chain)} hop(s)",
            expected="Clean redirect chain (<= 2 hops)",
            message="Redirect chain is concise and well-formed."
        )

    if http_res.get("has_redirect_loop", False):
        builder.add_evidence(
            rule_id="TECH-REDIRECT-018",
            category="technical",
            title="Redirect Loop Detected",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed="Redirect loop in HTTP hops",
            expected="Acyclic redirect path",
            message="Server encountered a circular redirect loop. Crawlers terminate and abandon crawl."
        )
        builder.add_finding(
            rule_id="TECH-REDIRECT-018",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Redirect Loop Failure",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=["Resolve circular redirection in server config or application routing."],
            impact_estimate="Complete failure to crawl or index target URL."
        )

    # TECH-SOFT-404-025: Soft 404 Detection
    if http_res.get("is_soft_404", False):
        builder.add_evidence(
            rule_id="TECH-SOFT-404-025",
            category="technical",
            title="Soft 404 Error Detection",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed="HTTP 200 returned for missing or error content",
            expected="HTTP 404 / 410 status code",
            message="Soft 404 detected: page returns HTTP 200 OK but displays missing content or error page text."
        )
        builder.add_finding(
            rule_id="TECH-SOFT-404-025",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Soft 404 Error Detected",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=["Return genuine HTTP 404 Not Found or 410 Gone status code for nonexistent resources."],
            impact_estimate="Search engines index error pages, wasting crawl budget and harming site domain quality."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-SOFT-404-025",
            category="technical",
            title="Soft 404 Error Detection",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="HTTP status aligns with content payload",
            expected="HTTP 200 with valid content",
            message="No soft 404 error patterns detected."
        )

    # PERF-COMPRESSION-021: HTTP Response Compression
    c_encoding = headers.get("content-encoding", "").lower()
    body_bytes_len = len(body_text.encode("utf-8"))
    if not http_res["is_local"] and body_bytes_len > 1024:
        if any(comp in c_encoding for comp in ("gzip", "br", "zstd", "deflate")):
            builder.add_evidence(
                rule_id="PERF-COMPRESSION-021",
                category="performance",
                title="HTTP Response Compression",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=c_encoding,
                expected="br, gzip, or zstd compression",
                message=f"HTTP response is compressed using {c_encoding}."
            )
        else:
            builder.add_evidence(
                rule_id="PERF-COMPRESSION-021",
                category="performance",
                title="HTTP Response Compression",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed="Uncompressed",
                expected="br, gzip, or zstd compression",
                message=f"HTTP response payload ({body_bytes_len} bytes) is uncompressed."
            )
            builder.add_finding(
                rule_id="PERF-COMPRESSION-021",
                category="performance",
                severity=STATUS_WARNING,
                title="Missing HTTP Response Compression",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=["Enable gzip, Brotli (br), or zstd compression on web server or CDN."],
                impact_estimate="Increases payload transfer size and mobile page load latency."
            )
    else:
        builder.add_evidence(
            rule_id="PERF-COMPRESSION-021",
            category="performance",
            title="HTTP Response Compression",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=c_encoding or "Local or compact payload",
            expected="N/A",
            message="Payload size is compact or inspected locally."
        )

    # PERF-CACHE-022: HTTP Cache-Control Header
    cache_ctrl = headers.get("cache-control", "")
    if not http_res["is_local"]:
        if cache_ctrl:
            builder.add_evidence(
                rule_id="PERF-CACHE-022",
                category="performance",
                title="HTTP Cache-Control Header",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=cache_ctrl,
                expected="Valid Cache-Control header",
                message=f"Cache-Control configured: {cache_ctrl}."
            )
        else:
            builder.add_evidence(
                rule_id="PERF-CACHE-022",
                category="performance",
                title="HTTP Cache-Control Header",
                status=STATUS_INFO,
                confidence=CONFIDENCE_VERIFIED,
                observed="None",
                expected="Cache-Control header configured",
                message="HTTP response does not specify a Cache-Control header."
            )

    # TECH-SITEMAP-LIMIT-026: XML Sitemap URL Limit
    if sitemap_res and sitemap_res.present:
        if sitemap_res.exceeds_url_limit:
            builder.add_evidence(
                rule_id="TECH-SITEMAP-LIMIT-026",
                category="technical",
                title="XML Sitemap URL Limit",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{sitemap_res.total_urls} URLs",
                expected="<= 50,000 URLs per sitemap",
                message=f"Sitemap exceeds 50,000 URL limit ({sitemap_res.total_urls} URLs found)."
            )
            builder.add_finding(
                rule_id="TECH-SITEMAP-LIMIT-026",
                category="technical",
                severity=STATUS_WARNING,
                title="Sitemap Exceeds 50,000 URL Limit",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P1_HIGH",
                remediation_steps=["Split sitemap into multiple files and use a sitemap index (<sitemapindex>)."],
                impact_estimate="Search engines will reject or truncate sitemap processing beyond 50,000 URLs."
            )
        else:
            builder.add_evidence(
                rule_id="TECH-SITEMAP-LIMIT-026",
                category="technical",
                title="XML Sitemap URL Limit",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{sitemap_res.total_urls} URLs",
                expected="<= 50,000 URLs per sitemap",
                message="Sitemap URL count is within the 50,000 limit."
            )

    # TECH-HEADING-HIERARCHY-027: Semantic Heading Hierarchy
    hdg_info = html_data.get("headings", {})
    empty_hdgs = hdg_info.get("empty_count", 0)
    jumps_count = hdg_info.get("hierarchy_jumps_count", 0)
    if empty_hdgs > 0 or jumps_count > 0:
        builder.add_evidence(
            rule_id="TECH-HEADING-HIERARCHY-027",
            category="technical",
            title="Semantic Heading Hierarchy",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{empty_hdgs} empty heading(s), {jumps_count} level jump(s)",
            expected="Sequential heading hierarchy without empty tags",
            message=f"Heading outline contains {empty_hdgs} empty heading tag(s) and {jumps_count} hierarchy level jump(s)."
        )
        builder.add_finding(
            rule_id="TECH-HEADING-HIERARCHY-027",
            category="technical",
            severity=STATUS_INFO,
            title="Heading Hierarchy Irregularities",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P3_LOW",
            remediation_steps=[
                "Ensure headings don't skip levels (e.g. H1 followed immediately by H3).",
                "Remove empty heading elements."
            ],
            impact_estimate="Minor accessibility and section chunking imperfection; no penalty to technical score."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-HEADING-HIERARCHY-027",
            category="technical",
            title="Semantic Heading Hierarchy",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="Clean sequential heading outline",
            expected="Sequential heading hierarchy",
            message="Heading outline is structurally sound without empty headings or level jumps."
        )

    # TECH-LINK-ANCHOR-028: Descriptive Link Anchor Text
    empty_anchors = html_data.get("links", {}).get("empty_anchors_count", 0)
    tot_links = html_data.get("links", {}).get("total_count", 0)
    if empty_anchors > 0:
        builder.add_evidence(
            rule_id="TECH-LINK-ANCHOR-028",
            category="technical",
            title="Descriptive Link Anchor Text",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{empty_anchors} empty anchor link(s) of {tot_links} total",
            expected="All links have anchor text, aria-label, or img alt",
            message=f"Document contains {empty_anchors} link(s) without descriptive text, aria-label, or child image alt."
        )
        builder.add_finding(
            rule_id="TECH-LINK-ANCHOR-028",
            category="technical",
            severity=STATUS_WARNING,
            title="Links Missing Descriptive Anchor Text",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Add descriptive anchor text or aria-label attributes to all <a> elements."],
            impact_estimate="Weakens internal link context for crawlers and fails WCAG 2.4.4 accessibility."
        )
    elif tot_links > 0:
        builder.add_evidence(
            rule_id="TECH-LINK-ANCHOR-028",
            category="technical",
            title="Descriptive Link Anchor Text",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"All {tot_links} links have descriptive text or aria-label",
            expected="Descriptive anchor text",
            message="All links provide descriptive text or accessible labels."
        )

    # TECH-FORM-LABEL-029: Accessible Form Input Labels
    unlabelled_inputs = html_data.get("forms", {}).get("unlabelled_count", 0)
    tot_inputs = html_data.get("forms", {}).get("total_inputs", 0)
    if unlabelled_inputs > 0:
        builder.add_evidence(
            rule_id="TECH-FORM-LABEL-029",
            category="technical",
            title="Accessible Form Input Labels",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{unlabelled_inputs} of {tot_inputs} input(s) lack labels",
            expected="Every form input has an associated <label> or aria-label",
            message=f"{unlabelled_inputs} form input(s) lack an associated <label for='...'> or aria-label attribute."
        )
        builder.add_finding(
            rule_id="TECH-FORM-LABEL-029",
            category="technical",
            severity=STATUS_WARNING,
            title="Form Inputs Missing Accessible Labels",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Associate each input with `<label for='id'>` or add `aria-label='...'`."],
            impact_estimate="Fails accessibility audits and impairs screen readers and autonomous form-filling agents."
        )
    elif tot_inputs > 0:
        builder.add_evidence(
            rule_id="TECH-FORM-LABEL-029",
            category="technical",
            title="Accessible Form Input Labels",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"All {tot_inputs} inputs have accessible labels",
            expected="Accessible labels for inputs",
            message="All form inputs have accessible labels."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-FORM-LABEL-029",
            category="technical",
            title="Accessible Form Input Labels",
            status=STATUS_NOT_APPLICABLE,
            confidence=CONFIDENCE_VERIFIED,
            observed="0 form inputs present",
            expected="N/A",
            message="No form inputs on page; label requirement is not applicable."
        )

    # TECH-LANDMARKS-030: HTML5 Semantic Landmarks
    landmarks = html_data.get("landmarks", {})
    if landmarks.get("has_main"):
        builder.add_evidence(
            rule_id="TECH-LANDMARKS-030",
            category="technical",
            title="HTML5 Semantic Landmarks",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="<main> landmark present",
            expected="<main> landmark present",
            message="Document utilizes semantic <main> landmark."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-LANDMARKS-030",
            category="technical",
            title="HTML5 Semantic Landmarks",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="Missing <main> tag",
            expected="<main> landmark",
            message="Document does not declare a semantic <main> landmark tag."
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

    if content_data.opening_has_direct_answer and content_data.total_words >= 25:
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

    if content_data.monolithic_chunks_count == 0 and content_data.total_chunks > 0 and content_data.total_words >= 25:
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

    if content_data.pronoun_lead_count <= 2 and content_data.total_words >= 25:
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

    from .analyzers.content_analyzer import CITATION_CUES
    citations_count = sum(1 for c in content_data.chunks if c.has_citation)
    raw_citations_found = sum(1 for cue in CITATION_CUES if cue in content_text.lower())
    citations_count = max(citations_count, raw_citations_found)

    builder.add_signal("content_citations_count", "Citation Cues Count", citations_count, unit="count")
    builder.add_signal("content_unverified_stats_count", "Unverified Stats Count", content_data.unverified_stats_count, unit="count")

    if citations_count > 0:
        builder.add_evidence(
            rule_id="GEO-SOURCE-ATTRIBUTION-005",
            category="geo",
            title="Source Attribution & Citations",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{citations_count} citation cue(s) found",
            expected="Explicit source citations and attribution",
            message="Content incorporates explicit source citations and verifiable references."
        )

    if content_data.evidence_density_score >= 20 and content_data.unverified_stats_count == 0:
        builder.add_evidence(
            rule_id="GEO-EVIDENCE-METRICS-004",
            category="geo",
            title="Evidence & Fact Density",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"Evidence density score: {content_data.evidence_density_score}/100",
            expected="Empirical metrics and verified factual assertions",
            message="Content incorporates verified empirical data and statistical support."
        )

    # E-E-A-T & Trust Evidence
    for ef in eeat_data.findings:
        builder.add_evidence(
            rule_id=ef.rule_id,
            category="geo",
            title=f"E-E-A-T: {ef.dimension}",
            status=ef.severity,
            confidence=CONFIDENCE_VERIFIED if ef.dimension != "Experience" else CONFIDENCE_HEURISTIC,
            observed=ef.details or ef.message,
            expected="Demonstrated Experience, Expertise, Authoritativeness, and Transparency",
            message=ef.message
        )
        if ef.severity in (STATUS_CRITICAL, STATUS_WARNING):
            builder.add_finding(
                rule_id=ef.rule_id,
                category="geo",
                severity=ef.severity,
                title=f"E-E-A-T Signal Issue: {ef.rule_id}",
                confidence=CONFIDENCE_VERIFIED if ef.dimension != "Experience" else CONFIDENCE_HEURISTIC,
                action_priority="P1_HIGH" if ef.severity == STATUS_CRITICAL else "P2_MEDIUM",
                remediation_steps=[ef.message],
                impact_estimate="Impairs human trust signals and AI engine citation confidence."
            )

    # Freshness & Temporal Consistency Evidence
    for ff in freshness_data.findings:
        builder.add_evidence(
            rule_id=ff.rule_id,
            category="technical" if "DATE" in ff.rule_id else "geo",
            title=f"Freshness: {ff.rule_id}",
            status=ff.severity,
            confidence=CONFIDENCE_VERIFIED,
            observed=ff.details or ff.message,
            expected="Consistent publication and modification dates without temporal contradiction",
            message=ff.message
        )
        if ff.severity in (STATUS_CRITICAL, STATUS_WARNING):
            builder.add_finding(
                rule_id=ff.rule_id,
                category="technical" if "DATE" in ff.rule_id else "geo",
                severity=ff.severity,
                title=f"Temporal Consistency Issue: {ff.rule_id}",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P1_HIGH" if ff.severity == STATUS_CRITICAL else "P2_MEDIUM",
                remediation_steps=[ff.message],
                impact_estimate="Search crawlers detect temporal contradictions or discard stale documents."
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
    md.append(f"| **Security Hygiene Score** | **{scores.security_score} / 100** ({scores.security_tier}) | Independent dimension: HTTPS (25%), HSTS (25%), Mixed Content (25%), Headers (25%) |")
    md.append(f"| **GEO Readiness Index** | **{scores.geo_readiness_index} / 100** ({scores.geo_maturity_tier}) | Direct answer frontloading, chunking, coreference, Schema graph |")
    crit_obs = ledger.metadata.get("criteria_observed", ledger.metadata.get("signals_measured", 0))
    crit_tot = ledger.metadata.get("criteria_total", ledger.metadata.get("signals_total", 0))
    md.append(f"| **Observation Coverage** | **{scores.observation_coverage_pct}%** ({crit_obs}/{crit_tot} criteria) | Empirical completeness of audit scope |")
    md.append("")

    # Historical Comparison (if previous audit provided)
    hist = ledger.metadata.get("historical_comparison")
    if hist:
        md.append("## Historical Audit Comparison")
        md.append("")
        prev_tech = hist.get("previous_technical_score", "N/A")
        tech_delta = hist.get("technical_score_delta", 0)
        tech_sign = "+" if isinstance(tech_delta, (int, float)) and tech_delta > 0 else ""
        prev_geo = hist.get("previous_geo_score", "N/A")
        geo_delta = hist.get("geo_score_delta", 0)
        geo_sign = "+" if isinstance(geo_delta, (int, float)) and geo_delta > 0 else ""
        md.append(f"- **Technical Score**: `{prev_tech}` -> **{scores.observable_technical_score}** ({tech_sign}{tech_delta} pts)")
        md.append(f"- **GEO Readiness**: `{prev_geo}` -> **{scores.geo_readiness_index}** ({geo_sign}{geo_delta} pts)")
        resolved = hist.get("resolved_findings", [])
        new_f = hist.get("new_findings", [])
        md.append(f"- **Resolved Issues**: {len(resolved)} (`{', '.join(resolved) if resolved else 'None'}`)")
        md.append(f"- **New Issues Detected**: {len(new_f)} (`{', '.join(new_f) if new_f else 'None'}`)")
        md.append("")

    idx_dict = ledger.metadata.get("indexability_matrix")
    if idx_dict:
        verdict = idx_dict.get("verdict", "UNKNOWN")
        if verdict == "INDEXABLE":
            v_badge = "**[INDEXABLE]**"
        elif verdict == "BLOCKED":
            v_badge = "**[BLOCKED]**"
        elif verdict == "CONFLICTED":
            v_badge = "**[CONFLICTED]**"
        else:
            v_badge = "**[AMBIGUOUS]**"
        md.append("## Indexability Matrix")
        md.append("")
        md.append(f"> **Final Indexability Verdict**: {v_badge} (Confidence: **{idx_dict.get('confidence_score', 0)}%**)")
        if idx_dict.get("blockers"):
            md.append(f"> **Active Indexability Blockers**: {', '.join(idx_dict['blockers'])}")
        if idx_dict.get("conflicting_signals"):
            md.append(f"> **Contradictory Directives**: {'; '.join(idx_dict['conflicting_signals'])}")
        md.append("")
        md.append("| Vector | Status | Evaluated Value / Reason |")
        md.append("| :--- | :--- | :--- |")
        for v_name, v_data in idx_dict.get("vectors", {}).items():
            st = v_data.get("status", "")
            st_b = "[PASS]" if st in ("PASS", "200_OK", "MATCH", "SELF_CANONICAL") else ("[BLOCKED]" if st in ("BLOCK", "NOINDEX", "DISALLOWED", "SOFT_404") else f"[{st}]")
            md.append(f"| **{v_name.replace('_', ' ').title()}** | `{st_b}` | {v_data.get('detail', '')} |")
        md.append("")

    if scores.security_hygiene:
        sec = scores.security_hygiene
        md.append("### Security Hygiene Breakdown")
        md.append("")
        md.append("| Dimension | Score | Status | Details |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **HTTPS Protocol** | {sec.https_score} / 25 pts | `{'[PASS]' if sec.https_score == 25 else '[FAIL]'}` | Served over secure HTTPS wire |")
        md.append(f"| **HSTS Header** | {sec.hsts_score} / 25 pts | `{'[PASS]' if sec.hsts_score == 25 else '[WARN]'}` | Strict-Transport-Security configured |")
        md.append(f"| **Mixed Content** | {sec.mixed_content_score} / 25 pts | `{'[PASS]' if sec.mixed_content_score == 25 else '[FAIL]'}` | Zero insecure http:// resource links |")
        md.append(f"| **Security Headers** | {sec.headers_score} / 25 pts | `{'[PASS]' if sec.headers_score >= 18 else '[WARN]'}` | X-Content-Type-Options, CSP, Frame Options |")
        md.append("")

    # GEO 8-Component Breakdown
    if scores.geo_dimensions:
        geo = scores.geo_dimensions
        md.append("## GEO Readiness Breakdown (8 Dimensions)")
        md.append("")
        md.append(f"> **GEO Readiness Index**: **{scores.geo_readiness_index} / 100** ({scores.geo_maturity_tier})  ")
        unk_str = ", ".join(geo.unknown_dimensions) if geo.unknown_dimensions else "None"
        md.append(f"> **Unknown Dimensions**: `{unk_str}`  ")
        md.append("")
        md.append("| Dimension | Max Weight | Points | Evaluation Basis |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **Answerability** | 20 | **{geo.answerability} pts** | Direct definition / resolution syntax in opening 60 words |")
        md.append(f"| **Evidence Density** | 20 | **{geo.evidence_density} pts** | Numerical statistics, percentages, and verifiable metrics |")
        md.append(f"| **Entity Clarity** | 15 | **{geo.entity_clarity} pts** | Coreference independence (avoids ambiguous pronouns) |")
        md.append(f"| **Passage Extractability** | 15 | **{geo.passage_extractability} pts** | Modular 100-200 word sections suited for vector retrieval |")
        md.append(f"| **Source Attribution** | 10 | **{geo.source_attribution} pts** | Authoritative citations, RFC standards, research refs |")
        md.append(f"| **Schema & Entity Graph** | 10 | **{geo.schema_graph} pts** | Interconnected JSON-LD graph with stable @id anchors |")
        md.append(f"| **Freshness & Temporal** | 5 | **{geo.freshness} pts** | Publication/modification dates and temporal consistency |")
        md.append(f"| **AI Crawler Access** | 5 | **{geo.ai_crawler_access} pts** | Search & retrieval AI bots permitted in robots.txt |")
        md.append("")
        md.append("> *Non-Guarantee Policy*: High GEO Readiness indicates document extractability and retrieval readiness; it does not guarantee neural generation or citation by third-party AI models.")
        md.append("")

    # E-E-A-T Profile
    eeat = ledger.metadata.get("eeat_analysis")
    if eeat:
        md.append("## E-E-A-T & Trust Profile")
        md.append("")
        auth_name = eeat.get("author_name") or "Not identified"
        bio_st = "Present" if eeat.get("has_author_bio") else "Missing"
        md.append(f"- **Author**: `{auth_name}` (Bio: `{bio_st}`)")
        same_as = eeat.get("author_same_as", [])
        same_as_str = ", ".join(same_as) if same_as else "None"
        md.append(f"- **Authority Profiles (sameAs)**: `{same_as_str}`")
        org_name = eeat.get("organization_name") or "Not identified"
        md.append(f"- **Publishing Organization**: `{org_name}`")
        md.append(f"- **Transparency Touchpoints**: About: `{'Yes' if eeat.get('has_about_page') else 'No'}`, Contact: `{'Yes' if eeat.get('has_contact_page') else 'No'}`, Editorial Policy: `{'Yes' if eeat.get('has_editorial_policy') else 'No'}`")
        md.append(f"- **First-Hand Experience Markers**: **{eeat.get('first_hand_experience_count', 0)}** detected")
        ymyl_str = "Yes" if eeat.get("is_ymyl_content") else "No"
        disc_str = " (Disclaimer: Present)" if (eeat.get("is_ymyl_content") and eeat.get("has_ymyl_disclaimer")) else (" (Disclaimer: MISSING)" if eeat.get("is_ymyl_content") else "")
        md.append(f"- **YMYL Content Detected**: `{ymyl_str}{disc_str}`")
        md.append("")

    # Schema & Rich Results Verdict
    sch_v = ledger.metadata.get("schema_verdict")
    if sch_v:
        md.append("## Schema.org & Rich Results Verdict")
        md.append("")
        md.append(f"- **Syntax Valid**: `{sch_v.get('syntax_valid', 'YES')}`")
        md.append(f"- **Schema.org Structure**: `{sch_v.get('schema_org_structure', 'VALID')}`")
        md.append(f"- **Google Rich Result Eligibility**: `{sch_v.get('google_rich_result_eligibility', 'UNKNOWN')}`")
        md.append(f"- **Visible-Content Consistency**: `{sch_v.get('visible_content_consistency', 'UNKNOWN')}`")
        md.append("")

    md.append("> [!NOTE]")
    md.append("> **Evidence Ledger Invariant: 'Unknown != Failure'**  ")
    md.append(f"> Exactly {scores.not_measured_count} unmeasured external signal(s) (e.g., CWV CrUX field data) were detected. In compliance with the Evidence Protocol, unmeasured signals carry 0 penalty and are explicitly segregated from verified defects.")
    md.append("")

    cat_cov = ledger.metadata.get("category_coverage", {})
    if cat_cov:
        md.append("### Criteria Breakdown by Category")
        md.append("")
        md.append("| Category | Total | Observed | Passed | Failed | Unknown | N/A | Coverage |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for cat_name, c_data in cat_cov.items():
            md.append(f"| **{cat_name.capitalize()}** | {c_data['total']} | {c_data['observed']} | {c_data['passed']} | {c_data['failed']} | {c_data['unknown']} | {c_data['not_applicable']} | **{c_data['coverage_pct']}%** |")
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
    md.append("| Category | Rule ID | Tier | Status | Confidence | Observed Value | Expected Contract |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for ev in ledger.evidence:
        status_badge = (
            "[CRITICAL]" if ev.status == STATUS_CRITICAL
            else ("[WARNING]" if ev.status == STATUS_WARNING
            else ("[PASS]" if ev.status == STATUS_PASS
            else ("[NOT_MEASURED]" if ev.status == STATUS_NOT_MEASURED else "[INFO]")))
        )
        obs_str = str(ev.observed).replace("\n", " ")[:60]
        exp_str = str(ev.expected).replace("\n", " ")[:60]
        ev_tier = getattr(ev, "tier", "") or "Tier E"
        md.append(f"| `{ev.category}` | `{ev.rule_id}` | `{ev_tier}` | `{status_badge}` | `{ev.confidence}` | {obs_str} | {exp_str} |")
    md.append("")

    return "\n".join(md)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Ultimate SEO & GEO Autonomous Inspection Engine v3.1.0")
    parser.add_argument("target", nargs="?", default=None, help="Target URL (https://...) or local HTML file path")
    parser.add_argument("--validate-schema", nargs="?", const="stdin", default=None, help="Validate standalone Schema.org JSON-LD snippet (file path, raw JSON string, or stdin)")
    parser.add_argument("--format", choices=["markdown", "json", "sarif"], default="markdown", help="Output format (markdown, json, or sarif)")
    parser.add_argument("--output", help="Optional output file path to write results")
    parser.add_argument("--sarif", help="Optional output file path to write OASIS SARIF v2.1.0 report")
    parser.add_argument("--robots", help="Optional custom robots.txt file or URL")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP request timeout in seconds")
    parser.add_argument("--user-agent", default=None, help="Custom User-Agent header for HTTP inspection")
    parser.add_argument("--rendered-html", default=None, help="Path to pre-rendered HTML file or raw HTML string")
    parser.add_argument("--previous-audit", default=None, help="Path to previous inspection JSON report for historical comparison & score delta")
    parser.add_argument("--strict", action="store_true", help="Strict CI mode: exit with non-zero code (2) if any CRITICAL finding is detected")
    parser.add_argument("--fail-on", choices=["P0", "P1", "P2", "CRITICAL", "WARNING"], default=None, help="Fail CI pipeline if findings matching priority or severity exist")
    parser.add_argument("--fail-on-score", type=float, default=None, help="Fail CI pipeline if observable technical score is below threshold (0-100)")
    parser.add_argument("--crawl", action="store_true", help="Enable multi-page crawl mode starting from target URL")
    parser.add_argument("--max-pages", type=int, default=50, help="Maximum number of pages to crawl (default: 50)")
    parser.add_argument("--depth", type=int, default=3, help="Maximum crawl depth from seed (default: 3)")
    parser.add_argument("--config", default=None, help="Path to ultimate-seo-geo.json configuration file")
    parser.add_argument("--experiment", action="store_true", help="Run AI Citation Benchmark Before/After experiment comparison")
    parser.add_argument("--before", help="Path to baseline benchmark JSON file")
    parser.add_argument("--after", help="Path to post-optimization benchmark JSON file")

    args = parser.parse_args()

    # AI Citation Benchmark Experiment Mode
    if args.experiment:
        if not args.before or not args.after:
            parser.error("--experiment requires both --before <file> and --after <file>")
        comp_res = compare_experiments(args.before, args.after)
        if args.format == "json":
            import json
            out_str = json.dumps(comp_res, indent=2)
        else:
            out_str = render_experiment_markdown(comp_res)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out_str)
            print(f"Experiment results saved to {args.output}")
        else:
            print(out_str)
        return

    # Load configuration
    cfg = EngineConfig.load(args.config)

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

    # Site-Level Crawl Mode
    if args.crawl:
        from .crawler import CrawlConfig, crawl_site, format_site_crawl_markdown
        config = CrawlConfig(
            seed_url=args.target,
            max_pages=args.max_pages,
            max_depth=args.depth,
            timeout=args.timeout,
            user_agent=args.user_agent
        )
        report = crawl_site(config)
        if args.format == "json":
            import json
            output_str = json.dumps(report.to_dict(), indent=2)
        else:
            output_str = format_site_crawl_markdown(report)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_str)
            print(f"Crawl report saved to {args.output}")
        else:
            print(output_str)
        return

    custom_robots = None
    if args.robots:
        if os.path.exists(args.robots):
            with open(args.robots, "r", encoding="utf-8", errors="replace") as f:
                custom_robots = f.read()
        else:
            custom_robots = args.robots

    try:
        ledger, scores = run_inspection(
            args.target,
            custom_robots_txt=custom_robots,
            timeout=args.timeout,
            user_agent=args.user_agent,
            rendered_html=args.rendered_html
        )
    except Exception as exc:
        sys.stderr.write(f"Error executing inspection: {exc}\n")
        sys.exit(1)

    # Historical Audit Comparison
    if args.previous_audit and os.path.exists(args.previous_audit):
        try:
            with open(args.previous_audit, "r", encoding="utf-8", errors="replace") as pf:
                import json
                prev_data = json.load(pf)
            prev_scores = prev_data.get("scores", {})
            prev_tech = prev_scores.get("observable_technical_score", prev_scores.get("overall_seo_score"))
            prev_geo = prev_scores.get("geo_readiness_index")
            prev_findings = {f.get("rule_id") for f in prev_data.get("findings", []) if f.get("rule_id")}
            curr_findings = {f.rule_id for f in ledger.findings}

            hist_comp = {
                "previous_file": args.previous_audit,
                "previous_technical_score": prev_tech,
                "technical_score_delta": round(scores.observable_technical_score - prev_tech, 2) if prev_tech is not None else 0,
                "previous_geo_score": prev_geo,
                "geo_score_delta": round(scores.geo_readiness_index - prev_geo, 2) if prev_geo is not None else 0,
                "resolved_findings": sorted(list(prev_findings - curr_findings)),
                "new_findings": sorted(list(curr_findings - prev_findings))
            }
            ledger.metadata["historical_comparison"] = hist_comp
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to parse previous audit file: {e}\n")

    # Output Formatting
    if args.format == "json":
        res_dict = ledger.to_dict()
        res_dict["scores"] = scores.__dict__
        import json
        output_str = json.dumps(res_dict, indent=2, default=str)
    elif args.format == "sarif":
        from .sarif import format_sarif_json
        output_str = format_sarif_json(ledger)
    else:
        output_str = format_markdown_report(ledger, scores)

    # Secondary SARIF Export
    if args.sarif:
        from .sarif import format_sarif_json
        sarif_str = format_sarif_json(ledger)
        with open(args.sarif, "w", encoding="utf-8") as sf:
            sf.write(sarif_str)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Inspection report saved to {args.output}")
    else:
        print(output_str)

    # CI Quality Gates Enforcement
    ci_failed = False
    failure_reasons = []

    if args.strict:
        critical_findings = [f for f in ledger.findings if f.severity == STATUS_CRITICAL]
        if critical_findings:
            ci_failed = True
            failure_reasons.append(f"--strict mode: {len(critical_findings)} CRITICAL finding(s) detected")

    if args.fail_on:
        matching = []
        for f in ledger.findings:
            p_prefix = f.action_priority.split("_")[0] if f.action_priority else ""
            if args.fail_on in (f.action_priority, p_prefix, f.severity):
                matching.append(f)
        if matching:
            ci_failed = True
            failure_reasons.append(f"--fail-on {args.fail_on}: {len(matching)} finding(s) matched criteria")

    if args.fail_on_score is not None:
        if scores.observable_technical_score < args.fail_on_score:
            ci_failed = True
            failure_reasons.append(f"--fail-on-score {args.fail_on_score}: observable score is {scores.observable_technical_score}")

    if ci_failed:
        sys.stderr.write("\n[CI FAILURE] Quality gate thresholds violated:\n")
        for fr in failure_reasons:
            sys.stderr.write(f"  - {fr}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
