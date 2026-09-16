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
from engine.scoring import calculate_scores


def test_clean_page_inspection():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <title>Ultimate SEO &amp; GEO Engine Test Page</title>
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


if __name__ == "__main__":
    print("Running Engine v2.1.0 integration suite...")
    test_clean_page_inspection()
    test_defective_page_detection()
    test_robots_simulator_rfc9309()
    test_unknown_signal_invariant()
    test_csr_shell_detection()
    test_schema_standalone_validator()
    print("All Engine v2.1.0 tests passed successfully!")
