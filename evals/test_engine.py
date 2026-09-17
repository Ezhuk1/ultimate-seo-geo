"""
Automated integration tests for Autonomous Engine v2.0.0.
Verifies:
- Deterministic signal extraction
- RFC 9309 robots crawler simulation
- Schema.org AST & @graph interconnection
- GEO content analysis & direct answer frontload
- Strict 'Unknown != Failure' invariant & 0 penalty for unmeasured signals
- Multi-format output (Markdown & JSON)
"""

import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from engine.inspector import run_inspection, format_markdown_report
from engine.analyzers.robots_simulator import parse_robots_txt, simulate_ai_crawlers, is_allowed
from engine.analyzers.schema_analyzer import analyze_json_ld
from engine.analyzers.sitemap_analyzer import parse_sitemap_xml
from engine.scoring import calculate_scores


def test_clean_page_inspection():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <title>Ultimate SEO &amp; GEO Engine Test Page</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="A comprehensive test page demonstrating the evidence ledger protocol and deterministic SEO signal inspection in action with optimal length.">
    <link rel="canonical" href="https://example.com/test">
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "WebSite",
          "@id": "https://example.com/#website",
          "name": "Example Corp",
          "url": "https://example.com"
        },
        {
          "@type": "WebPage",
          "@id": "https://example.com/test#webpage",
          "url": "https://example.com/test",
          "name": "Test Page",
          "isPartOf": {"@id": "https://example.com/#website"}
        }
      ]
    }
    </script>
</head>
<body>
    <h1>Generative Engine Optimization Definition and Guide</h1>
    <p>Generative Engine Optimization is a methodology for structuring digital assets so that answer engines synthesize factual claims directly.</p>
</body>
</html>"""

    fd, path = tempfile.mkstemp(suffix=".html")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(html)

    try:
        ledger, scores = run_inspection(path)
        assert scores.observable_technical_score == 100, f"Expected 100, got {scores.observable_technical_score}"
        assert scores.geo_readiness_index >= 85, f"Expected >= 85, got {scores.geo_readiness_index}"
        assert scores.not_measured_count >= 1, "Expected at least 1 unmeasured signal (CWV field data)"
        assert len(ledger.raw.provenance_hash) == 64, "Expected valid 64-character SHA-256 hash"
        
        md_report = format_markdown_report(ledger, scores)
        assert "Evidence-Driven SEO & GEO Inspection Report" in md_report
        assert "Unknown != Failure" in md_report
        assert "Executive Scorecard" in md_report
        print("[PASS] test_clean_page_inspection")
    finally:
        os.remove(path)


def test_defective_page_detection():
    html = """<!DOCTYPE html>
<html>
<head>
    <!-- Missing canonical -->
    <!-- Missing title -->
    <!-- Missing meta description -->
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Offer",
      "price": "$99.95 USD"
    }
    </script>
</head>
<body>
    <!-- Missing H1 -->
    <h2>Subheading Only</h2>
    <p>In today's fast-paced world, have you ever wondered how things work? It is very interesting.</p>
</body>
</html>"""

    fd, path = tempfile.mkstemp(suffix=".html")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(html)

    try:
        ledger, scores = run_inspection(path)
        assert scores.observable_technical_score < 70, f"Expected severe deduction, got {scores.observable_technical_score}"
        
        rule_ids = {f.rule_id for f in ledger.findings}
        assert "TECH-CANONICAL-001" in rule_ids, "Missing TECH-CANONICAL-001 finding"
        assert "TECH-TITLE-003" in rule_ids, "Missing TECH-TITLE-003 finding"
        assert "TECH-VIEWPORT-006" in rule_ids, "Missing TECH-VIEWPORT-006 finding"
        assert "SCHEMA-PRICE-FORMAT-003" in rule_ids, "Missing SCHEMA-PRICE-FORMAT-003 finding"
        assert "GEO-ANSWER-FRONTLOAD-001" in rule_ids, "Missing GEO-ANSWER-FRONTLOAD-001 finding"
        print("[PASS] test_defective_page_detection")
    finally:
        os.remove(path)


def test_robots_simulator_rfc9309():
    robots_txt = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /

User-agent: GPTBot
Disallow: /api/
Allow: /

User-agent: ClaudeBot
Disallow: /
"""
    data = parse_robots_txt(robots_txt)
    
    # Check GPTBot
    allowed, rule, _ = is_allowed(data, "GPTBot", "/")
    assert allowed is True, "GPTBot should be allowed at /"
    
    allowed_api, _, _ = is_allowed(data, "GPTBot", "/api/data")
    assert allowed_api is False, "GPTBot should be disallowed at /api/data"

    # Check ClaudeBot
    allowed_claude, _, _ = is_allowed(data, "ClaudeBot", "/")
    assert allowed_claude is False, "ClaudeBot should be disallowed at /"

    # Check Wildcard crawler
    allowed_other, _, _ = is_allowed(data, "OtherBot", "/private/secret")
    assert allowed_other is False, "OtherBot should be disallowed at /private/secret"
    
    allowed_other_root, _, _ = is_allowed(data, "OtherBot", "/public")
    assert allowed_other_root is True, "OtherBot should be allowed at /public"

    sim = simulate_ai_crawlers(data)
    assert sim["GPTBot"]["root_allowed"] is True
    assert sim["ClaudeBot"]["root_allowed"] is False

    # Check RFC 9309 product token matching with complex User-Agent string
    full_ua = "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"
    allowed_full_root, _, _ = is_allowed(data, full_ua, "/")
    assert allowed_full_root is True, "Complex GPTBot user agent string must match GPTBot group"
    allowed_full_api, _, _ = is_allowed(data, full_ua, "/api/data")
    assert allowed_full_api is False, "Complex GPTBot user agent string must obey GPTBot disallow"

    print("[PASS] test_robots_simulator_rfc9309")


