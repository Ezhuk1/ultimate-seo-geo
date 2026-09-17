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
    # Test > 1 H1 has 0 penalty
    lb.add_evidence(
        rule_id="TECH-H1-OUTLINE-005",
        category="technical",
        title="H1 Heading Count",
        status=STATUS_WARNING,
        confidence=CONFIDENCE_VERIFIED,
        observed="2 H1 headings",
        expected="Exactly 1 H1 heading",
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
    print("All Engine v2.1.0 tests passed successfully!")
