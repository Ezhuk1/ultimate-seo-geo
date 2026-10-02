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
import re
import argparse
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List

from .analyzers.http_analyzer import analyze_target_http
from .analyzers.html_analyzer import analyze_target_html
from .analyzers.robots_simulator import parse_robots_txt, simulate_ai_crawlers
from .analyzers.schema_analyzer import analyze_json_ld, validate_schema_snippet
from .analyzers.content_analyzer import analyze_content
from .analyzers.content_analyzer import analyze_section_pyramid, analyze_information_gain
from .analyzers.content_analyzer import analyze_slop_patterns, analyze_audience_definition
from .analyzers.sitemap_analyzer import parse_sitemap_xml, SitemapAnalysisResult, merge_sitemap_results

MAX_SITEMAP_INDEX_CHILDREN = 50  # hard cap on sitemap-index children to expand
from .analyzers.eeat_analyzer import analyze_eeat
from .analyzers.freshness_analyzer import analyze_freshness
from .analyzers.performance_analyzer import analyze_performance
from .analyzers.llms_analyzer import check_llms_txt, check_llms_full_txt, generate_llms_txt, generate_llms_full_txt, LlmsTxtResult
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


def _bot_challenge_signature(status_code: int, headers: Optional[Dict[str, Any]], body: str) -> Optional[str]:
    """Returns a challenge/block marker when an edge WAF answers a bot fetch
    with a block or interactive challenge instead of real content."""
    headers = headers or {}
    if status_code in (401, 403, 429, 501):
        return f"HTTP {status_code}"
    cf_mit = str(headers.get("cf-mitigated", "") or "").lower()
    if "challenge" in cf_mit:
        return "cf-mitigated: challenge"
    body_head = (body or "")[:4000].lower()
    for marker in ("just a moment...", "checking your browser", "attention required",
                   "cf-challenge", "turnstile", "captcha-delivery", "verifying you are human"):
        if marker in body_head:
            return f"challenge page: {marker}"
    return None


