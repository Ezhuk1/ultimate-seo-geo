#!/usr/bin/env python3
"""
Deterministic regression suite for round-4 GEO capabilities (v3.7.0).
Run: python evals/test_engine_round4.py
Covers: WAF challenge signature, CSR fallback, citation anchors,
section pyramid, information gain, schema entity connectivity,
llms-full probe/generator, version sync.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS = True


def check(name: str, cond: bool) -> None:
    global PASS
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        PASS = False


FIXTURE_HTML = (
    "<!DOCTYPE html><html><head><title>Round 4 Capability Fixture</title>"
    '<meta name="description" content="Fixture for round-4 engine capabilities."></head>'
    "<body><main>"
    "<h1>Round 4 Fixture</h1>"
    '<h2 id="benchmark">Benchmark results</h2>'
    "<p>We tested the system and got 42% faster responses. We measured latency across 3 setups: "
    "the baseline averaged 120 ms, our setup averaged 70 ms. Formula: speedup = 120 / 70 = 1.71.</p>"
    + ("<p>Filler sentence with generic content for the benchmark section body.</p> " * 8)
    + "<h2>Unanchored section heading</h2>"
    "<p>In today's fast-paced world everything changes. Content follows without any numbers, "
    "definitions or citation cues, just narrative background sentences that bury the claim.</p>"
    + ("<p>Additional filler narrative for the unanchored weak section body text.</p> " * 8)
    + ("<p>Additional neutral paragraph with supporting context for the benchmark narrative body.</p> " * 10)    + "<h3 id="'"specs"'">Specifications</h3>"
    "<table><tr><th>Param</th><tr><td>Value</td></table>"
    "<noscript><p>Static fallback with the price 199 rubles, key specs and the main answer for crawlers without JS rendering.</p></noscript>"
    '<script type="application/ld+json">{"@context":"https://schema.org","@graph":['
    '{"@type":"Organization","@id":"#org","name":"Acme"},'
    '{"@type":"Article","@id":"#art","headline":"T","author":{"@id":"#person"},"publisher":{"@id":"#org"}},'
    '{"@type":"Person","@id":"#person","name":"Jane","sameAs":["https://linkedin.com/in/jane"]}]}'
    "</script>"
    "</main></body></html>"
)


def _run_fixture():
    from engine.inspector import run_inspection
    tf = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    tf.write(FIXTURE_HTML)
    tf.close()
    try:
        return run_inspection(tf.name)
    finally:
        os.unlink(tf.name)


def test_waf_signature():
    from engine.inspector import _bot_challenge_signature as sig
    check("waf: 403 detected", sig(403, {}, "ok") == "HTTP 403")
    check("waf: cf-mitigated header detected",
          sig(200, {"cf-mitigated": "challenge"}, "x") == "cf-mitigated: challenge")
    check("waf: interstitial body detected",
          sig(200, {}, "Just a moment...") is not None)
    check("waf: turnstile marker detected", sig(200, {}, "widget turnsTile load") is not None)
    check("waf: clean 200 page passes", sig(200, {}, "<p>real content</p>") is None)


def test_llms_full_generator():
    from engine.analyzers.llms_analyzer import generate_llms_full_txt
    md = generate_llms_full_txt("Site", [
        {"title": "Page One", "url": "https://x.com/a", "text": "Alpha content."},
        {"title": "Page Two", "url": "https://x.com/b", "text": ""},
    ])
    check("llms-full: title header present", "# Site — Full Content Dump" in md)
    check("llms-full: page section rendered", "## Page One" in md and "Source: https://x.com/a" in md)
    check("llms-full: empty-text pages skipped", "Page Two" not in md.split("Alpha content.")[-1])


def test_evidence_blocks():
    led, scores = _run_fixture()
    ev = {e.rule_id: e.status for e in led.evidence}
    fids = [f.rule_id for f in led.findings]

    check("round4: WAF probe skipped on local file (no evidence)",
          "GEO-WAF-BOT-ACCESS-021" not in ev)

    check("round4: CSR fallback evidence present", "GEO-CSR-FALLBACK-022" in ev)
    check("round4: CSR fallback PASS on meaningful noscript",
          ev.get("GEO-CSR-FALLBACK-022") in ("PASS", "INFO"))

    check("round4: anchors evidence present", "GEO-ANCHOR-DEEPLINK-023" in ev)

    check("round4: section pyramid evidence present", "GEO-SECTION-PYRAMID-024" in ev)

    check("round4: info gain evidence present", "GEO-INFO-GAIN-025" in ev)
    check("round4: info gain triggers found (we tested / 42%)",
          ev.get("GEO-INFO-GAIN-025") in ("PASS", "INFO"))

    check("round4: schema entity connectivity PASS (linked graph)",
          ev.get("SCHEMA-ENTITY-LINK-026") == "PASS")
    check("round4: schema connectivity finding not raised", "SCHEMA-ENTITY-LINK-026" not in fids)


def test_headings_with_ids():
    from engine.analyzers.html_analyzer import analyze_target_html
    result = analyze_target_html(FIXTURE_HTML, base_url="https://x.com/")
    outline = result.get("headings", {}).get("outline", [])
    ids = [h.get("id") for h in outline if h.get("level") in (2, 3)]
    check("html: heading ids captured (benchmark, specs)", "benchmark" in ids and "specs" in ids)
    check("html: unanchored heading has empty id", any(i == "" for i in ids))
    ns = result.get("noscript", {})
    check("html: noscript text captured", ns.get("count", 0) >= 1 and ns.get("total_words", 0) >= 10)


def test_section_pyramid_units():
    from engine.analyzers.content_analyzer import analyze_section_pyramid, analyze_information_gain
    heads = [{"level": 2, "text": "Alpha Section"}, {"level": 2, "text": "Beta Section"}]
    strong = ("Alpha Section We tested the system and got 42% faster responses. " + "detail " * 60 +
              "Beta Section This is a benchmark: a definition designed to explain the outcome. " + "detail " * 60)
    r1 = analyze_section_pyramid(strong, heads)
    check("pyramid: both sections frontloaded", r1["sections_frontloaded"] == 2)
    weak = ("Alpha Section " + "narrative word " * 60 +
            "Beta Section " + "narrative word " * 60)
    r2 = analyze_section_pyramid(weak, heads)
    check("pyramid: weak sections detected", len(r2["weak_sections"]) == 2)
    ig = analyze_information_gain("In today's fast-paced world of digital landscape, nothing concrete. " * 6)
    check("info-gain: water phrase detected, no triggers",
          ig["trigger_count"] == 0 and len(ig["water_phrases"]) >= 1)


def test_version_sync():
    import engine
    check("version: engine __version__ == 3.8.1", engine.__version__ == "3.8.1")
    cfg_src = open("engine/config.py", encoding="utf-8").read()
    check("version: no stale 3.6.0 in config", "3.6.0" not in cfg_src)
    rules_geo = json.load(open("rules/geo_rules.json", encoding="utf-8"))
    ids = {r["id"] for r in rules_geo["rules"]}
    check("rules: new geo rules registered",
          {"GEO-WAF-BOT-ACCESS-021", "GEO-CSR-FALLBACK-022", "GEO-ANCHOR-DEEPLINK-023",
           "GEO-SECTION-PYRAMID-024", "GEO-INFO-GAIN-025", "GEO-LLMS-FULL-020"} <= ids)


if __name__ == "__main__":
    print("--- Round-4 capability regression suite ---")
    test_waf_signature()
    test_llms_full_generator()
    test_evidence_blocks()
    test_headings_with_ids()
    test_section_pyramid_units()
    test_version_sync()
    if PASS:
        print("[SUCCESS] all round-4 capability checks passed")
        sys.exit(0)
    print("[FAILURE] one or more round-4 checks failed")
    sys.exit(1)