def test_unknown_signal_invariant():
    """Verifies that unmeasured signals NEVER deduct points from the observable score."""
    from engine.ledger import LedgerBuilder, STATUS_PASS, STATUS_NOT_MEASURED, CONFIDENCE_UNVERIFIABLE, CONFIDENCE_VERIFIED
    
    builder = LedgerBuilder("https://example.com")
    builder.set_raw(200, {"content-type": "text/html"}, "<html></html>", 50.0)
    builder.add_signal("observed_signal_1", "Test Signal", True)
    builder.add_signal("unmeasured_signal_1", "CWV Telemetry", None, is_measured=False)
    
    builder.add_evidence(
        rule_id="TEST-OBSERVED-PASS",
        category="technical",
        title="Observed Pass",
        status=STATUS_PASS,
        confidence=CONFIDENCE_VERIFIED,
        observed=True,
        expected=True,
        message="Pass"
    )
    builder.add_evidence(
        rule_id="TEST-UNMEASURED-SIGNAL",
        category="performance",
        title="Unmeasured CWV Field Metric",
        status=STATUS_NOT_MEASURED,
        confidence=CONFIDENCE_UNVERIFIABLE,
        observed="No telemetry key",
        expected="Measured value",
        message="Unmeasured metric"
    )
    
    ledger = builder.build()
    scores = calculate_scores(ledger)
    assert scores.observable_technical_score == 100, f"Expected 100 with unmeasured signals, got {scores.observable_technical_score}"
    assert scores.not_measured_count == 1
    assert len(scores.deductions) == 0
    print("[PASS] test_unknown_signal_invariant")


def test_csr_shell_detection():
    """Verifies that empty client-side rendering mounts are caught with TECH-CSR-SHELL-008."""
    csr_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <title>My Client-Side Single Page Application</title>
    <meta name="description" content="A client side rendered React application shell that loads data via client-side fetch API.">
    <link rel="canonical" href="https://example.com/app">
    <script src="/static/js/main.c498ef.chunk.js" defer></script>
</head>
<body>
    <div id="root"></div>
    <noscript>You need to enable JavaScript to run this app.</noscript>
</body>
</html>"""

    fd, path = tempfile.mkstemp(suffix=".html")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(csr_html)

    try:
        ledger, scores = run_inspection(path)
        rule_ids = {f.rule_id for f in ledger.findings}
        assert "TECH-CSR-SHELL-008" in rule_ids, "Expected TECH-CSR-SHELL-008 to be flagged for empty div#root"
        csr_ev = next(e for e in ledger.evidence if e.rule_id == "TECH-CSR-SHELL-008")
        assert csr_ev.status == "CRITICAL"
        assert "Fast AI search crawlers" in csr_ev.message
        print("[PASS] test_csr_shell_detection")
    finally:
        os.remove(path)


def test_schema_standalone_validator():
    """Verifies validate_schema_snippet catches broken @id references, bad prices, and invalid dates."""
    from engine.analyzers.schema_analyzer import validate_schema_snippet

    valid_schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": "https://example.com/#site",
                "name": "Example Corp",
                "url": "https://example.com"
            },
            {
                "@type": "WebPage",
                "@id": "https://example.com/#page",
                "name": "Example Page",
                "isPartOf": {"@id": "https://example.com/#site"},
                "datePublished": "2026-05-15T08:00:00Z",
                "dateModified": "2026-05-16"
            }
        ]
    }

    is_valid, errors, res = validate_schema_snippet(valid_schema)
    assert is_valid is True, f"Expected valid schema, got errors: {errors}"
    assert len(errors) == 0

    broken_schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": "https://example.com/#page",
                "name": "Page with Broken Ref and Bad Date",
                "author": {"@id": "https://example.com/#nonexistent_author"},
                "datePublished": "15 May 2026"
            },
            {
                "@type": "Offer",
                "price": "$199.99"
            }
        ]
    }

    is_valid_broken, errors_broken, res_broken = validate_schema_snippet(broken_schema)
    assert is_valid_broken is False, "Expected broken schema to fail validation"
    assert any("SCHEMA-BROKEN-REF-005" in e for e in errors_broken), "Missing broken ref error"
    assert any("SCHEMA-DATE-FORMAT-006" in e for e in errors_broken), "Missing invalid date error"
    assert any("SCHEMA-PRICE-FORMAT-003" in e for e in errors_broken), "Missing invalid price error"
    print("[PASS] test_schema_standalone_validator")


def test_canonical_hardening():
    html_rel = """<!DOCTYPE html>
<html>
<head>
    <title>Relative Canonical Test Page</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="canonical" href="/relative/path">