def run_inspection(
    target: str,
    custom_robots_txt: Optional[str] = None,
    custom_sitemap_xml: Optional[str] = None,
    timeout: float = 15.0,
    user_agent: Optional[str] = None,
    rendered_html: Optional[str] = None,
    config: Optional[EngineConfig] = None
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
        headings=html_data["headings"].get("outline", []),
        title=html_data["title"].get("value"),
        description=html_data["meta_description"].get("value"),
        extractable_elements=html_data.get("extractable_elements"),
        content_ratio=html_data.get("content_ratio"),
        schema_entities=schema_data.entities if schema_data else [],
        links=html_data.get("links", {}).get("all", [])
    )

    # Round-4 GEO: section pyramid + information gain (Tier E heuristics)
    try:
        section_pyramid = analyze_section_pyramid(content_text, headings=html_data["headings"].get("outline", []))
        info_gain = analyze_information_gain(content_text)
    except Exception:
        section_pyramid = {"sections_total": 0, "sections_frontloaded": 0, "ratio_pct": None, "weak_sections": [], "applicable": False}
        info_gain = {"trigger_count": 0, "triggers": [], "water_phrases": [], "applicable": False}

    # Round-5 GEO: AI-slop density + entity category-for-audience definition
    try:
        slop_data = analyze_slop_patterns(content_text)
        audience_def = analyze_audience_definition(content_data.opening_snippet)
    except Exception:
        slop_data = {"applicable": False, "word_count": 0, "hit_count": 0, "density_per_1000": 0.0, "matches": [], "verdict": "LOW"}
        audience_def = {"found": False, "snippet": ""}

    # 4.5 Performance & Asset Inspection
    final_url = http_res.get("final_url", target)
    psi_key = getattr(config, "psi_api_key", None) if config else None
    perf_data = analyze_performance(html_data, target_url=final_url, psi_api_key=psi_key)

    # 4.6 /llms.txt AI Context File Check
    llms_res: Optional[LlmsTxtResult] = None
    if not http_res["is_local"] and final_url.startswith(("http://", "https://")):
        llms_res = check_llms_txt(final_url, timeout=min(3.0, timeout))

    # 5. Robots & Sitemap Inspection
    parsed_target = urlparse(final_url)
    target_path = parsed_target.path or "/"

    robots_sim: Optional[Dict[str, Any]] = None
    robots_ast: Optional[Any] = None
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
        for child_sm_url in sitemap_res.nested_sitemaps[:MAX_SITEMAP_INDEX_CHILDREN]:
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
    builder.add_signal("html_hreflang_count", "Hreflang Tags Count", html_data.get("hreflang", {}).get("count", 0), unit="count")
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
    builder.metadata["page_title"] = html_data["title"]["value"]
    builder.metadata["page_visible_text"] = (content_text or "")[:20000]
    builder.metadata["meta_description"] = html_data["meta_description"]["value"]
    builder.metadata["html_links"] = html_data.get("links", {}).get("all", [])
    builder.metadata["schema_verdict"] = {
        "syntax_valid": schema_data.syntax_valid,
        "schema_org_structure": schema_data.schema_org_structure,
        "google_rich_result_eligibility": schema_data.google_rich_result_eligibility,
        "visible_content_consistency": schema_data.visible_content_consistency
    }

    # SCHEMA-ENTITY-LINK-026: entity graph connectivity for disambiguation
    try:
        _etypes = {str(e.get("@type")) for e in schema_data.entities if e.get("@type")}
        _etypes.discard("None")
        _link_props = ("author", "publisher", "brand", "hasOfferCatalog", "about",
                       "mainEntity", "reviewedBy", "member", "founder")
        _linked = any(any(k.lower() in _link_props for k in (e.keys() if isinstance(e, dict) else []))
                      for e in schema_data.entities)
        _has_org = bool(_etypes & {"Organization", "Corporation", "LocalBusiness", "WebSite"})
        _has_offer = bool(_etypes & {"Product", "Service", "Offer", "Article", "BlogPosting"})
        if _has_org and _has_offer and not _linked:
            builder.add_evidence(
                rule_id="SCHEMA-ENTITY-LINK-026",
                category="schema",
                title="Entity Graph Connectivity (Disambiguation)",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Entity types present: {sorted(_etypes)[:8]}, but no linking properties (author/publisher/brand/hasOfferCatalog)",
                expected="Organization linked to content entities via author/publisher/brand/hasOfferCatalog",
                message="Knowledge-graph entities exist but are not cross-linked, so LLMs cannot disambiguate the publisher behind the content."
            )
            builder.add_finding(
                rule_id="SCHEMA-ENTITY-LINK-026",
                category="schema",
                severity=STATUS_WARNING,
                title="Unlinked Schema Entities (No Publisher/Author Connectivity)",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    "Inside one @graph, connect entities explicitly:",
                    "Organization -> publisher on Article; author -> Person with sameAs to profiles; hasOfferCatalog -> Product/Service."
                ],
                impact_estimate="Generative engines conflate the brand with unrelated entities; weaker knowledge-graph grounding."
            )
        elif _etypes:
            builder.add_evidence(
                rule_id="SCHEMA-ENTITY-LINK-026",
                category="schema",
                title="Entity Graph Connectivity (Disambiguation)",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Entity types: {sorted(_etypes)[:8]}; linking properties: {'yes' if _linked else 'single-entity graph'}",
                expected="Cross-linked entities inside a unified @graph",
                message="Schema entity graph is connected enough for entity disambiguation."
            )
    except Exception:
        pass

    # SCHEMA-SPEAKABLE-027: SpeakableSpecification audio/voice answer targeting
    try:
        _has_article = bool(_etypes & {"Article", "NewsArticle", "BlogPosting", "WebPage"})
        _speakable_entities = [e for e in schema_data.entities if "speakable" in e]
        if _speakable_entities:
            _sp_valid = False
            for se in _speakable_entities:
                sp = se.get("speakable")
                if isinstance(sp, dict) and (sp.get("cssSelector") or sp.get("xpath")):
                    _sp_valid = True
                elif isinstance(sp, (list, str)) and sp:
                    _sp_valid = True
            if _sp_valid:
                builder.add_evidence(
                    rule_id="SCHEMA-SPEAKABLE-027",
                    category="schema",
                    title="SpeakableSpecification Audio/Voice Answer Targeting",
                    status=STATUS_PASS,
                    confidence=CONFIDENCE_VERIFIED,
                    observed="speakable property defined with valid CSS/XPath selectors",
                    expected="speakable property on Article/WebPage with SpeakableSpecification",
                    message="Schema speakable property properly specifies audio and voice answer targets for Google Assistant and voice synthesis.",
                    tier="Tier B (Google Structured Data Guidelines)"
                )
            else:
                builder.add_evidence(
                    rule_id="SCHEMA-SPEAKABLE-027",
                    category="schema",
                    title="SpeakableSpecification Audio/Voice Answer Targeting",
                    status=STATUS_WARNING,
                    confidence=CONFIDENCE_VERIFIED,
                    observed="speakable property present but missing valid cssSelector or xpath",
                    expected="Valid cssSelector or xpath targeting key summary paragraphs",
                    message="Schema speakable property is present but lacks valid selector definitions.",
                    tier="Tier B (Google Structured Data Guidelines)"
                )
        elif _has_article:
            builder.add_evidence(
                rule_id="SCHEMA-SPEAKABLE-027",
                category="schema",
                title="SpeakableSpecification Audio/Voice Answer Targeting",
                status=STATUS_INFO,
                confidence=CONFIDENCE_VERIFIED,
                observed="No speakable property on Article/WebPage entity",
                expected="speakable property (SpeakableSpecification) with cssSelector targeting concise answer passages",
                message="Article/WebPage entity does not define speakable. Adding SpeakableSpecification enables text-to-speech answer engines (Google Assistant, Siri) to read key passages aloud.",
                tier="Tier B (Google Structured Data Guidelines)"
            )
    except Exception:
        pass

    if sitemap_res:
        builder.add_signal("sitemap_present", "XML Sitemap Present", sitemap_res.present)
        builder.add_signal("sitemap_total_urls", "Sitemap URL Count", sitemap_res.total_urls, unit="count")
        builder.add_signal("sitemap_target_in_sitemap", "Target URL in Sitemap", sitemap_res.target_in_sitemap)

    # Week 2 Signals
    # Local files have no wire protocol/headers: marking these signals measured
    # turned every local audit into a measured HTTPS failure (security 25/100).
    _wire_measured = not http_res.get("is_local", False)
    builder.add_signal("target_is_https", "Target Protocol HTTPS", final_url.lower().startswith("https://"), is_measured=_wire_measured)
    builder.add_signal("http_hsts_present", "HSTS Header Present", bool(headers.get("strict-transport-security")), is_measured=_wire_measured)
    builder.add_signal("html_insecure_resources_count", "Mixed Insecure Content Count", html_data.get("mixed_content", {}).get("insecure_count", 0), unit="count")
    sec_hdrs_count = sum(1 for h in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy") if h in headers)
    builder.add_signal("http_security_headers_count", "Security Headers Count", sec_hdrs_count, unit="count", is_measured=_wire_measured)
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
    t_px = html_data["title"].get("pixel_width", 0)
    if t_len == 0:
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=0,
            expected="<= 580px (approx 30-65 chars)",
            message="Page has no <title> tag."
        )
        builder.add_finding(
            rule_id="TECH-TITLE-003",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Missing Title Tag",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=["Add a concise descriptive `<title>` (50-60 chars, <= 580px) with primary entity and brand."],
            impact_estimate="Direct loss of search engine snippet generation and LLM query matching."
        )
    elif t_px > 580 or t_len > 70 or (t_len < 20 and t_px < 150):
        trunc_msg = f"Title pixel width ({t_px}px, {t_len} chars) exceeds 580px desktop SERP limit." if t_px > 580 else f"Title length ({t_len} chars, {t_px}px) is too short to establish strong entity relevance."
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{t_len} chars, {t_px}px ('{title_text}')",
            expected="<= 580px (approx 30-65 chars)",
            message=trunc_msg
        )
        builder.add_finding(
            rule_id="TECH-TITLE-003",
            category="technical",
            severity=STATUS_WARNING,
            title="Suboptimal Title Length",
            confidence=CONFIDENCE_HEURISTIC,
            action_priority="P2_MEDIUM",
            remediation_steps=[f"Adjust title from {t_len} characters ({t_px}px) to fit within 580px desktop SERP width (approx 50-60 chars)."],
            impact_estimate="Risk of SERP pixel truncation with ellipses (...) or weak entity grounding."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{t_len} chars, {t_px}px ('{title_text}')",
            expected="<= 580px (approx 30-65 chars)",
            message=f"Title pixel width ({t_px}px, {t_len} chars) fits within Google desktop display limit (<= 580px)."
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
            expected="70-165 characters",
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
    elif d_len < 70 or d_len > 165:
        builder.add_evidence(
            rule_id="TECH-META-DESC-004",
            category="technical",
            title="Meta Description",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{d_len} chars",
            expected="70-165 characters",
            message=f"Meta description length ({d_len} chars) is outside optimal 70-165 window."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-META-DESC-004",
            category="technical",
            title="Meta Description",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{d_len} chars",
            expected="70-165 characters",
            message="Meta description length is optimal (70-165 chars)."
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

    # TECH-INTERSTITIAL-040: content-blocking overlays & cookie walls
    interstitial = html_data.get("interstitial_signals", {}) or {}
    _i_named = interstitial.get("named_walls", [])
    _i_generic = (
        (interstitial.get("dialog_elements", 0) + interstitial.get("aria_modal_markers", 0)
         + interstitial.get("fixed_high_z_overlays", 0)) > 0
        or bool(interstitial.get("generic_overlays"))
    )
    if _i_named:
        builder.add_evidence(
            rule_id="TECH-INTERSTITIAL-040",
            category="technical",
            title="Content-Blocking Overlays & Cookie Walls",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"Named overlay wall(s) served in initial HTML: {', '.join(_i_named[:5])}",
            expected="Content reachable in first-paint HTML without interaction",
            message="Consent/paywall/interstitial overlay markup is present in the served HTML. Crawlers that do not execute interaction flows (Google mobile interstitial policy; AI retrieval bots) may receive a blocked or degraded content view."
        )
        builder.add_finding(
            rule_id="TECH-INTERSTITIAL-040",
            category="technical",
            severity=STATUS_WARNING,
            title="Content-Blocking Overlay Detected (Cookie Wall / Paywall)",
            confidence=CONFIDENCE_HEURISTIC,
            action_priority="P2_MEDIUM",
            remediation_steps=[
                "Defer consent UI to a non-blocking banner; never gate the main answer behind a cookie wall or paywall.",
                "Verify with 'curl -s <URL>': the primary content and answer must be present in the raw response.",
                "Named wall markers detected: " + ", ".join(_i_named[:5])
            ],
            impact_estimate="Google down-ranks pages with intrusive interstitials; AI crawlers quoting raw HTML may extract overlay text instead of page content."
        )
    elif _i_generic:
        builder.add_evidence(
            rule_id="TECH-INTERSTITIAL-040",
            category="technical",
            title="Content-Blocking Overlays & Cookie Walls",
            status=STATUS_INFO,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"Dialog/overlay elements present (dialogs: {interstitial.get('dialog_elements', 0)}, aria-modal: {interstitial.get('aria_modal_markers', 0)}, high-z fixed: {interstitial.get('fixed_high_z_overlays', 0)}); no named consent walls",
            expected="Content reachable in first-paint HTML without interaction",
            message="Modal/dialog markup detected. If it covers the answer on load, AI crawlers and Google's interstitial policy treat it as blocking content."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-INTERSTITIAL-040",
            category="technical",
            title="Content-Blocking Overlays & Cookie Walls",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed="No overlay/consent-wall markup in initial HTML",
            expected="Content reachable in first-paint HTML without interaction",
            message="No content-blocking overlays detected in the served HTML."
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
        vp_parsed = vp_data.get("parsed", {})
        user_scalable = vp_parsed.get("user-scalable", "").lower()
        max_scale = vp_parsed.get("maximum-scale", "")
        is_zoom_blocked = user_scalable in ("no", "0") or max_scale in ("1", "1.0")

        if is_zoom_blocked:
            builder.add_evidence(
                rule_id="TECH-VIEWPORT-006",
                category="technical",
                title="Mobile Responsive Viewport",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=vp_data.get("value", ""),
                expected="width=device-width, initial-scale=1.0 without blocking pinch-to-zoom",
                message="Viewport tag disables pinch-to-zoom scaling ('user-scalable=no' or 'maximum-scale=1.0'). This violates WCAG 1.4.4 accessibility guidelines and harms mobile user experience."
            )
            builder.add_finding(
                rule_id="TECH-VIEWPORT-006",
                category="technical",
                severity=STATUS_WARNING,
                title="Mobile Viewport Disables Pinch-to-Zoom",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=["Remove 'user-scalable=no' and 'maximum-scale=1.0' from the viewport meta tag to permit user scaling."],
                impact_estimate="Degrades mobile accessibility and fails Google/WCAG mobile usability checks."
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
        # Aligned with CRAWLER_POLICIES (robots_simulator): ClaudeBot is MODEL_TRAINING,
        # ChatGPT-User is USER_FETCH — neither is a search-retrieval bot.
        blocked_ai_search = [b for b, res in robots_sim.items() if b in ("OAI-SearchBot", "PerplexityBot", "Claude-SearchBot") and not res.get("target_allowed", res["root_allowed"])]
        blocked_ai_training = [b for b, res in robots_sim.items() if b in ("GPTBot", "Google-Extended", "ClaudeBot", "Bytespider", "CCBot", "Amazonbot") and not res.get("target_allowed", res["root_allowed"])]

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

        if robots_ast and getattr(robots_ast, "exceeds_size_limit", False):
            builder.add_evidence(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                title="Robots.txt Size Limit (RFC 9309)",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{robots_ast.size_bytes} bytes",
                expected="<= 512,000 bytes (500 KiB)",
                message=f"robots.txt size ({robots_ast.size_bytes} bytes) exceeds the RFC 9309 500 KiB (512,000 bytes) limit. Crawlers may truncate the file, causing trailing rules and sitemaps to be ignored."
            )
            builder.add_finding(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                severity=STATUS_WARNING,
                title="Robots.txt Exceeds 500 KiB Limit",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=["Reduce robots.txt size below 500 KiB by consolidating wildcard rules and removing redundant disallow lines."],
                impact_estimate="Search engines may truncate robots.txt and ignore directives defined after the first 500 KiB."
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

        # TECH-SITEMAP-LIMIT-026: XML Sitemap URL and Size Limit (sitemaps.org)
        if sitemap_res.exceeds_url_limit or getattr(sitemap_res, "exceeds_byte_limit", False):
            limit_reasons = []
            if sitemap_res.exceeds_url_limit:
                limit_reasons.append(f"{sitemap_res.total_urls} URLs exceeds 50,000 URL limit")
            if getattr(sitemap_res, "exceeds_byte_limit", False):
                limit_reasons.append(f"{sitemap_res.size_bytes} bytes exceeds 50 MB (52,428,800 bytes) limit")
            builder.add_evidence(
                rule_id="TECH-SITEMAP-LIMIT-026",
                category="technical",
                title="XML Sitemap Size & URL Limit",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed="; ".join(limit_reasons),
                expected="<= 50,000 URLs and <= 50 MB uncompressed",
                message=f"Sitemap violates sitemaps.org limits: {'; '.join(limit_reasons)}. Search engines may discard or fail to parse oversized sitemaps."
            )
            builder.add_finding(
                rule_id="TECH-SITEMAP-LIMIT-026",
                category="technical",
                severity=STATUS_WARNING,
                title="XML Sitemap Exceeds Protocol Limits",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P1_HIGH",
                remediation_steps=[
                    "Split sitemaps containing over 50,000 URLs or 50 MB into multiple smaller sitemap files.",
                    "Reference all split sitemaps via a parent <sitemapindex> file."
                ],
                impact_estimate="Search crawlers will drop URLs exceeding the 50,000 URL / 50 MB boundary."
            )
        else:
            builder.add_evidence(
                rule_id="TECH-SITEMAP-LIMIT-026",
                category="technical",
                title="XML Sitemap Size & URL Limit",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{sitemap_res.total_urls} URLs, {sitemap_res.size_bytes} bytes",
                expected="<= 50,000 URLs and <= 50 MB uncompressed",
                message="Sitemap respects sitemaps.org URL and byte size limits."
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

    # TECH-HREFLANG-033: International Hreflang & Regional Annotations
    hreflang_info = html_data.get("hreflang", {})
    hreflang_tags = hreflang_info.get("tags", [])
    hreflang_count = len(hreflang_tags)

    if hreflang_count == 0:
        builder.add_evidence(
            rule_id="TECH-HREFLANG-033",
            category="technical",
            title="International Hreflang & Regional Annotations",
            status=STATUS_NOT_APPLICABLE,
            confidence=CONFIDENCE_VERIFIED,
            observed="0 hreflang tags declared",
            expected="N/A",
            message="No hreflang tags declared; multi-regional annotations not applicable for single-region document."
        )
    else:
        hreflang_errors = []
        hreflang_warnings = []
        seen_langs = set()
        has_self_ref = False
        target_norm = final_url.lower().rstrip("/")

        iso_pattern = re.compile(r"^(?:[a-z]{2,3}(?:-[A-Za-z0-9]{2,4})*|x-default)$", re.IGNORECASE)

        for tag in hreflang_tags:
            lang_code = tag.get("hreflang", "").strip().lower()
            href = tag.get("href", "").strip()

            if not iso_pattern.match(lang_code):
                hreflang_errors.append(f"Invalid hreflang code '{lang_code}'")
            elif lang_code == "en-uk":
                hreflang_errors.append("Invalid country code 'en-UK' (must use official ISO 3166-1 code 'en-GB')")

            if not href.startswith(("http://", "https://")):
                hreflang_errors.append(f"Relative URL in hreflang: '{href}' (must be absolute HTTPS)")
            elif href.startswith("http://"):
                hreflang_warnings.append(f"Insecure HTTP URL in hreflang: '{href}'")

            if href.lower().rstrip("/") == target_norm:
                has_self_ref = True

            if lang_code in seen_langs:
                hreflang_warnings.append(f"Duplicate hreflang code: '{lang_code}'")
            seen_langs.add(lang_code)

        if hreflang_count >= 2 and not hreflang_info.get("has_x_default", False):
            hreflang_warnings.append("Missing 'x-default' fallback hreflang tag for unmatched regional users")

        if not has_self_ref and not http_res.get("is_local", False):
            hreflang_warnings.append("Missing self-referencing hreflang tag for current page URL")

        if hreflang_errors:
            builder.add_evidence(
                rule_id="TECH-HREFLANG-033",
                category="technical",
                title="International Hreflang & Regional Annotations",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed="; ".join(hreflang_errors[:3]),
                expected="Valid ISO 639-1 / ISO 3166-1 codes and absolute HTTPS URLs",
                message=f"Hreflang annotation errors detected: {'; '.join(hreflang_errors[:3])}"
            )
            builder.add_finding(
                rule_id="TECH-HREFLANG-033",
                category="technical",
                severity=STATUS_WARNING,
                title="Invalid Hreflang Annotations",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    "Fix invalid language/region codes (e.g. use en-GB instead of en-UK).",
                    "Ensure all hreflang URLs are absolute HTTPS URLs."
                ],
                impact_estimate="Search engines will ignore invalid hreflang annotations and fail to serve localized versions in regional search."
            )
        elif hreflang_warnings:
            is_only_x_default = all("x-default" in w for w in hreflang_warnings)
            hreflang_status = STATUS_INFO if is_only_x_default else STATUS_WARNING
            builder.add_evidence(
                rule_id="TECH-HREFLANG-033",
                category="technical",
                title="International Hreflang & Regional Annotations",
                status=hreflang_status,
                confidence=CONFIDENCE_VERIFIED,
                observed="; ".join(hreflang_warnings[:3]),
                expected="Valid ISO codes and absolute HTTPS URLs (x-default recommended)",
                message=f"Hreflang advisory: {'; '.join(hreflang_warnings[:3])}" if is_only_x_default else f"Hreflang warnings: {'; '.join(hreflang_warnings[:3])}"
            )
            builder.add_finding(
                rule_id="TECH-HREFLANG-033",
                category="technical",
                severity=hreflang_status,
                title="Hreflang Configuration Advisory" if is_only_x_default else "Suboptimal Hreflang Configuration",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P3_LOW" if is_only_x_default else "P2_MEDIUM",
                remediation_steps=[
                    "Consider adding an 'x-default' fallback tag for unmatched regional users." if is_only_x_default else "Add self-referencing hreflang tag and 'x-default' fallback tag to complete bi-directional hreflang matrix."
                ],
                impact_estimate="Unmatched regional users may receive arbitrary language version rather than default landing page." if is_only_x_default else "Missing self-referencing hreflang tags can lead to unpredictable regional targeting."
            )
        else:
            builder.add_evidence(
                rule_id="TECH-HREFLANG-033",
                category="technical",
                title="International Hreflang & Regional Annotations",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{hreflang_count} valid hreflang tag(s)",
                expected="Valid ISO codes, absolute URLs, and x-default",
                message="Hreflang international annotations are properly configured."
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
    if not og_data:
        builder.add_evidence(
            rule_id="SOCIAL-OG-017",
            category="technical",
            title="Open Graph Metadata",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="No Open Graph tags declared",
            expected="og:title, og:type, og:image, and og:url declared",
            message="Document lacks Open Graph metadata tags for rich social media cards across Meta (Threads/Facebook/Instagram), Telegram, and LinkedIn."
        )
    else:
        required_og = ["og:title", "og:type", "og:image", "og:url"]
        missing_required = [tag for tag in required_og if not og_data.get(tag)]
        if missing_required:
            meta_note = " Note: Meta (Threads/Facebook/Instagram) strictly requires 'og:type' to compile preview objects and monetization assets." if "og:type" in missing_required else ""
            builder.add_evidence(
                rule_id="SOCIAL-OG-017",
                category="technical",
                title="Open Graph Metadata",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Missing: {', '.join(missing_required)}",
                expected="og:title, og:type, og:image, and og:url declared",
                message=f"Incomplete Open Graph protocol configuration. Missing required tags: {', '.join(missing_required)}.{meta_note}"
            )
            builder.add_finding(
                rule_id="SOCIAL-OG-017",
                category="technical",
                severity=STATUS_WARNING,
                title="Incomplete Open Graph Protocol Metadata",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    f"Declare missing Open Graph tags in <head>: {', '.join(missing_required)}.",
                    "In Next.js, ensure child pages re-specify 'type: website' when overriding openGraph."
                ],
                impact_estimate="Meta (Threads, Instagram, Facebook) and social scrapers cannot generate rich link cards or monetization objects."
            )
        else:
            og_type_val = og_data.get("og:type")
            builder.add_evidence(
                rule_id="SOCIAL-OG-017",
                category="technical",
                title="Open Graph Metadata",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"og:title, og:type ('{og_type_val}'), og:image, and og:url present",
                expected="og:title, og:type, og:image, and og:url declared",
                message=f"Essential Open Graph metadata tags are configured (type: '{og_type_val}')."
            )

    # SOCIAL-TWITTER-032: Twitter Card Metadata
    tw_data = html_data.get("twitter_card", {})
    if not tw_data:
        builder.add_evidence(
            rule_id="SOCIAL-TWITTER-032",
            category="technical",
            title="Twitter Card Metadata",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="No Twitter Card tags declared",
            expected="twitter:card declared (e.g. summary_large_image)",
            message="Document does not declare explicit Twitter card tags; social crawlers on X/Twitter will attempt fallback to Open Graph metadata."
        )
    else:
        card_type = tw_data.get("twitter:card")
        if not card_type:
            builder.add_evidence(
                rule_id="SOCIAL-TWITTER-032",
                category="technical",
                title="Twitter Card Metadata",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed="twitter:card tag is missing",
                expected="twitter:card declared with 'summary' or 'summary_large_image'",
                message="Twitter card properties are declared, but 'twitter:card' is missing. Rich previews on X/Twitter cannot render without a valid card type."
            )
            builder.add_finding(
                rule_id="SOCIAL-TWITTER-032",
                category="technical",
                severity=STATUS_WARNING,
                title="Twitter Card Type Tag Missing",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=["Add <meta name='twitter:card' content='summary_large_image'> to <head>."],
                impact_estimate="X/Twitter cannot render rich summary cards without an explicit twitter:card tag."
            )
        else:
            builder.add_evidence(
                rule_id="SOCIAL-TWITTER-032",
                category="technical",
                title="Twitter Card Metadata",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"twitter:card='{card_type}' present",
                expected="twitter:card declared",
                message=f"Twitter Card metadata is configured with card type '{card_type}'."
            )

    # SOCIAL-PREVIEW-SYNC-033: Social Preview Parity & Metadata Consistency
    # Prevents Next.js / meta-framework root layout inheritance bugs where
    # twitter:title defaults to site brand while og:title has the page-specific title,
    # causing Telegram, Discord, and X previews to display generic homepage titles.
    og_title = (og_data.get("og:title") or "").strip() if og_data else ""
    tw_title = (tw_data.get("twitter:title") or "").strip() if tw_data else ""
    og_desc = (og_data.get("og:description") or "").strip() if og_data else ""
    tw_desc = (tw_data.get("twitter:description") or "").strip() if tw_data else ""
    og_site_name = (og_data.get("og:site_name") or "").strip() if og_data else ""
    tw_card_type = (tw_data.get("twitter:card") or "").strip() if tw_data else ""
    page_h1_list = html_data.get("headings", {}).get("h1_values", [])
    first_h1 = page_h1_list[0].strip() if page_h1_list else ""

    if not og_title and not tw_title:
        builder.add_evidence(
            rule_id="SOCIAL-PREVIEW-SYNC-033",
            category="technical",
            title="Social Preview Parity",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="No Open Graph or Twitter title tags declared",
            expected="Synchronized og:title and twitter:title across social tags",
            message="Document does not declare social card title tags; social preview parity cannot be evaluated."
        )
    elif og_title and not tw_title:
        if tw_card_type:
            builder.add_evidence(
                rule_id="SOCIAL-PREVIEW-SYNC-033",
                category="technical",
                title="Social Preview Parity",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"og:title='{og_title}', twitter:card='{tw_card_type}' (no conflicting twitter:title)",
                expected="Synchronized or fallback-safe social metadata",
                message=f"Document relies on Open Graph fallback for Twitter card ('{og_title}'). No conflicting twitter:title detected."
            )
        else:
            builder.add_evidence(
                rule_id="SOCIAL-PREVIEW-SYNC-033",
                category="technical",
                title="Social Preview Parity",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"og:title='{og_title}' present",
                expected="Open Graph metadata present",
                message=f"Open Graph title declared ('{og_title}'). Social crawlers will render this title cleanly."
            )
    elif tw_title and not og_title:
        builder.add_evidence(
            rule_id="SOCIAL-PREVIEW-SYNC-033",
            category="technical",
            title="Social Preview Parity",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"twitter:title='{tw_title}' present but og:title is missing",
            expected="Both og:title and twitter:title declared or og:title provided for standard Open Graph crawlers",
            message="Document declares 'twitter:title' without 'og:title'. Non-Twitter crawlers (Facebook, LinkedIn, Slack) will lack a title."
        )
        builder.add_finding(
            rule_id="SOCIAL-PREVIEW-SYNC-033",
            category="technical",
            severity=STATUS_WARNING,
            title="Missing og:title for Social Preview Parity",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=[
                f"Add <meta property='og:title' content='{tw_title}'> to <head> to ensure non-Twitter social crawlers display a rich title."
            ],
            impact_estimate="Facebook, LinkedIn, and Slack scrapers rely on og:title and may display raw URLs without it."
        )
    else:
        # Both og_title and tw_title are present! Check for divergence / conflict
        def _extract_core_title(t: str) -> str:
            for sep in [" | ", " — ", " - ", " · "]:
                if sep in t:
                    return t.split(sep)[0].strip()
            return t.strip()

        core_og = _extract_core_title(og_title)
        core_tw = _extract_core_title(tw_title)
        titles_match = (og_title == tw_title)
        brand_variant = (core_og.lower() == core_tw.lower() and len(core_og) > 0)

        # Check for classic Next.js layout inheritance trap:
        # twitter:title matches site_name or generic brand while og:title has page-specific title
        is_site_name_fallback = False
        if og_site_name:
            if tw_title.lower() == og_site_name.lower() and og_title.lower() != og_site_name.lower():
                is_site_name_fallback = True
            elif core_tw.lower() == og_site_name.lower() and core_og.lower() != og_site_name.lower():
                is_site_name_fallback = True

        if not titles_match and not brand_variant:
            diag_reason = (
                f"Root layout inheritance conflict: 'twitter:title' equals site name '{og_site_name}' while 'og:title' has page title '{og_title}'."
                if is_site_name_fallback else
                f"'og:title' ('{og_title}') and 'twitter:title' ('{tw_title}') are in direct conflict."
            )
            builder.add_evidence(
                rule_id="SOCIAL-PREVIEW-SYNC-033",
                category="technical",
                title="Social Preview Metadata Parity",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Conflict: og:title='{og_title}' vs twitter:title='{tw_title}'",
                expected="Synchronized og:title and twitter:title",
                message=f"Conflicting social title tags detected. {diag_reason} Telegram, Discord, and X prioritize 'twitter:title' when 'twitter:card' is present, rendering '{tw_title}' instead of '{og_title}'."
            )
            builder.add_finding(
                rule_id="SOCIAL-PREVIEW-SYNC-033",
                category="technical",
                severity=STATUS_WARNING,
                title="Social Preview Metadata Mismatch (og:title vs twitter:title)",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P1_HIGH",
                remediation_steps=[
                    f"Update <meta name='twitter:title' content='{og_title}'> to match <meta property='og:title'>.",
                    "In Next.js, export child page 'twitter: { title: ... }' alongside 'openGraph' to prevent root layout twitter inheritance from overriding link previews."
                ],
                impact_estimate="Social messengers (Telegram, Discord) and X will display generic or conflicting titles instead of the specific page topic."
            )
        elif og_desc and tw_desc and og_desc != tw_desc:
            builder.add_evidence(
                rule_id="SOCIAL-PREVIEW-SYNC-033",
                category="technical",
                title="Social Preview Metadata Parity",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed="Title parity OK, but description divergence detected",
                expected="Synchronized og:description and twitter:description",
                message=f"Social descriptions diverge: og:description ('{og_desc[:50]}...') vs twitter:description ('{tw_desc[:50]}...'). Social link previews will show differing descriptions across platforms."
            )
            builder.add_finding(
                rule_id="SOCIAL-PREVIEW-SYNC-033",
                category="technical",
                severity=STATUS_WARNING,
                title="Social Description Metadata Divergence",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    "Align <meta name='twitter:description'> with <meta property='og:description'> on child routes."
                ],
                impact_estimate="Previews across Telegram, Discord, and X may show inconsistent snippet descriptions."
            )
        else:
            if og_site_name and og_title.lower() == og_site_name.lower() and first_h1 and first_h1.lower() != og_site_name.lower():
                builder.add_evidence(
                    rule_id="SOCIAL-PREVIEW-SYNC-033",
                    category="technical",
                    title="Social Preview Metadata Parity",
                    status=STATUS_WARNING,
                    confidence=CONFIDENCE_VERIFIED,
                    observed=f"og:title and twitter:title equal site_name ('{og_site_name}') on deep page with H1='{first_h1}'",
                    expected=f"Page-specific social title matching H1 ('{first_h1}') rather than generic site name",
                    message=f"Deep page uses generic site name '{og_site_name}' as social preview title instead of page topic '{first_h1}'."
                )
                builder.add_finding(
                    rule_id="SOCIAL-PREVIEW-SYNC-033",
                    category="technical",
                    severity=STATUS_WARNING,
                    title="Generic Site Title on Deep Page Social Preview",
                    confidence=CONFIDENCE_VERIFIED,
                    action_priority="P1_HIGH",
                    remediation_steps=[
                        f"Set og:title and twitter:title to reflect the page content (e.g. '{first_h1} | {og_site_name}').",
                        "In Next.js, define page-level metadata on inner page routes."
                    ],
                    impact_estimate="Social shares of this page will only display the brand name without indicating what the page is about."
                )
            else:
                builder.add_evidence(
                    rule_id="SOCIAL-PREVIEW-SYNC-033",
                    category="technical",
                    title="Social Preview Metadata Parity",
                    status=STATUS_PASS,
                    confidence=CONFIDENCE_VERIFIED,
                    observed=f"og:title and twitter:title synchronized ('{tw_title}')",
                    expected="Synchronized og:title and twitter:title",
                    message="Open Graph and Twitter Card metadata are synchronized, ensuring consistent link previews across Telegram, Discord, X, and LinkedIn."
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
        if cf.rule_id in ("CONTENT-DATE-VISIBLE-005", "CONTENT-QUESTION-HEADINGS-002", "CONTENT-EXTRACTABLE-003", "CONTENT-TEXT-RATIO-004"):
            continue
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

    # PERFORMANCE EVIDENCE
    dom_findings = [f for f in perf_data.findings if f.rule_id == "PERF-DOM-005"]
    if dom_findings:
        builder.add_evidence(
            rule_id="PERF-DOM-005",
            category="performance",
            title="DOM Size and Tree Nesting Depth",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=dom_findings[0].message,
            expected="<= 1500 nodes, <= 32 depth, <= 50 scripts",
            message=dom_findings[0].message
        )
        builder.add_finding(
            rule_id="PERF-DOM-005",
            category="performance",
            severity=STATUS_WARNING,
            title="Excessive DOM Tree Complexity",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=dom_findings[0].remediation_steps,
            impact_estimate=dom_findings[0].impact_estimate
        )
    else:
        builder.add_evidence(
            rule_id="PERF-DOM-005",
            category="performance",
            title="DOM Size and Tree Nesting Depth",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{perf_data.dom_nodes_count} nodes, max depth {perf_data.max_dom_depth}, {perf_data.script_tags_count} scripts",
            expected="<= 1500 nodes and <= 32 depth",
            message="DOM tree complexity is within optimal bounds."
        )

    rb_findings = [f for f in perf_data.findings if f.rule_id == "PERF-RENDER-BLOCK-003"]
    if rb_findings:
        builder.add_evidence(
            rule_id="PERF-RENDER-BLOCK-003",
            category="performance",
            title="Render-Blocking CSS and Synchronous JavaScript",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=rb_findings[0].message,
            expected="Asynchronous non-critical styles and scripts",
            message=rb_findings[0].message
        )
        builder.add_finding(
            rule_id="PERF-RENDER-BLOCK-003",
            category="performance",
            severity=STATUS_WARNING,
            title="Render-Blocking Assets in <head>",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=rb_findings[0].remediation_steps,
            impact_estimate=rb_findings[0].impact_estimate
        )
    else:
        builder.add_evidence(
            rule_id="PERF-RENDER-BLOCK-003",
            category="performance",
            title="Render-Blocking CSS and Synchronous JavaScript",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="0 render-blocking assets in <head>",
            expected="Asynchronous non-critical styles and scripts",
            message="No render-blocking scripts or non-print stylesheets detected in <head>."
        )

    hint_lazy = next((f for f in perf_data.findings if f.rule_id == "PERF-RESOURCE-HINTS-006" and f.severity == STATUS_WARNING), None)
    if hint_lazy:
        builder.add_evidence(
            rule_id="PERF-RESOURCE-HINTS-006",
            category="performance",
            title="Resource Hints and LCP Priority Optimization",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=hint_lazy.message,
            expected="Eager high-priority loading for hero image",
            message=hint_lazy.message
        )
        builder.add_finding(
            rule_id="PERF-RESOURCE-HINTS-006",
            category="performance",
            severity=STATUS_WARNING,
            title=hint_lazy.title,
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P1_HIGH",
            remediation_steps=hint_lazy.remediation_steps,
            impact_estimate=hint_lazy.impact_estimate
        )
    else:
        builder.add_evidence(
            rule_id="PERF-RESOURCE-HINTS-006",
            category="performance",
            title="Resource Hints and LCP Priority Optimization",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{len(perf_data.resource_hints)} resource hint(s)",
            expected="Optimized above-the-fold image delivery",
            message="Above-the-fold image delivery is optimized without lazy-load anti-patterns."
        )

    img_mod_finding = next((f for f in perf_data.findings if f.rule_id == "TECH-IMAGE-MODERN-038"), None)
    if img_mod_finding:
        builder.add_evidence(
            rule_id="TECH-IMAGE-MODERN-038",
            category="technical",
            title="Modern Image Formats (WebP / AVIF)",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=img_mod_finding.message,
            expected="Next-gen WebP/AVIF format utilization",
            message=img_mod_finding.message
        )
        builder.add_finding(
            rule_id="TECH-IMAGE-MODERN-038",
            category="technical",
            severity=STATUS_WARNING,
            title=img_mod_finding.title,
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=img_mod_finding.remediation_steps,
            impact_estimate=img_mod_finding.impact_estimate
        )
    else:
        builder.add_evidence(
            rule_id="TECH-IMAGE-MODERN-038",
            category="technical",
            title="Modern Image Formats (WebP / AVIF)",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{perf_data.image_formats.get('modern', 0)} modern image(s)",
            expected="Modern format utilization or compact asset count",
            message="Image assets leverage modern compressed formats or document is compact."
        )

    # TECH-ROBOTS-SITEMAP-034
    if robots_ast:
        if len(robots_ast.sitemaps) == 0:
            builder.add_evidence(
                rule_id="TECH-ROBOTS-SITEMAP-034",
                category="technical",
                title="XML Sitemap Declaration in robots.txt",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed="0 Sitemap directives declared in robots.txt",
                expected="At least 1 Sitemap: directive",
                message="robots.txt lacks a Sitemap: directive pointing search crawlers to the sitemap index."
            )
            builder.add_finding(
                rule_id="TECH-ROBOTS-SITEMAP-034",
                category="technical",
                severity=STATUS_WARNING,
                title="Missing Sitemap Directive in robots.txt",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=["Add 'Sitemap: https://example.com/sitemap.xml' to the end of robots.txt."],
                impact_estimate="Search crawlers take longer to discover new content and taxonomy changes."
            )
        else:
            builder.add_evidence(
                rule_id="TECH-ROBOTS-SITEMAP-034",
                category="technical",
                title="XML Sitemap Declaration in robots.txt",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{len(robots_ast.sitemaps)} sitemap directive(s) declared",
                expected="At least 1 Sitemap: directive",
                message=f"robots.txt declares sitemap(s): {', '.join(robots_ast.sitemaps[:2])}."
            )

    # TECH-URL-STRUCTURE-037
    if not http_res.get("is_local", False) and final_url.startswith(("http://", "https://")):
        parsed_u = urlparse(final_url)
        u_path = parsed_u.path or "/"
        u_query = parsed_u.query or ""
        u_issues = []
        if any(c.isupper() for c in u_path):
            u_issues.append("Uppercase characters in URL path")
        if "_" in u_path:
            u_issues.append("Underscores in URL path instead of hyphens")
        q_parts = [qp.split("=")[0].lower() for qp in u_query.split("&") if qp]
        if any(sid in q_parts for sid in ("sid", "phpsessid", "jsessionid", "aspsessionid")):
            u_issues.append("Session ID in query parameters")
        if len(q_parts) > 3:
            u_issues.append(f"Excessive query parameters ({len(q_parts)} > 3)")
        path_segs = [s for s in u_path.split("/") if s]
        if len(path_segs) > 4:
            u_issues.append(f"Excessive directory depth ({len(path_segs)} levels > 4)")
        if u_issues:
            builder.add_evidence(
                rule_id="TECH-URL-STRUCTURE-037",
                category="technical",
                title="Clean URL Structure & Parameter Hygiene",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed="; ".join(u_issues),
                expected="Lowercase alphanumeric paths with hyphens and <=3 query parameters",
                message=f"URL structure irregularities detected: {'; '.join(u_issues)}."
            )
            builder.add_finding(
                rule_id="TECH-URL-STRUCTURE-037",
                category="technical",
                severity=STATUS_WARNING,
                title="Suboptimal URL Structure",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    "Use lowercase alphanumeric characters separated by hyphens.",
                    "Eliminate session parameters and minimize query parameters."
                ],
                impact_estimate="Poor readability, crawling overhead, and potential duplicate content."
            )
        else:
            builder.add_evidence(
                rule_id="TECH-URL-STRUCTURE-037",
                category="technical",
                title="Clean URL Structure & Parameter Hygiene",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Clean URL structure (depth {len(path_segs)})",
                expected="Lowercase alphanumeric paths with hyphens",
                message="URL conforms to search engine best practices."
            )
    else:
        builder.add_evidence(
            rule_id="TECH-URL-STRUCTURE-037",
            category="technical",
            title="Clean URL Structure & Parameter Hygiene",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="Clean URL structure",
            expected="Clean URL structure",
            message="URL structure check evaluated cleanly."
        )

    # CONTENT-TITLE-QUALITY-001
    title_dict = html_data.get("title", {})
    t_val = title_dict.get("value", "")
    p_width = title_dict.get("pixel_width", 0)
    h1_vals = html_data.get("headings", {}).get("h1_values", [])
    first_h1 = h1_vals[0].strip() if h1_vals else ""
    t_issues = []
    if t_val and first_h1 and t_val.strip().lower() == first_h1.strip().lower() and len(t_val.split()) > 2:
        t_issues.append("Title and H1 are verbatim identical")
    if p_width > 580:
        t_issues.append(f"Title pixel width ({p_width}px) exceeds 580px desktop SERP limit")
    if t_issues:
        builder.add_evidence(
            rule_id="CONTENT-TITLE-QUALITY-001",
            category="technical",
            title="Title Pixel Width & Snippet Formatting",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed="; ".join(t_issues),
            expected="Width <= 580px and distinct from H1",
            message=f"Title snippet optimization issue: {'; '.join(t_issues)}."
        )
        builder.add_finding(
            rule_id="CONTENT-TITLE-QUALITY-001",
            category="technical",
            severity=STATUS_WARNING,
            title="Title Snippet Truncation or Duplication",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=[
                "Format title to under 580px in desktop Google SERP.",
                "Ensure <title> and H1 have distinct nuances rather than identical copy."
            ],
            impact_estimate="Google SERP truncates long titles with ellipses (...) or rewrites them non-deterministically."
        )
    else:
        builder.add_evidence(
            rule_id="CONTENT-TITLE-QUALITY-001",
            category="technical",
            title="Title Pixel Width & Snippet Formatting",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{p_width}px (~580px desktop limit), distinct from H1",
            expected="Width <= 580px and distinct from H1",
            message="Title is well-proportioned for Google desktop search snippets."
        )

    # CONTENT-QUESTION-HEADINGS-002
    q_cnt = content_data.question_headings_count
    ans_cnt = content_data.question_answers_count
    if q_cnt > 0:
        builder.add_evidence(
            rule_id="CONTENT-QUESTION-HEADINGS-002",
            category="technical",
            title="Question Headings & Direct Answer Architecture",
            status=STATUS_PASS if ans_cnt > 0 else STATUS_INFO,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{q_cnt} question heading(s), {ans_cnt} direct answer block(s)",
            expected="Question headings followed by direct 40–60 word answer passages",
            message=f"Content declares {q_cnt} question headings with {ans_cnt} direct answer blocks for PAA/AEO extraction."
        )
    else:
        builder.add_evidence(
            rule_id="CONTENT-QUESTION-HEADINGS-002",
            category="technical",
            title="Question Headings & Direct Answer Architecture",
            status=STATUS_INFO,
            confidence=CONFIDENCE_HEURISTIC,
            observed="0 question headings declared",
            expected="Optional question-style subheadings for PAA/AEO",
            message="No question-style headings (What/How/Why) declared. Consider structuring FAQ sections for PAA inclusion."
        )

    # CONTENT-EXTRACTABLE-003
    extr = html_data.get("extractable_elements", {})
    tb_c = extr.get("tables_count", 0)
    li_c = extr.get("lists_count", 0)
    tldr_c = extr.get("tldr_blocks_count", 0)
    has_extr = (tb_c > 0 or li_c > 0 or tldr_c > 0 or extr.get("definition_lists_count", 0) > 0)
    if has_extr:
        builder.add_evidence(
            rule_id="CONTENT-EXTRACTABLE-003",
            category="technical",
            title="Structured Extractable Elements (Tables, Lists, TL;DR)",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"Tables: {tb_c}, Lists: {li_c}, TL;DR: {tldr_c}",
            expected="Structured tables, bulleted lists, or summary callout boxes",
            message="Document provides structured extractable elements that generative engines favor for direct citations."
        )
    elif content_data.total_words >= 300:
        builder.add_evidence(
            rule_id="CONTENT-EXTRACTABLE-003",
            category="technical",
            title="Structured Extractable Elements (Tables, Lists, TL;DR)",
            status=STATUS_INFO,
            confidence=CONFIDENCE_HEURISTIC,
            observed="No comparison tables, structured lists, or TL;DR callouts",
            expected="Structured tables, bulleted lists, or summary callout boxes",
            message="Longer content document lacks structured tables or bulleted lists that AI engines extract for synthesis."
        )
    else:
        builder.add_evidence(
            rule_id="CONTENT-EXTRACTABLE-003",
            category="technical",
            title="Structured Extractable Elements (Tables, Lists, TL;DR)",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed="Compact document",
            expected="Structured elements",
            message="Compact page format."
        )

    # CONTENT-TEXT-RATIO-004
    c_rat = html_data.get("content_ratio", {})
    r_val = c_rat.get("ratio", 1.0)
    tot_w = c_rat.get("total_words", 0)
    if tot_w >= 300 and r_val < 0.20:
        builder.add_evidence(
            rule_id="CONTENT-TEXT-RATIO-004",
            category="technical",
            title="Content-to-Boilerplate Ratio (Thin Template Guard)",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"Substantive content ratio: {int(r_val*100)}% (< 20%)",
            expected="Substantive main content >= 20% of total page words",
            message=f"Page is dominated by header/nav/footer boilerplate ({int(r_val*100)}% substantive main text)."
        )
        builder.add_finding(
            rule_id="CONTENT-TEXT-RATIO-004",
            category="technical",
            severity=STATUS_WARNING,
            title="Low Substantive Content-to-Boilerplate Ratio",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Expand main body content or streamline redundant header, footer, and navigation boilerplate."],
            impact_estimate="Search crawlers classify low-content-ratio pages as thin templates with reduced indexing priority."
        )
    else:
        builder.add_evidence(
            rule_id="CONTENT-TEXT-RATIO-004",
            category="technical",
            title="Content-to-Boilerplate Ratio (Thin Template Guard)",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"Substantive content ratio: {int(r_val*100)}%",
            expected="Substantive main content >= 20%",
            message="Content-to-boilerplate ratio is healthy."
        )

    # CONTENT-DATE-VISIBLE-005
    date_finding = next((f for f in content_data.findings if f.rule_id == "CONTENT-DATE-VISIBLE-005"), None)
    if date_finding:
        builder.add_evidence(
            rule_id="CONTENT-DATE-VISIBLE-005",
            category="technical",
            title="Schema Date Visible Rendering Parity",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=date_finding.message,
            expected="Schema publication/modification dates visibly rendered in document body",
            message=date_finding.message
        )
        builder.add_finding(
            rule_id="CONTENT-DATE-VISIBLE-005",
            category="technical",
            severity=STATUS_WARNING,
            title="Schema Date Not Rendered in Visible HTML",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Add a visible byline date (e.g. 'Updated: [Date]') to ensure parity with Schema JSON-LD."],
            impact_estimate="Google search spam guidelines penalize misleading metadata that contradicts visible content."
        )
    else:
        builder.add_evidence(
            rule_id="CONTENT-DATE-VISIBLE-005",
            category="technical",
            title="Schema Date Visible Rendering Parity",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="Schema date consistent with visible HTML text or unassigned",
            expected="Visible publication date parity",
            message="Schema dates align with human-visible document bylines."
        )

    # GEO-PAWC-SCORE-001
    pawc_obj = content_data.pawc
    if pawc_obj.score >= 50 or content_data.total_words < 25:
        builder.add_evidence(
            rule_id="GEO-PAWC-SCORE-001",
            category="geo",
            title="Position-Adjusted Word Weighting (PAWC)",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"PAWC Score: {pawc_obj.score}/100 (opening weight: {pawc_obj.opening_evidence_weight}, heading weight: {pawc_obj.heading_answer_weight})",
            expected="PAWC score >= 50/100 with evidence frontloading",
            message="Document successfully frontloads factual definitions and metrics before exponential position decay."
        )
    elif pawc_obj.score >= 30:
        builder.add_evidence(
            rule_id="GEO-PAWC-SCORE-001",
            category="geo",
            title="Position-Adjusted Word Weighting (PAWC)",
            status=STATUS_INFO,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"PAWC Score: {pawc_obj.score}/100 (moderate frontloading)",
            expected="PAWC score >= 50/100",
            message="Document has moderate evidence frontloading. Advancing key definitions to the first 60 words will increase LLM citation probability."
        )
    else:
        builder.add_evidence(
            rule_id="GEO-PAWC-SCORE-001",
            category="geo",
            title="Position-Adjusted Word Weighting (PAWC)",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"PAWC Score: {pawc_obj.score}/100 (low early evidence density)",
            expected="PAWC score >= 50/100",
            message="Key claims and factual definitions are buried deep in the document, succumbing to exponential citation decay."
        )
        builder.add_finding(
            rule_id="GEO-PAWC-SCORE-001",
            category="geo",
            severity=STATUS_WARNING,
            title="Low PAWC Evidence Frontloading Score",
            confidence=CONFIDENCE_HEURISTIC,
            action_priority="P1_HIGH",
            remediation_steps=[
                "State core definition in the opening sentence: '[Topic] is [category] designed to [function]'.",
                "Lead sub-sections with verifiable quantitative metrics before narrative background."
            ],
            impact_estimate="Generative answer engines (ChatGPT, Perplexity) extract earlier sentences; delayed definitions are omitted from synthesis."
        )

    # GEO-LLMS-TXT-CHECK-006
    if llms_res:
        if llms_res.is_valid:
            builder.add_evidence(
                rule_id="GEO-LLMS-TXT-CHECK-006",
                category="geo",
                title="/llms.txt AI Context File & Syntax Compliance",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Valid /llms.txt ('{llms_res.title}', {llms_res.links_count} links)",
                expected="Valid /llms.txt with H1, blockquote summary, and documentation links",
                message=f"Website declares standard-compliant /llms.txt for autonomous agent traversal ({llms_res.links_count} links)."
            )
        elif llms_res.is_present:
            builder.add_evidence(
                rule_id="GEO-LLMS-TXT-CHECK-006",
                category="geo",
                title="/llms.txt AI Context File & Syntax Compliance",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"/llms.txt present but invalid: {'; '.join(llms_res.validation_errors[:2])}",
                expected="Valid /llms.txt structure",
                message=f"/llms.txt syntax errors: {'; '.join(llms_res.validation_errors)}."
            )
            builder.add_finding(
                rule_id="GEO-LLMS-TXT-CHECK-006",
                category="geo",
                severity=STATUS_WARNING,
                title="Invalid /llms.txt Syntax",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=["Ensure /llms.txt begins with '# Project Title' and a blockquote '> Summary'."],
                impact_estimate="Autonomous LLM agents fail to parse website overview and documentation links."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-LLMS-TXT-CHECK-006",
                category="geo",
                title="/llms.txt AI Context File & Syntax Compliance",
                status=STATUS_INFO,
                confidence=CONFIDENCE_VERIFIED,
                observed="No /llms.txt found at website root",
                expected="Optional /llms.txt specification",
                message="Website does not publish /llms.txt. Creating one per Answer.AI specification accelerates LLM agent comprehension."
            )
    else:
        builder.add_evidence(
            rule_id="GEO-LLMS-TXT-CHECK-006",
            category="geo",
            title="/llms.txt AI Context File & Syntax Compliance",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="Local file inspection or unprobed /llms.txt",
            expected="N/A",
            message="Local inspection mode; remote /llms.txt probe skipped."
        )

    # GEO-LLMS-FULL-020: llms-full.txt companion check
    if llms_res and llms_res.is_valid and not http_res["is_local"]:
        _llms_full = check_llms_full_txt(final_url, timeout=min(3.0, timeout))
        if _llms_full.get("is_present"):
            builder.add_evidence(
                rule_id="GEO-LLMS-FULL-020",
                category="geo",
                title="/llms-full.txt Full-Content Companion",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"/llms-full.txt present ({_llms_full.get('word_count', 0)} words, {_llms_full.get('size_bytes', 0)} bytes)",
                expected="Full-content companion for direct LLM context loading",
                message="Site publishes the full-content dump, enabling one-shot context loading for agents."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-LLMS-FULL-020",
                category="geo",
                title="/llms-full.txt Full-Content Companion",
                status=STATUS_INFO,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"/llms-full.txt not found (HTTP {_llms_full.get('status_code')})",
                expected="Full-content companion for direct LLM context loading",
                message="llms.txt exists without its full-content companion; agents must crawl linked pages individually."
            )

    # GEO-WAF-BOT-ACCESS-021: edge/WAF AI-bot accessibility probe (remote only)
    if (not http_res["is_local"] and final_url.startswith(("http://", "https://"))
            and http_res.get("status_code") == 200
            and not _bot_challenge_signature(http_res.get("status_code", 0), http_res.get("headers", {}), str(http_res.get("raw_content", "")))):
        _probe_uas = ("GPTBot", "PerplexityBot", "ClaudeBot", "Google-Extended", "YandexRenderResourcesBot")
        _probe_results: Dict[str, Dict[str, Any]] = {}
        for _ua in _probe_uas:
            try:
                _pr = analyze_target_http(final_url, timeout=min(5.0, timeout),
                                          user_agent=f"Mozilla/5.0 (compatible; {_ua}/1.0; +https://github.com/Ezhuk1/ultimate-seo-geo)")
                _sig = _bot_challenge_signature(_pr.get("status_code", 0), _pr.get("headers", {}),
                                                str(_pr.get("raw_content", "")))
                _probe_results[_ua] = {"status": _pr.get("status_code"), "challenge": _sig}
            except Exception as _pe:
                _probe_results[_ua] = {"status": None, "challenge": None, "error": str(_pe)[:80]}
        _blocked_search = [u for u in ("GPTBot", "PerplexityBot", "ClaudeBot") if _probe_results.get(u, {}).get("challenge")]
        _blocked_any = [u for u, v in _probe_results.items() if v.get("challenge")]
        _probe_observed = "; ".join(f"{u}: {v['status']}" + (f" ({v['challenge']})" if v.get("challenge") else "")
                                    for u, v in _probe_results.items())
        if _blocked_search:
            builder.add_evidence(
                rule_id="GEO-WAF-BOT-ACCESS-021",
                category="geo",
                title="Edge/WAF AI-Bot Accessibility Probe",
                status=STATUS_CRITICAL,
                confidence=CONFIDENCE_VERIFIED,
                observed=_probe_observed,
                expected="Search-retrieval AI bots receive the same 200 HTML as browsers",
                message="Edge WAF (Cloudflare/CloudFront/Qrator/Fastly) silently challenges or blocks AI search crawlers despite robots.txt allowing them — the site is invisible in AI answers."
            )
            builder.add_finding(
                rule_id="GEO-WAF-BOT-ACCESS-021",
                category="geo",
                severity=STATUS_CRITICAL,
                title="Edge WAF Blocks AI Search Crawlers (Managed Challenge)",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P0_BLOCKER",
                remediation_steps=[
                    "Cloudflare: Security -> WAF -> Custom rules — create rule: (cf.client.bot) or User Agent contains 'GPTBot' or 'PerplexityBot' or 'ClaudeBot' -> Action: Skip (all managed challenges).",
                    "Nginx: map $http_user_agent $ai_bot { default 0; ~*(GPTBot|PerplexityBot|ClaudeBot|Google-Extended) 1; } server { if ($ai_bot) { set $skip_challenge 1; } } — and exclude them from rate-limit/challenge zones.",
                    "Caddy: @aibots header User-Agent *GPTBot* / *PerplexityBot* / *ClaudeBot* — invoke @aibots before any bot-protection directive.",
                    "Verify after deploy: curl -A 'Mozilla/5.0 (compatible; GPTBot/1.0)' -I https://your.site/ must return 200 without challenge markers."
                ],
                impact_estimate="robots.txt permits these bots, but the WAF answer means zero citations in ChatGPT/Perplexity/Claude search products."
            )
        elif _blocked_any:
            builder.add_evidence(
                rule_id="GEO-WAF-BOT-ACCESS-021",
                category="geo",
                title="Edge/WAF AI-Bot Accessibility Probe",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=_probe_observed,
                expected="AI crawlers receive real content instead of challenges",
                message="Edge WAF challenges AI crawlers (training/user-fetch tier). Search retrieval is unaffected, but training-tier visibility is lost."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-WAF-BOT-ACCESS-021",
                category="geo",
                title="Edge/WAF AI-Bot Accessibility Probe",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=_probe_observed,
                expected="AI crawlers receive real content instead of challenges",
                message="Edge/WAF layer serves AI crawlers real content (no Managed Challenge detected)."
            )

    # GEO-CSR-FALLBACK-022: fallback content for non-rendering crawlers
    try:
        _ns = html_data.get("noscript", {}) or {}
        _ns_words = int(_ns.get("total_words", 0) or 0)
        _csr_risk = bool(html_data.get("is_csr_shell")) or len(html_data.get("render_blocking_js", []) or []) > 3
        if _csr_risk and _ns_words >= 30:
            builder.add_evidence(
                rule_id="GEO-CSR-FALLBACK-022",
                category="geo",
                title="CSR Fallback Content (Non-Rendering Crawlers)",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"JS-heavy page with <noscript> fallback ({_ns_words} words)",
                expected="Meaningful <noscript> or server-side skeleton for critical sections",
                message="Page is JS-heavy but provides a noscript fallback, so non-rendering AI crawlers still see key content."
            )
        elif _csr_risk:
            builder.add_evidence(
                rule_id="GEO-CSR-FALLBACK-022",
                category="geo",
                title="CSR Fallback Content (Non-Rendering Crawlers)",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"JS-heavy page, <noscript> fallback {_ns_words} words (need >= 30)",
                expected="Meaningful <noscript> or server-side skeleton for critical sections",
                message="Client-rendered page offers no meaningful fallback: bots without JS rendering (GPTBot, ClaudeBot, PerplexityBot) see an empty shell."
            )
            builder.add_finding(
                rule_id="GEO-CSR-FALLBACK-022",
                category="geo",
                severity=STATUS_WARNING,
                title="No Meaningful Fallback Content for Non-Rendering Crawlers",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P1_HIGH",
                remediation_steps=[
                    "Add a <noscript> block duplicating the critical above-the-fold content (price, key specs, main answer).",
                    "Prefer SSR/SSG for the main content; hydrate interactivity only.",
                    "Keep the initial HTML self-sufficient: title, h1, key sections present without JS."
                ],
                impact_estimate="Non-rendering AI crawlers index an empty page; the URL cannot be cited."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-CSR-FALLBACK-022",
                category="geo",
                title="CSR Fallback Content (Non-Rendering Crawlers)",
                status=STATUS_INFO,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Server-rendered page (noscript blocks: {_ns.get('count', 0)})",
                expected="N/A for server-rendered pages",
                message="Page does not rely on client-side rendering; fallback content is not required."
            )
    except Exception:
        pass

    # GEO-ANCHOR-DEEPLINK-023: heading/table anchors for citation deep links
    try:
        _outline = html_data["headings"].get("outline", [])
        _h23 = [h for h in _outline if int(h.get("level", 9)) in (2, 3)]
        _anchored = [h for h in _h23 if h.get("id")]
        _h23n = len(_h23)
        _ratio = round(len(_anchored) / _h23n * 100.0, 1) if _h23n else None
        if _h23n >= 5 and _ratio == 0.0:
            builder.add_evidence(
                rule_id="GEO-ANCHOR-DEEPLINK-023",
                category="geo",
                title="Citation Deep-Link Anchors (id on Headings)",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"0 of {_h23n} H2/H3 headings have id anchors",
                expected="Unique id attributes on headings and key tables for #fragment and #:~:text= citations",
                message="AI answers cannot deep-link into this page: no heading anchors exist for fragment citations."
            )
            builder.add_finding(
                rule_id="GEO-ANCHOR-DEEPLINK-023",
                category="geo",
                severity=STATUS_WARNING,
                title="No Deep-Link Anchors for Citation Fragments",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    "Give every H2/H3 a stable unique id attribute matching its topic (e.g. <h2 id='pricing'>).",
                    "Add id attributes to comparison tables and FAQ entries.",
                    "Keep ids stable across releases — they become citation addresses in AI answers."
                ],
                impact_estimate="Answers citing the page cannot link to the specific block, losing verification traffic and trust signals."
            )
        elif _h23n:
            builder.add_evidence(
                rule_id="GEO-ANCHOR-DEEPLINK-023",
                category="geo",
                title="Citation Deep-Link Anchors (id on Headings)",
                status=STATUS_PASS if (_ratio or 0) >= 70.0 else STATUS_INFO,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"{len(_anchored)}/{_h23n} H2/H3 headings carry id anchors ({_ratio}%)",
                expected=">= 70% of headings anchored",
                message="Deep-link anchors allow AI engines to cite specific blocks via fragment identifiers."
            )
    except Exception:
        pass

    # GEO-AI-BOT-POLICY-007
    if robots_sim:
        blocked_search_bots = []
        for b_name in ("OAI-SearchBot", "PerplexityBot", "Claude-SearchBot"):
            b_info = robots_sim.get(b_name, {})
            if not b_info.get("root_allowed", True) or not b_info.get("target_allowed", True):
                blocked_search_bots.append(b_name)
        if blocked_search_bots:
            builder.add_evidence(
                rule_id="GEO-AI-BOT-POLICY-007",
                category="geo",
                title="AI Search Engine Retrieval Bot Permissibility",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Blocked search retrieval crawler(s): {', '.join(blocked_search_bots)}",
                expected="Allow directives for search retrieval bots",
                message=f"robots.txt disallows search retrieval bot(s): {', '.join(blocked_search_bots)}. Site is invisible in AI search engines."
            )
            builder.add_finding(
                rule_id="GEO-AI-BOT-POLICY-007",
                category="geo",
                severity=STATUS_WARNING,
                title="Search Retrieval AI Crawlers Blocked in robots.txt",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P1_HIGH",
                remediation_steps=[
                    "Add explicit permissive directives in robots.txt:",
                    "User-agent: OAI-SearchBot\\nAllow: /\\n\\nUser-agent: PerplexityBot\\nAllow: /\\n\\nUser-agent: Claude-SearchBot\\nAllow: /"
                ],
                impact_estimate="Total exclusion from ChatGPT Search, Perplexity answer citations, and Claude search results."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-AI-BOT-POLICY-007",
                category="geo",
                title="AI Search Engine Retrieval Bot Permissibility",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed="All search retrieval bots (OAI-SearchBot, PerplexityBot, Claude-SearchBot) allowed",
                expected="Permissive search retrieval policy",
                message="Search retrieval bots have full access to index and cite site content."
            )
    else:
        builder.add_evidence(
            rule_id="GEO-AI-BOT-POLICY-007",
            category="geo",
            title="AI Search Engine Retrieval Bot Permissibility",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="Default allow policy (RFC 9309)",
            expected="Permissive search retrieval policy",
            message="No robots.txt restrictions detected; search retrieval bots allowed by default."
        )

    # GEO-SECTION-PYRAMID-024: per-section inverted pyramid for LLM chunking
    if section_pyramid.get("applicable"):
        _sp_total = section_pyramid["sections_total"]
        _sp_ratio = section_pyramid["ratio_pct"] or 0.0
        if _sp_ratio >= 70.0:
            builder.add_evidence(
                rule_id="GEO-SECTION-PYRAMID-024",
                category="geo",
                title="Inverted Pyramid per Section (LLM Chunkability)",
                status=STATUS_PASS,
                confidence=CONFIDENCE_HEURISTIC,
                observed=f"{section_pyramid['sections_frontloaded']}/{_sp_total} H2/H3 sections frontload substance (stats/definition/citation) in the first ~55 words",
                expected=">= 70% of sections lead with a standalone claim",
                message="Sections follow the inverted-pyramid pattern, so LLM chunks stay self-contained."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-SECTION-PYRAMID-024",
                category="geo",
                title="Inverted Pyramid per Section (LLM Chunkability)",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_HEURISTIC,
                observed=f"Only {section_pyramid['sections_frontloaded']}/{_sp_total} sections frontload substance; weak: {', '.join(section_pyramid['weak_sections'][:3]) or '—'}",
                expected=">= 70% of sections lead with a standalone claim",
                message="Sections bury the key claim below narrative background; LLM chunks start with noise and get skipped."
            )
            builder.add_finding(
                rule_id="GEO-SECTION-PYRAMID-024",
                category="geo",
                severity=STATUS_WARNING,
                title="Sections Lack Inverted-Pyramid Structure",
                confidence=CONFIDENCE_HEURISTIC,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    "Open every H2/H3 section with a standalone claim in the first 40–60 words.",
                    "Place statistics, definitions or a verdict sentence before background narrative.",
                    "Weak sections detected: " + (", ".join(section_pyramid["weak_sections"][:3]) or "—")
                ],
                impact_estimate="Perplexity/SearchGPT index 300–800-token chunks; chunks without a leading claim are dropped from synthesis."
            )

    # GEO-INFO-GAIN-025: originality triggers vs boilerplate water
    if info_gain.get("applicable"):
        _ig_triggers = info_gain["trigger_count"]
        _ig_water = info_gain["water_phrases"]
        if _ig_triggers >= 2 and not _ig_water:
            builder.add_evidence(
                rule_id="GEO-INFO-GAIN-025",
                category="geo",
                title="Information Gain (Originality Signals)",
                status=STATUS_PASS,
                confidence=CONFIDENCE_HEURISTIC,
                observed=f"Originality triggers: {info_gain['triggers'][:3]}",
                expected="First-party results, benchmarks, formulas or artifacts",
                message="Page carries first-party information AI engines cannot source elsewhere."
            )
        elif _ig_triggers == 0 and _ig_water:
            builder.add_evidence(
                rule_id="GEO-INFO-GAIN-025",
                category="geo",
                title="Information Gain (Originality Signals)",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_HEURISTIC,
                observed=f"No originality triggers; boilerplate openers: {_ig_water[:3]}",
                expected="First-party results, benchmarks, formulas or artifacts",
                message="Page adds no verifiable information beyond common knowledge and opens with boilerplate AI crawlers discard."
            )
            builder.add_finding(
                rule_id="GEO-INFO-GAIN-025",
                category="geo",
                severity=STATUS_WARNING,
                title="Low Information Gain (Boilerplate, No First-Party Signals)",
                confidence=CONFIDENCE_HEURISTIC,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    "Add first-party data: 'we tested / we measured / our telemetry shows X'.",
                    "Replace boilerplate openers (" + ", ".join(_ig_water[:2]) + ") with the main claim.",
                    "Publish at least one artifact: benchmark table, formula, dataset or annotated screenshot."
                ],
                impact_estimate="Zero-information-gain pages are de-prioritized by AI answer engines and duplicate-content filters."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-INFO-GAIN-025",
                category="geo",
                title="Information Gain (Originality Signals)",
                status=STATUS_INFO,
                confidence=CONFIDENCE_HEURISTIC,
                observed=f"Triggers: {_ig_triggers}; water: {_ig_water[:2] or '—'}",
                expected="First-party results, benchmarks, formulas or artifacts",
                message="Partial originality signals detected; more first-party data would strengthen citation eligibility."
            )

    # GEO-SLOP-DETECT-026: AI-slop phrasing density (anti-citation register)
    if slop_data.get("applicable"):
        _sl_density = slop_data.get("density_per_1000", 0.0)
        _sl_hits = slop_data.get("hit_count", 0)
        _sl_matches = slop_data.get("matches", [])
        if slop_data.get("verdict") == "HIGH":
            builder.add_evidence(
                rule_id="GEO-SLOP-DETECT-026",
                category="geo",
                title="AI Slop Density (Citation-Killer Phrasing)",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_HEURISTIC,
                observed=f"Slop density {_sl_density}/1000 words ({_sl_hits} hits): {', '.join(_sl_matches[:5])}",
                expected="Concrete, verifiable register without generated-boilerplate phrasing",
                message="Page reads as AI-generated boilerplate: unsupported superlatives, hype verbs and corporate filler erode the trust synthesis engines place in a passage."
            )
            builder.add_finding(
                rule_id="GEO-SLOP-DETECT-026",
                category="geo",
                severity=STATUS_WARNING,
                title="High AI-Slop Density (Unsupported Superlatives, Hype Filler)",
                confidence=CONFIDENCE_HEURISTIC,
                action_priority="P2_MEDIUM",
                remediation_steps=[
                    "Replace each superlative ('industry-leading', 'революционный') with a named fact: client, number, date.",
                    "Flatten hedging stacks ('may potentially reduce') to one verifiable claim ('reduces by 31% at client X').",
                    "Remove emoji used as document structure; keep one register throughout.",
                    "Detected patterns: " + ", ".join(_sl_matches[:6])
                ],
                impact_estimate="Citation-killer register: readers and AI engines discount claims that pattern-match generated boilerplate; pages are quoted less and trusted less."
            )
        elif slop_data.get("verdict") == "LOW":
            builder.add_evidence(
                rule_id="GEO-SLOP-DETECT-026",
                category="geo",
                title="AI Slop Density (Citation-Killer Phrasing)",
                status=STATUS_PASS,
                confidence=CONFIDENCE_HEURISTIC,
                observed="No AI-slop phrasing patterns detected",
                expected="Concrete, verifiable register without generated-boilerplate phrasing",
                message="Content register is concrete and free of generated-boilerplate phrasing."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-SLOP-DETECT-026",
                category="geo",
                title="AI Slop Density (Citation-Killer Phrasing)",
                status=STATUS_INFO,
                confidence=CONFIDENCE_HEURISTIC,
                observed=f"Slop density {_sl_density}/1000 words ({_sl_hits} hits): {', '.join(_sl_matches[:5])}",
                expected="Concrete, verifiable register without generated-boilerplate phrasing",
                message="Some boilerplate phrasing detected; replacing it with named facts would strengthen citation trust."
            )

    # GEO-ENTITY-DEFINITION-027: '[category] for [audience]' opening definition
    if content_data.opening_has_direct_answer:
        if audience_def.get("found"):
            builder.add_evidence(
                rule_id="GEO-ENTITY-DEFINITION-027",
                category="geo",
                title="Category-for-Audience Definition Pattern",
                status=STATUS_PASS,
                confidence=CONFIDENCE_HEURISTIC,
                observed=f"Definition pattern in opening block: \"{audience_def.get('snippet', '')[:100]}\"",
                expected="Opening defines entity as '[category] for [audience]'",
                message="Opening block carries a canonical category-for-audience definition AI engines can reuse verbatim for 'what is X / who is X for' queries."
            )
        else:
            builder.add_evidence(
                rule_id="GEO-ENTITY-DEFINITION-027",
                category="geo",
                title="Category-for-Audience Definition Pattern",
                status=STATUS_INFO,
                confidence=CONFIDENCE_HEURISTIC,
                observed="Opening block has a definition but does not name the audience ('... for [audience]')",
                expected="Opening defines entity as '[category] for [audience]'",
                message="Add the audience to the opening definition: '[Entity] is a [category] for [audience] that [outcome]' — the pattern AI engines reuse verbatim."
            )

    # GEO-CITATION-LINKS-008
    st_count = content_data.unverified_stats_count
    ext_links_count = html_data.get("links", {}).get("external_count", 0)
    if st_count > 0 and ext_links_count == 0:
        builder.add_evidence(
            rule_id="GEO-CITATION-LINKS-008",
            category="geo",
            title="Statistical Claims Outbound Source Grounding",
            status=STATUS_INFO,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{st_count} numeric claims without external hyperlink citations",
            expected="External anchor links backing factual assertions",
            message="Page presents statistics without outbound hyperlink sources. Adding <a href='...'> citations enables AI crawlers to verify claims."
        )
    else:
        builder.add_evidence(
            rule_id="GEO-CITATION-LINKS-008",
            category="geo",
            title="Statistical Claims Outbound Source Grounding",
            status=STATUS_PASS,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"Claims grounded ({ext_links_count} external links present)",
            expected="External anchor links or verified citations",
            message="Claims are grounded with outbound link references or verified citations."
        )

    # SCHEMA-AUTHOR-LINK-012
    if schema_data and schema_data.entities:
        person_nodes = []
        for e in schema_data.entities:
            if e.get("@type") == "Person" and e.get("name"):
                person_nodes.append(e)
            auth = e.get("author")
            if isinstance(auth, dict) and auth.get("name"):
                person_nodes.append(auth)
            elif isinstance(auth, list):
                for a in auth:
                    if isinstance(a, dict) and a.get("name"):
                        person_nodes.append(a)
        if person_nodes:
            v_text = html_data.get("visible_text", "")
            p_name = person_nodes[0].get("name", "").strip()
            if p_name and p_name.lower() in v_text.lower():
                builder.add_evidence(
                    rule_id="SCHEMA-AUTHOR-LINK-012",
                    category="schema",
                    title="Author Person Byline & SameAs Parity",
                    status=STATUS_PASS,
                    confidence=CONFIDENCE_VERIFIED,
                    observed=f"Schema author '{p_name}' verified in visible document text",
                    expected="Schema author name visibly rendered in HTML",
                    message="Author identity in Schema matches visible author byline."
                )
            elif p_name:
                builder.add_evidence(
                    rule_id="SCHEMA-AUTHOR-LINK-012",
                    category="schema",
                    title="Author Person Byline & SameAs Parity",
                    status=STATUS_WARNING,
                    confidence=CONFIDENCE_VERIFIED,
                    observed=f"Schema author '{p_name}' not found in visible text",
                    expected="Schema author name visibly rendered in HTML",
                    message=f"Schema declares author '{p_name}', but name is not rendered in visible HTML text."
                )
                builder.add_finding(
                    rule_id="SCHEMA-AUTHOR-LINK-012",
                    category="schema",
                    severity=STATUS_WARNING,
                    title="Schema Author Name Missing From Visible Byline",
                    confidence=CONFIDENCE_VERIFIED,
                    action_priority="P2_MEDIUM",
                    remediation_steps=[f"Add visible author byline mentioning '{p_name}'."],
                    impact_estimate="Google E-E-A-T evaluator guidelines require author transparency."
                )

    # PERF-CWV-FIELD-007
    if perf_data.cwv_field.is_measured and perf_data.cwv_field.lcp_ms is not None:
        lcp = perf_data.cwv_field.lcp_ms
        inp = perf_data.cwv_field.inp_ms
        cls = perf_data.cwv_field.cls_score
        is_good = (lcp <= 2500 and (inp is None or inp <= 200) and (cls is None or cls <= 0.1))
        builder.add_evidence(
            rule_id="PERF-CWV-FIELD-007",
            category="performance",
            title="Core Web Vitals Real-User Field Metrics (CrUX)",
            status=STATUS_PASS if is_good else STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"CrUX Field Data: LCP={lcp}ms, INP={inp}ms, CLS={cls}",
            expected="75th percentile LCP < 2.5s, INP < 200ms, CLS < 0.1",
            message=f"Real-user field performance from PageSpeed Insights API. Overall Performance Score: {perf_data.cwv_field.performance_score or 'N/A'}/100."
        )
    else:
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
    # TECH-INDEXNOW-KEY-039: IndexNow Protocol Fast-Track Search Engine Indexing
    has_indexnow = False
    indexnow_detail = "IndexNow key not detected on single-page fetch"
    # Only structured markers (meta/link tag) count: a page merely *mentioning*
    # IndexNow in body text used to earn PASS "instant indexing configured".
    if re.search(r"<meta[^>]+indexnow|<link[^>]+indexnow", str(body_text), re.IGNORECASE):
        has_indexnow = True
        indexnow_detail = "IndexNow meta/link tag detected in page head"
    builder.add_evidence(
        rule_id="TECH-INDEXNOW-KEY-039",
        category="technical",
        title="IndexNow Protocol Instant Search Indexing",
        status=STATUS_PASS if has_indexnow else STATUS_INFO,
        confidence=CONFIDENCE_VERIFIED,
        observed=indexnow_detail,
        expected="Hosted /{apiKey}.txt or IndexNow automated submission hook",
        message="IndexNow instant indexing configured." if has_indexnow else "Fast-Track Indexing: For new sites, host an IndexNow key at /{apiKey}.txt for instant push indexing to Bing/Yandex/Seznam. For Google, submit via Search Console (Google Indexing API is officially restricted to JobPosting/BroadcastEvent)."
    )

    # AGENT-MARKDOWN-NEGOTIATION-001: Content Negotiation for AI Agents
    agentic_data = html_data.get("agentic_readiness", {})
    md_alt = agentic_data.get("markdown_alternate_url")
    _vary_tokens = [t.strip().lower() for t in str(headers.get("vary", "")).split(",")]
    has_vary_accept = "accept" in _vary_tokens
    if md_alt or has_vary_accept:
        builder.add_evidence(
            rule_id="AGENT-MARKDOWN-NEGOTIATION-001",
            category="technical",
            title="Markdown Content Negotiation for Autonomous AI Agents",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"Markdown alternate detected: {md_alt or 'Vary: Accept'}",
            expected="<link rel='alternate' type='text/markdown'> or Accept: text/markdown negotiation",
            message="Site provides clean Markdown alternate content for autonomous browsing agents."
        )
    else:
        builder.add_evidence(
            rule_id="AGENT-MARKDOWN-NEGOTIATION-001",
            category="technical",
            title="Markdown Content Negotiation for Autonomous AI Agents",
            status=STATUS_INFO,
            confidence=CONFIDENCE_VERIFIED,
            observed="No Markdown alternate link or Vary: Accept header detected",
            expected="<link rel='alternate' type='text/markdown'> or Accept: text/markdown negotiation",
            message="Consider providing <link rel='alternate' type='text/markdown' href='...'> or /llms.txt for autonomous agent readers."
        )

    # AGENT-A11Y-INTERACTIVE-002: Lighthouse Agentic Browsing Accessibility
    unnamed_btn = agentic_data.get("unnamed_buttons_count", 0)
    unlabelled_inp = agentic_data.get("unlabelled_inputs_count", 0)
    fake_btn = agentic_data.get("fake_buttons_count", 0)
    total_a11y_defects = unnamed_btn + unlabelled_inp + fake_btn
    if total_a11y_defects > 0:
        builder.add_evidence(
            rule_id="AGENT-A11Y-INTERACTIVE-002",
            category="technical",
            title="Interactive Accessibility for Autonomous Agents (Lighthouse Agentic Browsing)",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{unnamed_btn} unnamed button(s), {unlabelled_inp} unlabelled input(s), {fake_btn} non-semantic button(s)",
            expected="All buttons and inputs have accessible names for agent navigation",
            message=f"Interactive elements lack accessible names ({total_a11y_defects} issue(s)). AI browsing agents rely on accessibility tree labels to click and navigate."
        )
        builder.add_finding(
            rule_id="AGENT-A11Y-INTERACTIVE-002",
            category="technical",
            severity=STATUS_WARNING,
            title="Interactive Elements Missing Accessible Names for AI Agents",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=[
                "Add aria-label or visible text to empty <button> elements.",
                "Ensure all form <input> tags have corresponding <label for='...'> or aria-label.",
                "Replace <div onclick> with <button> or add role='button' and tabindex='0'."
            ],
            impact_estimate="Prevents autonomous browsing agents (Operator, Claude Computer Use) from navigating interactive workflows."
        )
    else:
        builder.add_evidence(
            rule_id="AGENT-A11Y-INTERACTIVE-002",
            category="technical",
            title="Interactive Accessibility for Autonomous Agents (Lighthouse Agentic Browsing)",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed="All interactive elements have accessible names and semantic roles",
            expected="All buttons and inputs have accessible names",
            message="Clean accessibility tree: autonomous browsing agents can accurately identify and operate interactive controls."
        )

    # Disabled rules must be filtered BEFORE build(): filtering the built ledger
    # only touched evidence, leaving findings, coverage and criteria tables
    # inconsistent with the report (and --fail-on firing on disabled rules).
    if config and config.disabled_rules:
        disabled_set = set(config.disabled_rules)
        builder.evidence = [e for e in builder.evidence if e.rule_id not in disabled_set]
        builder.findings = [f for f in builder.findings if f.rule_id not in disabled_set]
    ledger = builder.build(expected_baseline=EXPECTED_BASELINE_SIGNALS)

    ledger.metadata["agentic_readiness"] = agentic_data
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
    md.append(f"| **AEO & Direct Answer Score** | **{scores.aeo_score} / 100** ({scores.aeo_tier}) | Answer Engine Optimization: direct answers, Q&A headings, section pyramid, speech/voice schema |")
    crit_obs = ledger.metadata.get("criteria_observed", ledger.metadata.get("signals_measured", 0))
    crit_tot = ledger.metadata.get("criteria_total", ledger.metadata.get("signals_total", 0))
    md.append(f"| **Observation Coverage** | **{scores.observation_coverage_pct}%** ({crit_obs}/{crit_tot} criteria) | Empirical completeness of audit scope |")
    md.append("")

    # Baseline notice from Project Context (if present)
    baseline_info = ledger.metadata.get("project_context_recent_baseline")
    if baseline_info:
        md.append("> [!TIP]")
        md.append(f"> **Project Context:** Reusing verified audit baseline from `{baseline_info.get('timestamp')}` ({baseline_info.get('summary')}).")
        md.append("")

    # 1. Your Next SEO Move (Top 1-3 Recommendations: Do this / Why)
    findings = ledger.findings
    # "Highest-leverage actions" requires actual prioritization, not emission order.
    def _priority_rank(f):
        ap = str(getattr(f, "action_priority", "") or "")
        if ap.startswith("P0"):
            return 0
        if ap.startswith("P1"):
            return 1
        if ap.startswith("P2"):
            return 2
        return 3

    _sev_rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2, "PASS": 3}
    top_findings = sorted(
        findings,
        key=lambda f: (_priority_rank(f), _sev_rank.get(getattr(f, "severity", ""), 4)),
    )[:3]
    deferred_findings = findings[3:]

    if top_findings:
        md.append("## 🚀 Your Next SEO Move (Top Priorities)")
        md.append("")
        for idx, f in enumerate(top_findings, 1):
            md.append(f"### {idx}. {f.title}")
            md.append("**Do this:**")
            for step in f.remediation_steps[:3]:
                md.append(f"- {step}")
            md.append("")
            md.append("**Why:**")
            md.append(f"- **Observed Gap:** {f.impact_estimate}")
            md.append(f"- **Evaluation Category:** `{f.category}` (Priority: `[{f.action_priority}]`, Severity: `{f.severity}`)")
            md.append("- **Plausible Benefit:** Eliminates ranking friction and improves synthetic answer retrieval probability.")
            md.append("- **Main Uncertainty:** Search engine crawl re-indexation lag (typically 3–14 days).")
            md.append("")

    if deferred_findings:
        md.append("### 📋 What Else We Checked (Deferred Opportunities)")
        md.append("These candidate issues were evaluated but deferred to keep execution focused on the highest-leverage actions:")
        md.append("")
        md.append("| Opportunity / Check | Observed Finding | Decision & Rationale |")
        md.append("| :--- | :--- | :--- |")
        for df in deferred_findings:
            rationale = "Deferred: secondary hygiene, prioritize core blockers first" if df.action_priority in ("P2_MEDIUM", "P3_LOW") else "Deferred: test primary recommendations first"
            clean_impact = df.impact_estimate.replace("|", "/")
            md.append(f"| `{df.rule_id}`: {df.title} | {clean_impact} | {rationale} |")
        md.append("")

    # GSC Striking Distance Section (if present)
    gsc_md = ledger.metadata.get("gsc_markdown")
    if gsc_md:
        md.append(gsc_md)
        md.append("")

    # GA4 AI-Referral Traffic Section (if present)
    ga4_md = ledger.metadata.get("ga4_markdown")
    if ga4_md:
        md.append(ga4_md)
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

    # AEO 7-Component Breakdown
    if scores.aeo_dimensions:
        aeo = scores.aeo_dimensions
        md.append("## 🎯 Answer Engine Optimization (AEO & Direct Answers)")
        md.append("")
        md.append(f"> **AEO & Direct Answer Score**: **{scores.aeo_score} / 100** ({scores.aeo_tier})  ")
        md.append("")
        md.append("| Dimension | Max Weight | Points | Evaluation Basis |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **Direct Answer Definition** | 25 | **{aeo.direct_answer_definition} pts** | Definition frontloaded in first 40–60 words (`GEO-ANSWER-FRONTLOAD-001`) |")
        md.append(f"| **Question Headings** | 20 | **{aeo.question_headings} pts** | H2/H3 natural question phrasing followed immediately by direct answer (`CONTENT-QUESTION-HEADINGS-002`) |")
        md.append(f"| **Section Inverted Pyramid** | 15 | **{aeo.section_pyramid} pts** | Core conclusion/result first in each subsection (`GEO-SECTION-PYRAMID-024`) |")
        md.append(f"| **Passage Autonomy** | 15 | **{aeo.passage_autonomy} pts** | Standalone self-contained paragraphs free of dangling pronouns (`GEO-COREFERENCE-INDEPENDENCE-003`, `GEO-ADAPTIVE-CHUNKING-002`) |")
        md.append(f"| **Citation & Deep-Link Anchors** | 10 | **{aeo.citation_anchors} pts** | Explicit section IDs for precise AI quote deep-linking (`GEO-ANCHOR-DEEPLINK-023`) |")
        md.append(f"| **Extractable Formats** | 10 | **{aeo.extractable_formats} pts** | Tabular, step-by-step, or TL;DR summary formats (`CONTENT-EXTRACTABLE-003`) |")
        md.append(f"| **Machine & Voice Markup** | 5 | **{aeo.semantic_qa_markup} pts** | `SpeakableSpecification` or structured FAQ/HowTo markup (`SCHEMA-SPEAKABLE-027`, `SCHEMA-FAQ-PAGE-001`) |")
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

    # Autonomous Agent Readiness (Lighthouse Agentic Browsing & WebMCP)
    agentic = ledger.metadata.get("agentic_readiness")
    if agentic:
        md.append("## 🤖 Autonomous Agent Readiness (Lighthouse Agentic Browsing)")
        md.append("")
        a11y_score = agentic.get("interactive_accessibility_score", 100.0)
        tier_str = "Agent-Ready" if a11y_score >= 90 else ("Frictional" if a11y_score >= 70 else "Agent-Hostile")
        md.append(f"> **Interactive Accessibility Score**: **{a11y_score:.1f} / 100** ({tier_str})")
        md.append("> *Measures whether autonomous browsing agents (Operator, Claude Computer Use) can perceive controls and navigate.*")
        md.append("")
        md.append("| Check | Observed Value | Agent Impact |")
        md.append("| :--- | :--- | :--- |")
        btn_total = agentic.get("buttons_count", 0)
        unnamed_btn = agentic.get("unnamed_buttons_count", 0)
        btn_status = f"{btn_total - unnamed_btn}/{btn_total} named" if btn_total > 0 else "0 buttons"
        btn_verdict = "[PASS] All buttons named" if unnamed_btn == 0 else f"[WARN] {unnamed_btn} unnamed button(s)"
        md.append(f"| **Accessible Buttons** | `{btn_status}` ({btn_verdict}) | Screen reader / LLM accessibility tree label |")

        inp_unlabelled = agentic.get("unlabelled_inputs_count", 0)
        inp_verdict = "[PASS] All inputs labelled" if inp_unlabelled == 0 else f"[WARN] {inp_unlabelled} unlabelled input(s)"
        md.append(f"| **Form Input Labels** | {inp_verdict} | Enables form autofill & synthetic interaction |")

        fake_btn = agentic.get("fake_buttons_count", 0)
        fake_verdict = "[PASS] Semantic controls" if fake_btn == 0 else f"[WARN] {fake_btn} non-semantic <div onclick>"
        md.append(f"| **Semantic Elements** | {fake_verdict} | Keyboard & synthetic pointer focusability |")

        md_alt = agentic.get("markdown_alternate_url")
        md_status = f"`{md_alt}`" if md_alt else "None detected"
        md.append(f"| **Markdown Alternate** | {md_status} | Fast-path context ingest (<link rel='alternate' type='text/markdown'>) |")

        has_pricing = agentic.get("has_pricing_link", False)
        pricing_status = "[PASS] Transparent pricing / documentation link" if has_pricing else "[INFO] No dedicated /pricing link detected"
        md.append(f"| **Transparent Pricing** | {pricing_status} | Transparent pricing enables direct procurement recommendations |")
        md.append("")
        md.append("> *Protocol Note*: WebMCP (W3C Draft) and `/llms.txt` support enable autonomous agents to query APIs and structured catalogs without DOM scraping overhead.")
        md.append("")

    md.append("> [!NOTE]")
    md.append("> **Evidence Ledger Invariant: 'Unknown != Failure' & Observations != Causes**  ")
    md.append(f"> Exactly {scores.not_measured_count} unmeasured external signal(s) (e.g., CWV CrUX field data) were detected. In compliance with the Evidence Protocol, unmeasured signals carry 0 penalty. Observations describe verified technical state (`[VERIFIED_FACT]`), not algorithmic penalties or speculative revenue claims.")
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

    parser = argparse.ArgumentParser(description="Ultimate SEO & GEO Autonomous Inspection Engine v3.8.0")
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
    parser.add_argument("--generate-llms-txt", action="store_true", help="Generate standard-compliant /llms.txt file from target/crawl metadata")
    parser.add_argument("--experiment", action="store_true", help="Run AI Citation Benchmark Before/After experiment comparison")
    parser.add_argument("--before", help="Path to baseline benchmark JSON file")
    parser.add_argument("--after", help="Path to post-optimization benchmark JSON file")
    parser.add_argument("--gsc-csv", help="Optional path to Google Search Console performance export CSV for striking distance and CTR underperformance analysis")
    parser.add_argument("--ga4-csv", help="Optional path to GA4 Traffic Acquisition CSV for AI referral engine analysis (ChatGPT, Perplexity, Claude, etc.)")
    parser.add_argument("--project-context", help="Optional path to persistent SEO project dossier JSON (auto-detects seo-project-context.json or .seo-context.json if omitted)")

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
        from .config import CrawlConfig
        from .crawler import crawl_site, format_site_crawl_markdown
        config = CrawlConfig(
            seed_url=args.target,
            max_pages=args.max_pages if args.max_pages != 50 else cfg.crawl.max_pages,
            max_depth=args.depth if args.depth != 3 else cfg.crawl.max_depth,
            timeout=args.timeout if args.timeout != 15.0 else cfg.crawl.timeout,
            delay_seconds=cfg.crawl.delay_seconds,
            user_agent=args.user_agent or cfg.crawl.user_agent
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

    # Project Context Dossier Handling (Pre-inspection)
    p_ctx = None
    try:
        from .project_context import ProjectContext
        p_ctx = ProjectContext.load(args.project_context)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to load project context: {e}\n")

    try:
        ledger, scores = run_inspection(
            args.target,
            custom_robots_txt=custom_robots,
            timeout=args.timeout,
            user_agent=args.user_agent,
            rendered_html=args.rendered_html,
            config=cfg
        )
    except Exception as exc:
        sys.stderr.write(f"Error executing inspection: {exc}\n")
        sys.exit(1)

    # Attach Project Context metadata & check 30-day baseline
    if p_ctx is not None and (p_ctx.project_name or p_ctx.domain or p_ctx.research_log):
        ledger.metadata["project_context"] = p_ctx.to_dict()
        recent_baseline = p_ctx.get_recent_research(args.target, max_age_days=30)
        if recent_baseline:
            ledger.metadata["project_context_recent_baseline"] = recent_baseline

    # Google Search Console (GSC) Performance Analysis
    if args.gsc_csv:
        try:
            from .analyzers.gsc_analyzer import analyze_gsc_csv, format_gsc_markdown_summary
            gsc_res = analyze_gsc_csv(args.gsc_csv)
            ledger.metadata["gsc_analysis"] = gsc_res.to_dict()
            ledger.metadata["gsc_markdown"] = format_gsc_markdown_summary(gsc_res)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to analyze GSC CSV: {e}\n")

    # GA4 AI-Referral Traffic Analysis
    if args.ga4_csv:
        try:
            from .analyzers.ga4_analyzer import analyze_ga4_csv, format_ga4_markdown_summary
            ga4_res = analyze_ga4_csv(args.ga4_csv)
            ledger.metadata["ga4_analysis"] = ga4_res.to_dict()
            ledger.metadata["ga4_markdown"] = format_ga4_markdown_summary(ga4_res)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to analyze GA4 CSV: {e}\n")

    # Persist audit results to Project Context if dossier is active
    if p_ctx is not None and (args.project_context or os.path.exists("seo-project-context.json") or os.path.exists(".seo-context.json")):
        findings_summary = f"Observable Tech Score: {scores.observable_technical_score}, GEO Score: {scores.geo_readiness_index}, Findings: {len(ledger.findings)}"
        p_ctx.append_research_log(
            summary=f"Audit {args.target}: {findings_summary}",
            verdict=f"Tech: {scores.observable_technical_score}/100, GEO: {scores.geo_readiness_index}/100",
            mode="audit"
        )
        if str(args.target).startswith(("http://", "https://")):
            p_ctx.add_key_page(args.target, role="audited_page")
        try:
            p_ctx.save(args.project_context)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to save project context: {e}\n")

    # Standard-Compliant /llms.txt Generation Mode
    if args.generate_llms_txt:
        from .analyzers.llms_analyzer import generate_llms_txt
        site_title = ledger.metadata.get("page_title") or "Website Documentation"
        site_desc = ledger.metadata.get("meta_description") or "Curated content and key documentation pages for LLM context grounding."
        pages_list = [{"title": site_title, "url": args.target, "description": site_desc}]
        seen_urls = {args.target}
        raw_links = ledger.metadata.get("html_links", [])
        for link in raw_links:
            href = link.get("href", "").strip()
            anchor = link.get("text", "").strip()
            if href and href not in seen_urls and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                seen_urls.add(href)
                pages_list.append({
                    "title": anchor or href.rstrip("/").split("/")[-1].replace("-", " ").capitalize() or "Documentation",
                    "url": href,
                    "description": ""
                })
            if len(pages_list) >= 20:
                break

        llms_txt_str = generate_llms_txt(
            title=site_title,
            summary=site_desc,
            pages=pages_list
        )
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(llms_txt_str)
            print(f"Generated /llms.txt saved to {args.output}")
            _full_path = args.output.replace(".txt", "") + "-full.txt"
            _page_text = ""
            try:
                _page_text = str(ledger.metadata.get("page_visible_text", "") or "")
            except Exception:
                _page_text = ""
            with open(_full_path, "w", encoding="utf-8") as f:
                f.write(generate_llms_full_txt(
                    title=site_title,
                    pages=[{"title": site_title, "url": args.target, "text": _page_text}] + [
                        {"title": p.get("title", ""), "url": p.get("url", ""), "text": ""}
                        for p in pages_list[1:]
                    ]
                ))
            print(f"Generated /llms-full.txt saved to {_full_path}")
        else:
            print(llms_txt_str)
        return

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
        from dataclasses import asdict, is_dataclass
        res_dict = ledger.to_dict()
        res_dict["scores"] = asdict(scores) if is_dataclass(scores) else scores.__dict__
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

    if args.strict or (cfg and cfg.strict_mode):
        critical_findings = [f for f in ledger.findings if f.severity == STATUS_CRITICAL]
        if critical_findings:
            ci_failed = True
            failure_reasons.append(f"strict mode: {len(critical_findings)} CRITICAL finding(s) detected")

    if cfg and cfg.strict_mode:
        if scores.observable_technical_score < cfg.thresholds.technical_score:
            ci_failed = True
            failure_reasons.append(f"Config strict_mode: Technical score {scores.observable_technical_score} below threshold {cfg.thresholds.technical_score}")
        if scores.geo_readiness_index < cfg.thresholds.geo_score:
            ci_failed = True
            failure_reasons.append(f"Config strict_mode: GEO score {scores.geo_readiness_index} below threshold {cfg.thresholds.geo_score}")
        if scores.security_score < cfg.thresholds.security_score:
            ci_failed = True
            failure_reasons.append(f"Config strict_mode: Security score {scores.security_score} below threshold {cfg.thresholds.security_score}")

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
