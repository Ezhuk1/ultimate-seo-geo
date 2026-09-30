#!/usr/bin/env python3
"""
Deterministic regression suite for the external-audit round 2 hardening fixes.
Run: python evals/test_engine_round2.py
Covers:
  1. Freshness analyzer no longer crashes on unparseable schema dates (exit-code guard).
  2. SSRF validator: userinfo netloc ("http://x@127.0.0.1/"), localhost. and *.localhost.
  3. scoring.ScoreBreakdown survives typing.get_type_hints (Optional import).
  4. Percentage/number patterns: "68% of users", "68%", "68 %", "250 000".
  5. E-E-A-T: author {"@id"} reference resolution, sameAs hostname match, @type lists.
  6. robots.txt: UTF-8 BOM, empty Disallow, "User agent:" variant, percent-encoding,
     linear glob matcher (ReDoS-proof, RFC 9309 longest-match/tie-break preserved).
  7. Sitemap: W3C-truncated lastmod formats, future-date threshold.
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS = True


def check(name: str, cond: bool) -> None:
    global PASS
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        PASS = False


def test_freshness_invalid_date_no_crash():
    import subprocess
    import tempfile
    import os
    html = (
        '<!DOCTYPE html><html><head><title>T</title></head><body><main><h1>H</h1>'
        '<p>Enough readable body text for the analyzer to proceed normally.</p></main>'
        '<script type="application/ld+json">{"@context":"https://schema.org","@graph":'
        '[{"@type":"Article","headline":"T","datePublished":"2024-13-45",'
        '"author":{"@type":"Person","name":"A"}}]}</script></body></html>'
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(html)
        path = tf.name
    try:
        r = subprocess.run(
            [sys.executable, "-m", "engine.inspector", path, "--format", "json"],
            capture_output=True, text=True, timeout=60,
        )
        check("freshness: invalid datePublished no longer crashes CLI (exit 0)", r.returncode == 0)
    finally:
        os.unlink(path)


def test_ssrf_validator():
    from engine.security_utils import is_safe_target_url
    ok, _ = is_safe_target_url("http://x@127.0.0.1/")
    check("SSRF: userinfo netloc rejected", not ok)
    ok, _ = is_safe_target_url("http://LOCALHOST./")
    check("SSRF: trailing-dot localhost rejected", not ok)
    ok, _ = is_safe_target_url("http://sub.localhost/")
    check("SSRF: *.localhost rejected", not ok)
    ok, _ = is_safe_target_url("https://example.com/some/page")
    check("SSRF: public https target allowed", ok)


def test_scoring_type_hints():
    import typing
    from engine.scoring import ScoreBreakdown
    try:
        typing.get_type_hints(ScoreBreakdown)
        check("scoring: get_type_hints(ScoreBreakdown) works", True)
    except Exception:
        check("scoring: get_type_hints(ScoreBreakdown) works", False)


def test_stat_patterns():
    from engine.analyzers.content_analyzer import PERCENTAGE_PATTERN, NUMERIC_STAT_PATTERN
    check("patterns: '68% of users' matched", bool(PERCENTAGE_PATTERN.search("68% of users")))
    check("patterns: '68%.' matched", bool(PERCENTAGE_PATTERN.search("Grew 68%.")))
    check("patterns: '68 %' matched", bool(PERCENTAGE_PATTERN.search("68 % growth")))
    check("patterns: '250 000' matched", bool(NUMERIC_STAT_PATTERN.search("250 000 users")))
    check("patterns: '25,000' still matched", bool(NUMERIC_STAT_PATTERN.search("25,000 users")))


def test_eeat():
    from engine.analyzers.eeat_analyzer import analyze_eeat
    graph = [
        {"@type": "Article", "headline": "T", "author": {"@id": "#p1"}},
        {"@type": "Person", "@id": "#p1", "name": "Real Author",
         "description": "A biography long enough for the checker",
         "sameAs": ["https://linkedin.com/in/real"]},
    ]
    r = analyze_eeat(visible_text="x", schema_entities=graph, links=[])
    check("EEAT: author @id reference resolved", r.author_name == "Real Author")
    check("EEAT: bio picked up via reference", r.has_author_bio)
    check("EEAT: trusted profile via reference", r.has_trusted_authority_profile)
    r2 = analyze_eeat(visible_text="x", schema_entities=[
        {"@type": "Person", "name": "A", "sameAs": ["https://evil.example/?p=linkedin.com"]}], links=[])
    check("EEAT: sameAs substring spoof rejected", not r2.has_trusted_authority_profile)
    r3 = analyze_eeat(visible_text="x", schema_entities=[
        {"@type": ["Person", "Author"], "name": "List Author",
         "sameAs": ["https://orcid.org/0000-0002-1825-0097"]}], links=[])
    check("EEAT: @type list recognized", r3.author_name == "List Author")
    check("EEAT: @type list sameAs trusted", r3.has_trusted_authority_profile)


def test_robots():
    from engine.analyzers.robots_simulator import parse_robots_txt, is_allowed
    r = parse_robots_txt("\ufeffUser-agent: *\nDisallow: /private/\n")
    check("robots: BOM parsed (1 rule)", sum(len(g.rules) for g in r.groups) == 1)
    check("robots: BOM disallow enforced", not is_allowed(r, "*", "/private/x")[0])

    r2 = parse_robots_txt("User-agent: *\nDisallow:\nDisallow: /\n")
    check("robots: empty Disallow does not neutralize Disallow: /",
          not is_allowed(r2, "*", "/page")[0])

    r3 = parse_robots_txt("User agent: BadBot\nDisallow: /\nUser-agent: *\nAllow: /\n")
    check("robots: 'User agent:' variant recognized",
          not is_allowed(r3, "BadBot", "/x")[0])

    r4 = parse_robots_txt("User-agent: *\nDisallow: /~user/\n")
    check("robots: percent-encoding normalized (/%7Euser/)",
          not is_allowed(r4, "*", "/%7Euser/x")[0] and not is_allowed(r4, "*", "/~user/x")[0])

    r5 = parse_robots_txt("User-agent: *\nDisallow: /private$\n")
    check("robots: $ anchor blocks exact", not is_allowed(r5, "*", "/private")[0])
    check("robots: $ anchor allows deeper path", is_allowed(r5, "*", "/private/x")[0])

    r6 = parse_robots_txt("User-agent: *\nDisallow: /blog/\nAllow: /blog/allowed/\n")
    check("robots: longest match preserved", not is_allowed(r6, "*", "/blog/x")[0]
          and is_allowed(r6, "*", "/blog/allowed/x")[0])
    r7 = parse_robots_txt("User-agent: *\nDisallow: /\nAllow: /\n")
    check("robots: equal length Allow wins", is_allowed(r7, "*", "/x")[0])

    pat = "/a" + "a*" * 40 + "b"
    r8 = parse_robots_txt(f"User-agent: *\nDisallow: {pat}\n")
    t0 = time.perf_counter()
    for _ in range(50):
        is_allowed(r8, "*", "/a" + "a" * 80 + "c")
    dt = time.perf_counter() - t0
    check(f"robots: 41-star pattern linear ({dt / 50 * 1000:.2f} ms avg, no ReDoS)",
          dt / 50 < 0.01)
    check("robots: multi-star still matches correctly",
          not is_allowed(r8, "*", "/a" + "a" * 42 + "b")[0])


def test_sitemap_lastmod():
    from engine.analyzers.sitemap_analyzer import parse_sitemap_xml

    def warnings_for(lm: str):
        xml = (f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               f'<url><loc>https://x.com/a</loc><lastmod>{lm}</lastmod></url></urlset>')
        r = parse_sitemap_xml(xml, sitemap_url="https://x.com/s.xml",
                              target_url="https://x.com/", base_domain="x.com", status_code=200)
        return r.warnings

    check("sitemap: W3C '2024' not 'Unparseable'",
          not any("Unparseable" in w for w in warnings_for("2024")))
    check("sitemap: W3C '2024-05' not 'Unparseable'",
          not any("Unparseable" in w for w in warnings_for("2024-05")))
    check("sitemap: future lastmod (2027-06-01) warned",
          any("Future" in w for w in warnings_for("2027-06-01")))


if __name__ == "__main__":
    print("--- Round-2 hardening regression suite ---")
    test_freshness_invalid_date_no_crash()
    test_ssrf_validator()
    test_scoring_type_hints()
    test_stat_patterns()
    test_eeat()
    test_robots()
    test_sitemap_lastmod()
    if PASS:
        print("[SUCCESS] all round-2 hardening checks passed")
        sys.exit(0)
    print("[FAILURE] one or more round-2 checks failed")
    sys.exit(1)