</head>
<body><h1>Test Heading</h1></body>
</html>"""
    fd, path = tempfile.mkstemp(suffix=".html")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(html_rel)
    try:
        ledger, _ = run_inspection(path)
        rule_ids = {f.rule_id for f in ledger.findings}
        assert "TECH-CANONICAL-001" in rule_ids, "Expected relative canonical to trigger TECH-CANONICAL-001 finding"
        canonical_ev = [e for e in ledger.evidence if e.rule_id == "TECH-CANONICAL-001"][0]
        assert "relative" in canonical_ev.message.lower()
        print("[PASS] test_canonical_hardening")
    finally:
        os.remove(path)


def test_noindex_detection():
    html_noindex = """<!DOCTYPE html>
<html>
<head>
    <title>Noindex Test Page</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, follow">
    <link rel="canonical" href="https://example.com/noindex">
</head>
<body><h1>Test Heading</h1></body>
</html>"""
    fd, path = tempfile.mkstemp(suffix=".html")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(html_noindex)
    try:
        ledger, _ = run_inspection(path)
        rule_ids = {f.rule_id for f in ledger.findings}
        assert "TECH-NOINDEX-009" in rule_ids, "Expected noindex to trigger TECH-NOINDEX-009 finding"
        print("[PASS] test_noindex_detection")
    finally:
        os.remove(path)


def test_sitemap_analyzer():
    valid_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>https://example.com/test</loc>
      <lastmod>2026-05-15</lastmod>
      <changefreq>monthly</changefreq>
      <priority>0.8</priority>
   </url>
   <url>
      <loc>https://example.com/about</loc>
      <lastmod>2026-05-10</lastmod>
   </url>
</urlset>"""

    res = parse_sitemap_xml(valid_xml, target_url="https://example.com/test", base_domain="example.com")
    assert res.is_valid_xml is True
    assert res.total_urls == 2
    assert res.target_in_sitemap is True
    assert len(res.errors) == 0

    broken_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>/relative/url</loc>
   </url>
   <url>
      <loc>http://insecure.example.com</loc>
      <lastmod>invalid-date-format</lastmod>
   </url>
</urlset>"""
    res_broken = parse_sitemap_xml(broken_xml, target_url="https://example.com/test", base_domain="example.com")
    assert res_broken.is_valid_xml is True
    assert len(res_broken.invalid_urls) == 1
    assert len(res_broken.non_https_urls) == 1
    assert any("Relative URL" in e for e in res_broken.errors)
    assert any("Unparseable lastmod" in w for w in res_broken.warnings)
    print("[PASS] test_sitemap_analyzer")


def test_schema_empty_and_calendar_validation():
    from engine.analyzers.schema_analyzer import validate_schema_snippet
    
    # 1. Empty snippet {} must fail
    is_valid_empty, errors_empty, _ = validate_schema_snippet({})
    assert is_valid_empty is False, "Empty schema {} must fail validation"
    assert any("SCHEMA-EMPTY-000" in e or "SCHEMA-TYPE-MISSING-007" in e for e in errors_empty)
    
    # 2. Price with 1 decimal digit (19.9) must pass
    valid_one_dec = {
        "@context": "https://schema.org",
        "@type": "Offer",
        "price": "19.9"
    }
    is_valid_price, errors_price, _ = validate_schema_snippet(valid_one_dec)
    assert is_valid_price is True, f"Price 19.9 should be valid, got errors: {errors_price}"
    
    # 3. Non-existent calendar date (2026-02-31) must fail
    bad_calendar_date = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "Test Article",
        "datePublished": "2026-02-31"
    }
    is_valid_date, errors_date, _ = validate_schema_snippet(bad_calendar_date)
    assert is_valid_date is False, "Non-existent calendar date 2026-02-31 must fail"
    assert any("SCHEMA-DATE-FORMAT-006" in e for e in errors_date)
    print("[PASS] test_schema_empty_and_calendar_validation")


def test_http_status_blocking_and_coverage():
    from unittest.mock import patch
    from engine.inspector import run_inspection
    
    mock_404_resp = {
        "target": "https://example.com/not-found",
        "final_url": "https://example.com/not-found",
        "is_local": False,
        "status_code": 404,
        "headers": {"content-type": "text/html"},
        "raw_content": "<html><body><h1>404 Not Found</h1></body></html>",
        "response_time_ms": 120.0,
        "tls_valid": True,
        "redirect_chain": [],
        "x_robots_directives": [],
        "x_robots_bot_directives": {},
        "error": None
    }
    
    with patch("engine.inspector.analyze_target_http", return_value=mock_404_resp):
        ledger, scores = run_inspection("https://example.com/not-found")
        rule_ids = {f.rule_id for f in ledger.findings}
        assert "TECH-HTTP-STATUS-000" in rule_ids, "HTTP 404 must trigger TECH-HTTP-STATUS-000 finding"
        assert scores.critical_count >= 1
        assert scores.observable_technical_score <= 75
        # Observation coverage must reflect baseline unmeasured signals, not 100%
        assert scores.observation_coverage_pct < 50.0, f"Expected coverage < 50% on early 404, got {scores.observation_coverage_pct}%"
        print("[PASS] test_http_status_blocking_and_coverage")


def test_sitemap_analyzer_inspector_integration():
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Sitemap Integration Test Page</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="canonical" href="https://example.com/page">
</head>
<body><h1>Sitemap Integration</h1></body>
</html>"""
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>https://example.com/page</loc>
      <lastmod>2026-05-15</lastmod>
   </url>
</urlset>"""
    fd, path = tempfile.mkstemp(suffix=".html")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(html)
    try:
        ledger, scores = run_inspection(path, custom_sitemap_xml=sitemap_xml)
        rule_ids = {e.rule_id for e in ledger.evidence}
        assert "TECH-SITEMAP-011" in rule_ids, "TECH-SITEMAP-011 must be evaluated when sitemap is provided"
        sm_ev = next(e for e in ledger.evidence if e.rule_id == "TECH-SITEMAP-011")
        assert sm_ev.status == "PASS"
        assert ledger.signals["sitemap_present"].value is True
        print("[PASS] test_sitemap_analyzer_inspector_integration")
    finally:
        os.remove(path)


def test_audit_v2_16_fixes():
    """Comprehensive test covering the 16 audit fixes."""
    from engine.analyzers.http_analyzer import _detect_and_decode, _extract_header_canonical
    from engine.analyzers.content_analyzer import analyze_content
    from engine.analyzers.html_analyzer import analyze_target_html
    from engine.analyzers.sitemap_analyzer import merge_sitemap_results, SitemapAnalysisResult
    from engine.ledger import LedgerBuilder, STATUS_CRITICAL, STATUS_WARNING, STATUS_PASS, CONFIDENCE_VERIFIED

    # 1. Sitemap lastmod parsing with standard ISO 8601 offset
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>https://example.com/item1</loc>
      <lastmod>2026-05-15T08:00:00+00:00</lastmod>
   </url>
   <url>
      <loc>https://example.com/item2</loc>
      <lastmod>2026-05-15T08:00:00Z</lastmod>
   </url>
</urlset>"""
    sm_res = parse_sitemap_xml(sitemap_xml, sitemap_url="https://example.com/sitemap.xml", target_url="https://example.com/item1", base_domain="example.com", status_code=200)
    assert len(sm_res.warnings) == 0, f"Expected 0 lastmod warnings for valid ISO strings, got: {sm_res.warnings}"
    assert sm_res.target_in_sitemap is True

    # 1b. Sitemap index merging
    parent = SitemapAnalysisResult(present=True, status_code=200, url="https://example.com/index.xml", is_valid_xml=True, is_sitemap_index=True)
    child = SitemapAnalysisResult(present=True, status_code=200, url="https://example.com/child1.xml", is_valid_xml=True, is_sitemap_index=False, target_in_sitemap=True)
    merged = merge_sitemap_results(parent, [child])
    assert merged.target_in_sitemap is True

    # 2. Charset detection (windows-1251)
    ru_text = "Пример текста на русском языке"
    raw_cp1251 = ru_text.encode("windows-1251")
    decoded, charset = _detect_and_decode(raw_cp1251, "text/html; charset=windows-1251")
    assert charset == "windows-1251"
    assert decoded == ru_text

    # Sniff meta charset from bytes
    raw_with_meta = b'<html><head><meta charset="windows-1251"></head><body>' + raw_cp1251 + b'</body></html>'
    decoded_meta, charset_meta = _detect_and_decode(raw_with_meta, None)
    assert charset_meta == "windows-1251"
    assert ru_text in decoded_meta

    # 3. Header Link canonical parsing
    header_canon = _extract_header_canonical(None, {"link": '<https://example.com/canonical>; rel="canonical"'})
    assert header_canon == "https://example.com/canonical"

    # 4. Robots.txt exact product token and multiple wildcard groups
    robots_content = """
User-agent: *
Disallow: /admin/

User-agent: bot
Disallow: /all-bots-trap/

User-agent: Googlebot
Disallow: /google-only/

User-agent: Googlebot-Image
Disallow: /images/

User-agent: *
Disallow: /private/

Clean-param: ref /catalog
"""
    rdata = parse_robots_txt(robots_content)
    assert "ref /catalog" in rdata.clean_params

    # Googlebot should NOT match Googlebot-Image rules
    allowed_gb_img, _, _ = is_allowed(rdata, "Googlebot", "/images/pic.png")
    assert allowed_gb_img is True, "Googlebot must NOT match Googlebot-Image group rules"

    # Googlebot should match Googlebot group
    allowed_gb, _, _ = is_allowed(rdata, "Googlebot", "/google-only/")
    assert allowed_gb is False, "Googlebot must match Googlebot group rule"

    # Googlebot should NOT match generic 'bot' group
    allowed_gb_trap, _, _ = is_allowed(rdata, "Googlebot", "/all-bots-trap/")
    assert allowed_gb_trap is True, "Googlebot must NOT match 'bot' group rules"

    # Wildcard groups must be merged: /admin/ and /private/ both disallowed for other bots
    allowed_w1, _, _ = is_allowed(rdata, "OtherBot", "/admin/sec")
    allowed_w2, _, _ = is_allowed(rdata, "OtherBot", "/private/sec")
    assert allowed_w1 is False, "Merged wildcard group 1 (/admin/) must disallow"
    assert allowed_w2 is False, "Merged wildcard group 2 (/private/) must disallow"

    # 5. HTML analyzer in_head tracking, rel tokens, duplicates, lang, meta charset, link classification
    test_html = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Первый заголовок</title>
    <title>Второй дубликат заголовка</title>
    <meta name="description" content="Описание 1">
    <meta name="description" content="Описание 2">
    <link rel="canonical alternate" href="https://example.com/head-canonical">
</head>
<body>
    <link rel="canonical" href="https://example.com/body-canonical">
    <a href="mailto:test@example.com">Email</a>
    <a href="tel:+123456789">Phone</a>
    <a href="javascript:void(0)">JS</a>
    <a href="#section">Anchor</a>
    <a href="/internal/path">Internal</a>
    <a href="https://external.com/out">External</a>
</body>
</html>"""
    parsed_h = analyze_target_html(test_html, base_url="https://example.com")
    assert parsed_h["lang"] == "ru"
    assert parsed_h["meta_charset"] == "utf-8"
    assert parsed_h["title"]["count"] == 2
    assert parsed_h["meta_description"]["count"] == 2
    assert parsed_h["canonical"]["in_body"] is True
    assert parsed_h["canonical"]["value"] == "https://example.com/head-canonical"
    # Links: only /internal/path is internal. mailto, tel, javascript, anchor must be excluded!
    assert parsed_h["links"]["internal_count"] == 1
    assert parsed_h["links"]["external_count"] == 1

    # 6. Schema Analyzer: author deduplication & multiple scripts severity INFO
    multi_schema = [
        """{"@context": "https://schema.org", "@type": "Article", "headline": "Test", "author": {"@type": "Person", "name": "Alice", "@id": "#alice"}}""",
        """{"@context": "https://schema.org", "@type": "Person", "name": "Alice", "@id": "#alice"}"""
    ]
    schema_res = analyze_json_ld(multi_schema)
    multi_script_finding = next((f for f in schema_res.findings if f.rule_id == "SCHEMA-GRAPH-INTERCONNECT-002"), None)
    assert multi_script_finding is not None
    assert multi_script_finding.severity == "INFO", "Multiple scripts should have severity INFO, not WARNING"
    # Author findings should be deduplicated: only 1 warning for Alice missing sameAs
    author_findings = [f for f in schema_res.findings if f.rule_id == "SCHEMA-AUTHOR-SAMEAS-004"]
    assert len(author_findings) == 1, f"Expected 1 deduplicated author finding, got {len(author_findings)}"

    # 7. Scoring improvements: H1 split & GEO baseline on error
    lb = LedgerBuilder("https://example.com")
    lb.set_raw(200, {}, "<html></html>", 10.0)
    # Test > 1 H1 has 0 penalty (informational recommendation)
    lb.add_evidence(
        rule_id="TECH-H1-OUTLINE-005",
        category="technical",
        title="H1 Heading Count",
        status="INFO",
        confidence=CONFIDENCE_VERIFIED,
        observed="2 H1 headings",
        expected="1 H1 heading recommended",
        message="Multiple H1s"
    )
    test_scores = calculate_scores(lb.build())
    assert test_scores.observable_technical_score == 100, f"Expected 100 for >1 H1, got {test_scores.observable_technical_score}"

    # Test error response gets 0 GEO readiness index
    lb_err = LedgerBuilder("https://example.com")
    lb_err.set_raw(404, {}, "", 10.0)
    lb_err.add_signal("http_status_code", "HTTP Status", 404)
    lb_err.add_signal("content_total_words", "Word Count", 0)
    err_scores = calculate_scores(lb_err.build())
    assert err_scores.geo_readiness_index == 0, f"Expected 0 GEO score on 404, got {err_scores.geo_readiness_index}"

    # 8. Russian content fluff and pronoun leads
    ru_fluff_content = "В современном мире каждый задумывается о технологиях.\n\nЭто очень важная тема для каждого пользователя."
    c_res = analyze_content(ru_fluff_content)
    assert c_res.opening_has_fluff is True
    assert c_res.pronoun_lead_count >= 1

    print("[PASS] test_audit_v2_16_fixes")


def test_week1_foundation_edge_cases():
    """
    Validates all 11 Week 1 Foundation edge cases from todo.md:
    1. Multiple canonicals
    2. Canonical in <body>
    3. Relative canonical
    4. Canonical with fragment (#) and query params
    5. Scoped noindex in meta and X-Robots-Tag
    6. Complex robots.txt groups
    7. Allow/Disallow of identical length (Allow wins)
    8. Empty CSR shell
    9. WAF challenge page
    10. HTML without <main>
    11. Page without text but with valid Schema
    """
    from engine.analyzers.html_analyzer import analyze_target_html
    from engine.analyzers.robots_simulator import parse_robots_txt, is_allowed
    from unittest.mock import patch

    # 1. Multiple canonical tags in <head>
    html_multi_canon = """<!DOCTYPE html>
<html><head>
    <title>Multiple Canonicals Test</title>
    <link rel="canonical" href="https://example.com/canonical-1">
    <link rel="canonical" href="https://example.com/canonical-2">
</head><body><h1>Heading</h1></body></html>"""
    fd1, path1 = tempfile.mkstemp(suffix=".html")
    with open(fd1, "w", encoding="utf-8") as f:
        f.write(html_multi_canon)
    try:
        ledger1, scores1 = run_inspection(path1)
        ev1 = next(e for e in ledger1.evidence if e.rule_id == "TECH-CANONICAL-001")
        assert ev1.status == "CRITICAL", f"Expected CRITICAL for multiple canonicals, got {ev1.status}"
        assert "Multiple canonical tags" in ev1.message
    finally:
        os.remove(path1)

    # 2. Canonical in <body>
    html_body_canon = """<!DOCTYPE html>
<html><head><title>Canonical in Body Test</title></head>
<body>
    <link rel="canonical" href="https://example.com/body-canon">
    <h1>Heading</h1>
</body></html>"""
    fd2, path2 = tempfile.mkstemp(suffix=".html")
    with open(fd2, "w", encoding="utf-8") as f:
        f.write(html_body_canon)
    try:
        ledger2, scores2 = run_inspection(path2)
        ev2 = next(e for e in ledger2.evidence if e.rule_id == "TECH-CANONICAL-001")
        assert ev2.status == "WARNING"
        assert "<body>" in str(ev2.observed) or "body" in ev2.message.lower()
    finally:
        os.remove(path2)

    # 3. Relative canonical
    html_rel_canon = """<!DOCTYPE html>
<html><head>
    <title>Relative Canonical Test</title>
    <link rel="canonical" href="/relative-path">
</head><body><h1>Heading</h1></body></html>"""
    fd3, path3 = tempfile.mkstemp(suffix=".html")
    with open(fd3, "w", encoding="utf-8") as f:
        f.write(html_rel_canon)
    try:
        ledger3, scores3 = run_inspection(path3)
        ev3 = next(e for e in ledger3.evidence if e.rule_id == "TECH-CANONICAL-001")
        assert ev3.status == "WARNING"
        assert "relative" in ev3.message.lower()
    finally:
        os.remove(path3)

    # 4. Canonical with fragment (#) and query params
    html_frag_canon = """<!DOCTYPE html>
<html><head>
    <title>Fragment Canonical Test</title>
    <link rel="canonical" href="https://example.com/page#section?utm_source=test">
</head><body><h1>Heading</h1></body></html>"""
    fd4, path4 = tempfile.mkstemp(suffix=".html")
    with open(fd4, "w", encoding="utf-8") as f:
        f.write(html_frag_canon)
    try:
        ledger4, scores4 = run_inspection(path4)
        ev4 = next(e for e in ledger4.evidence if e.rule_id == "TECH-CANONICAL-001")
        assert ev4.status == "WARNING"
        assert "fragment" in ev4.message.lower()
    finally:
        os.remove(path4)

    # 5. Scoped noindex in meta and X-Robots-Tag
    html_scoped_meta = """<!DOCTYPE html>
<html><head>
    <title>Scoped Meta Noindex Test</title>
    <meta name="googlebot" content="noindex, follow">
</head><body><h1>Heading</h1></body></html>"""
    parsed_scoped = analyze_target_html(html_scoped_meta)
    assert parsed_scoped["meta_robots"]["googlebot"] == "noindex, follow"

    mock_scoped_http = {
        "target": "https://example.com/scoped",
        "final_url": "https://example.com/scoped",
        "is_local": False,
        "status_code": 200,
        "headers": {"content-type": "text/html"},
        "raw_content": "<html><head><title>Scoped Header Test</title></head><body><h1>Heading</h1></body></html>",
        "response_time_ms": 100.0,
        "tls_valid": True,
        "redirect_chain": [],
        "x_robots_directives": ["googlebot: noindex"],
        "x_robots_bot_directives": {"googlebot": ["noindex"]},
        "error": None
    }
    with patch("engine.inspector.analyze_target_http", return_value=mock_scoped_http):
        ledger5, scores5 = run_inspection("https://example.com/scoped")
        ev5 = next((e for e in ledger5.evidence if e.rule_id == "TECH-NOINDEX-009"), None)
        assert ev5 is not None
        assert ev5.status == "CRITICAL"
        assert "googlebot" in str(ev5.observed).lower()

    # 6. Complex robots.txt groups
    complex_robots = """
User-agent: Googlebot
Allow: /public/
Disallow: /admin/

User-agent: Claude-SearchBot
Disallow: /no-claude/

User-agent: *
Disallow: /secret/
"""
    r_data = parse_robots_txt(complex_robots)
    # Googlebot uses Googlebot group
    allow_gb_pub, _, _ = is_allowed(r_data, "Googlebot", "/public/file")
    allow_gb_adm, _, _ = is_allowed(r_data, "Googlebot", "/admin/file")
    allow_gb_sec, _, _ = is_allowed(r_data, "Googlebot", "/secret/file")
    assert allow_gb_pub is True
    assert allow_gb_adm is False
    assert allow_gb_sec is True  # Googlebot group overrides wildcard!

    # Claude-SearchBot uses Claude-SearchBot group
    allow_csb_nc, _, _ = is_allowed(r_data, "Claude-SearchBot", "/no-claude/file")
    assert allow_csb_nc is False

    # OtherBot uses wildcard
    allow_ob_sec, _, _ = is_allowed(r_data, "OtherBot", "/secret/file")
    allow_ob_adm, _, _ = is_allowed(r_data, "OtherBot", "/admin/file")
    assert allow_ob_sec is False
    assert allow_ob_adm is True

    # 7. Allow / Disallow of identical length: RFC 9309 Allow precedence
    tie_robots = """
User-agent: *
Disallow: /catalog
Allow: /catalog
"""
    r_tie = parse_robots_txt(tie_robots)
    allowed_tie, rule_tie, reason_tie = is_allowed(r_tie, "Googlebot", "/catalog/item-123")
    assert allowed_tie is True, f"Allow must take precedence on equal length, got reason: {reason_tie}"
    assert rule_tie is not None and rule_tie.allow is True

    # 8. Empty CSR shell
    html_csr = """<!DOCTYPE html>
<html><head><title>CSR App</title><script src="/bundle.js"></script></head>
<body><div id="root"></div></body></html>"""
    fd8, path8 = tempfile.mkstemp(suffix=".html")
    with open(fd8, "w", encoding="utf-8") as f:
        f.write(html_csr)
    try:
        ledger8, scores8 = run_inspection(path8)
        rule_ids8 = {f.rule_id for f in ledger8.findings}
        assert "TECH-CSR-SHELL-008" in rule_ids8
    finally:
        os.remove(path8)

    # 9. WAF / Cloudflare challenge page detection
    mock_waf = {
        "target": "https://example.com/protected",
        "final_url": "https://example.com/protected",
        "is_local": False,
        "status_code": 403,
        "headers": {"content-type": "text/html", "server": "cloudflare"},
        "raw_content": "<html><head><title>Just a moment... Attention Required! | Cloudflare</title></head><body><div id='cf-browser-verification'></div></body></html>",
        "response_time_ms": 150.0,
        "tls_valid": True,
        "redirect_chain": [],
        "x_robots_directives": [],
        "x_robots_bot_directives": {},
        "is_challenge_page": True,
        "error": None
    }
    with patch("engine.inspector.analyze_target_http", return_value=mock_waf):
        ledger9, scores9 = run_inspection("https://example.com/protected")
        # Ensure 403 error is detected but NOT falsely flagged as client-side CSR shell
        assert any(e.rule_id == "TECH-HTTP-STATUS-000" for e in ledger9.evidence)
        assert not any(e.rule_id == "TECH-CSR-SHELL-008" and e.status == "CRITICAL" for e in ledger9.evidence)

    # 10. HTML without <main> element
    html_no_main = """<!DOCTYPE html>
<html lang="en"><head><title>No Main Tag</title></head>
<body><header>Header</header><div class="content"><p>Some body content text.</p></div><footer>Footer</footer></body></html>"""
    parsed_no_main = analyze_target_html(html_no_main)
    assert parsed_no_main["has_main"] is False
    assert parsed_no_main["word_count"] > 0

    # 11. Page without text, but with valid Schema.org graph
    html_textless_schema = """<!DOCTYPE html>
<html lang="en">
<head>
    <title>Textless Page With Schema</title>
    <link rel="canonical" href="https://example.com/schema-only">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "WebSite",
          "@id": "https://example.com/#website",
          "name": "Schema Only Site"
        },
        {
          "@type": "WebPage",
          "@id": "https://example.com/schema-only#webpage",
          "name": "Schema Only Page",
          "isPartOf": {"@id": "https://example.com/#website"}
        }
      ]
    }
    </script>
</head>
<body>
</body>
</html>"""
    fd11, path11 = tempfile.mkstemp(suffix=".html")
    with open(fd11, "w", encoding="utf-8") as f:
        f.write(html_textless_schema)
    try:
        ledger11, scores11 = run_inspection(path11)
        # GEO readiness must be 0 due to 0 content words
        assert scores11.geo_readiness_index == 0
        # Schema graph passed
        schema_ev = next(e for e in ledger11.evidence if e.rule_id == "SCHEMA-GRAPH-INTERCONNECT-002")
        assert schema_ev.status == "PASS"
        # 0 images means TECH-IMG-ALT-010 is NOT_APPLICABLE
        img_ev = next(e for e in ledger11.evidence if e.rule_id == "TECH-IMG-ALT-010")
        assert img_ev.status == "NOT_APPLICABLE"
        assert scores11.criteria_not_applicable >= 1
    finally:
        os.remove(path11)

    print("[PASS] test_week1_foundation_edge_cases")


def test_week2_indexability_and_security():
    import tempfile
    import os
    from engine.indexability import evaluate_indexability_matrix, VERDICT_INDEXABLE, VERDICT_BLOCKED, VERDICT_AMBIGUOUS
    from engine.inspector import run_inspection
    from engine.analyzers.sitemap_analyzer import parse_sitemap_xml

    # 1. Direct Indexability Matrix Unit Tests
    # A. Clean Indexable
    mat_clean = evaluate_indexability_matrix(
        target_url="https://example.com/page",
        http_res={"status_code": 200, "is_local": False, "redirect_chain": [], "x_robots_directives": []},
        html_data={
            "canonical": {"value": "https://example.com/page", "count": 1, "in_body": False},
            "meta_robots": {"is_noindex": False},
            "links": {"internal_count": 5},
            "csr_detection": {"is_csr_shell": False},
            "word_count": 150
        }
    )
    assert mat_clean.verdict == VERDICT_INDEXABLE
    assert mat_clean.to_dict()["confidence_score"] == 100

    # B. Blocked via Soft 404
    mat_soft = evaluate_indexability_matrix(
        target_url="https://example.com/page",
        http_res={"status_code": 200, "is_soft_404": True, "redirect_chain": []},
        html_data={"canonical": {"value": "https://example.com/page", "count": 1}}
    )
    assert mat_soft.verdict == VERDICT_BLOCKED
    assert "soft_404" in mat_soft.rendered_content_status

    # C. Ambiguous via Canonical to Other URL
    mat_other = evaluate_indexability_matrix(
        target_url="https://example.com/page-variant",
        http_res={"status_code": 200, "redirect_chain": []},
        html_data={"canonical": {"value": "https://example.com/primary-page", "count": 1}, "links": {"internal_count": 2}}
    )
    assert mat_other.verdict == VERDICT_AMBIGUOUS
    assert mat_other.canonical_status == "other"

    # 2. Sitemap 50k URL Limit
    sitemap_header = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    sitemap_footer = '</urlset>'
    sitemap_body = "".join(f"<url><loc>https://example.com/page/{i}</loc></url>" for i in range(50005))
    large_sitemap = sitemap_header + sitemap_body + sitemap_footer
    sm_res = parse_sitemap_xml(large_sitemap, base_domain="example.com")
    assert sm_res.exceeds_url_limit is True
    assert sm_res.total_urls == 50005
    assert any("50,000" in w for w in sm_res.warnings)

    # 3. Full Inspector Week 2 Rules Verification (Trailing slash, WWW, Anchor text, Form labels, Landmarks, Security)
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Week 2 Comprehensive Audit Verification</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="canonical" href="https://example.com/test-page/">
</head>
<body>
    <header><h1>Primary Topic Headline</h1></header>
    <main>
        <h2>Section Two</h2>
        <p>This is substantive main content for search and AI discovery engines with sufficient words to establish context and verify indexability rules.</p>
        <a href="https://example.com/target"></a>
        <a href="https://example.com/target2">Valid Anchor Link</a>
        <form>
            <input type="text" name="unlabelled_field">
            <input type="text" id="labelled_field" name="field2">
            <label for="labelled_field">Field 2 Label</label>
        </form>
    </main>
    <footer><p>Footer content</p></footer>
</body>
</html>"""
    fd, path = tempfile.mkstemp(suffix=".html")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(html_content)

    try:
        from unittest.mock import patch
        mock_http = {
            "target": "https://example.com/test-page",
            "final_url": "https://example.com/test-page",
            "is_local": False,
            "status_code": 200,
            "headers": {
                "content-type": "text/html; charset=utf-8",
                "strict-transport-security": "max-age=31536000; includeSubDomains",
                "content-encoding": "gzip",
                "cache-control": "public, max-age=3600",
                "x-content-type-options": "nosniff",
                "x-frame-options": "DENY",
                "content-security-policy": "default-src 'self'",
                "referrer-policy": "strict-origin-when-cross-origin"
            },
            "raw_content": html_content,
            "response_time_ms": 80.0,
            "tls_valid": True,
            "redirect_chain": [],
            "x_robots_directives": [],
            "x_robots_bot_directives": {},
            "error": None,
            "is_soft_404": False,
            "has_redirect_loop": False,
            "is_challenge_page": False
        }

        with patch("engine.inspector.analyze_target_http", return_value=mock_http):
            ledger, scores = run_inspection("https://example.com/test-page")

            # Check Security Hygiene Score: HTTPS (25) + HSTS (25) + No mixed content (25) + 4 Security headers (25) = 100
            assert scores.security_score == 100
            assert scores.security_tier == "EXCELLENT"
            assert scores.security_hygiene is not None
            assert scores.security_hygiene.hsts_score == 25
            assert scores.security_hygiene.mixed_content_score == 25

            # Rule TECH-CANONICAL-TRAILING-019 (requested /test-page vs canonical /test-page/)
            rule_ids = {e.rule_id: e for e in ledger.evidence}
            assert "TECH-CANONICAL-TRAILING-019" in rule_ids
            assert rule_ids["TECH-CANONICAL-TRAILING-019"].status == "WARNING"

            # Rule TECH-LINK-ANCHOR-028 (1 empty anchor link)
            assert "TECH-LINK-ANCHOR-028" in rule_ids
            assert rule_ids["TECH-LINK-ANCHOR-028"].status == "WARNING"

            # Rule TECH-FORM-LABEL-029 (1 unlabelled input)
            assert "TECH-FORM-LABEL-029" in rule_ids
            assert rule_ids["TECH-FORM-LABEL-029"].status == "WARNING"

            # Rule TECH-LANDMARKS-030 (<main> present)
            assert "TECH-LANDMARKS-030" in rule_ids
            assert rule_ids["TECH-LANDMARKS-030"].status == "PASS"

            # Rule PERF-COMPRESSION-021 (gzip)
            assert "PERF-COMPRESSION-021" in rule_ids
            assert rule_ids["PERF-COMPRESSION-021"].status == "PASS"

            # Indexability Matrix present in metadata and score breakdown
            assert scores.indexability_matrix is not None
            assert scores.indexability_matrix["verdict"] in (VERDICT_INDEXABLE, VERDICT_AMBIGUOUS)
    finally:
        os.remove(path)

    print("[PASS] test_week2_indexability_and_security")


if __name__ == "__main__":
    print("Running Engine v2.1.0 integration suite...")
    test_clean_page_inspection()
    test_defective_page_detection()
    test_robots_simulator_rfc9309()
    test_unknown_signal_invariant()
    test_csr_shell_detection()
    test_schema_standalone_validator()
    test_canonical_hardening()
    test_noindex_detection()
    test_sitemap_analyzer()
    test_schema_empty_and_calendar_validation()
    test_http_status_blocking_and_coverage()
    test_sitemap_analyzer_inspector_integration()
    test_audit_v2_16_fixes()
    test_week1_foundation_edge_cases()
    test_week2_indexability_and_security()
    print("All Engine v2.1.0 tests passed successfully!")
