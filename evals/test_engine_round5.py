#!/usr/bin/env python3
"""
Deterministic regression suite for round-5 GEO capabilities (v3.8.1).
Run: python evals/test_engine_round5.py
Covers: AI-slop density detection, content-blocking overlays & cookie walls,
category-for-audience definition pattern, version sync.
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


SLOP_HTML = (
    "<!DOCTYPE html><html><head><title>Slop Fixture</title></head><body><main>"
    "<h1>Innovative Solutions</h1>"
    "<p>We are a cutting-edge, industry-leading provider of comprehensive suite services. "
    "Our seamless platform will empower your business and unlock the power of synergy "
    "in today's fast-paced world. 🚀 ✨ 💡</p>"
    + ("<p>Our holistic approach is revolutionary and game-changing, delivering robust platform "
       "value for your wide range of services. 🚀 ✨ Our unparalleled team of professionals "
       "offers best-in-class quality.</p> " * 12)
    + "</main></body></html>"
)

COOKIE_WALL_HTML = (
    "<!DOCTYPE html><html><head><title>Cookie Wall Fixture</title></head><body><main>"
    "<h1>Article</h1>"
    "<p>This article explains the topic in plain words with a direct answer near the top "
    "for readers and crawlers alike.</p>"
    "<div id=\"cookie-consent-wall\" class=\"consent interstitial\">We use cookies</div>"
    "<p>More paragraph content follows here with enough words to pass thin-content "
    "thresholds for analysis and keeps the page above the applicable size.</p>"
    "</main></body></html>"
)

GENERIC_MODAL_HTML = (
    "<!DOCTYPE html><html><head><title>Modal Fixture</title></head><body><main>"
    "<h1>Article</h1>"
    "<p>This article explains the topic in plain words with a direct answer near the top "
    "for readers and crawlers alike.</p>"
    "<dialog id=\"video-lightbox\"><p>Video player placeholder content lives here.</p></dialog>"
    "<p>More paragraph content follows here with enough words to pass thin-content "
    "thresholds for analysis and keeps the page above the applicable size.</p>"
    "</main></body></html>"
)

CLEAN_HTML = (
    "<!DOCTYPE html><html><head><title>Clean Fixture</title></head><body><main>"
    "<h1>WidgetFlow</h1>"
    "<p>WidgetFlow is an invoice-matching tool for finance teams that reconciles supplier "
    "invoices against purchase orders. It reduced escalations by 31% at Acme, according to "
    "our 2025 telemetry of 120 users.</p>"
    + ("<p>Filler supporting context paragraph for the clean fixture body text.</p> " * 14)
    + "</main></body></html>"
)


def _run_fixture(html: str):
    from engine.inspector import run_inspection
    tf = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    tf.write(html)
    tf.close()
    try:
        ledger, score = run_inspection(tf.name)
        ev = {e.rule_id: e.status for e in ledger.evidence}
        fids = [f.rule_id for f in ledger.findings]
        return ev, fids, score
    finally:
        os.unlink(tf.name)


def test_slop_detection_units():
    from engine.analyzers.content_analyzer import analyze_slop_patterns, analyze_audience_definition
    heavy = ("We are a cutting-edge, industry-leading provider. Our seamless platform will "
             "empower you and unlock the power of synergy. ") * 12
    r = analyze_slop_patterns(heavy)
    check("slop: high density detected", r["applicable"] and r["verdict"] == "HIGH" and r["hit_count"] >= 10)
    clean = "We reduced invoice escalations by 31% at Acme in 2025, according to our telemetry of 120 users. " * 6
    r2 = analyze_slop_patterns(clean)
    check("slop: clean factual text passes", r2["verdict"] == "LOW" and r2["hit_count"] == 0)
    short = "short page"
    r3 = analyze_slop_patterns(short)
    check("slop: short page not applicable", r3["applicable"] is False)
    a = analyze_audience_definition("WidgetFlow is an invoice-matching tool for finance teams that reconciles invoices.")
    check("entity-def: EN category-for-audience found", a["found"] is True)
    a2 = analyze_audience_definition("Наш сервис — это комплексное решение для маркетинговых команд, которое ускоряет отчётность.")
    check("entity-def: RU category-for-audience found", a2["found"] is True)
    a3 = analyze_audience_definition("The system uses a queue to process events in order of arrival.")
    check("entity-def: non-definition sentence not matched", a3["found"] is False)


def test_interstitial_units():
    from engine.analyzers.html_analyzer import analyze_target_html
    r = analyze_target_html(COOKIE_WALL_HTML, base_url="https://x.com/")
    sig = r.get("interstitial_signals", {})
    check("interstitial: named wall markers captured", "cookie" in sig.get("named_walls", []) and "consent" in sig.get("named_walls", []))
    r2 = analyze_target_html(GENERIC_MODAL_HTML, base_url="https://x.com/")
    sig2 = r2.get("interstitial_signals", {})
    check("interstitial: dialog captured, no named walls",
          sig2.get("dialog_elements", 0) == 1 and not sig2.get("named_walls"))
    r3 = analyze_target_html(CLEAN_HTML, base_url="https://x.com/")
    sig3 = r3.get("interstitial_signals", {})
    check("interstitial: clean page has no overlay signals",
          not sig3.get("named_walls") and sig3.get("dialog_elements", 0) == 0)


def test_evidence_blocks():
    ev, fids, score = _run_fixture(SLOP_HTML)
    check("slop: WARNING evidence on slop-heavy page", ev.get("GEO-SLOP-DETECT-026") == "WARNING")
    check("slop: finding raised", "GEO-SLOP-DETECT-026" in fids)

    ev2, fids2, _ = _run_fixture(COOKIE_WALL_HTML)
    check("interstitial: WARNING on cookie wall", ev2.get("TECH-INTERSTITIAL-040") == "WARNING")
    check("interstitial: finding raised on cookie wall", "TECH-INTERSTITIAL-040" in fids2)

    ev3, fids3, _ = _run_fixture(GENERIC_MODAL_HTML)
    check("interstitial: INFO on generic modal (no false positive)",
          ev3.get("TECH-INTERSTITIAL-040") in ("INFO", "PASS"))
    check("interstitial: no finding on generic modal", "TECH-INTERSTITIAL-040" not in fids3)

    ev4, fids4, _ = _run_fixture(CLEAN_HTML)
    check("interstitial: PASS on clean page", ev4.get("TECH-INTERSTITIAL-040") == "PASS")
    check("slop: PASS on clean factual page", ev4.get("GEO-SLOP-DETECT-026") == "PASS")
    check("entity-def: PASS on category-for-audience opening", ev4.get("GEO-ENTITY-DEFINITION-027") == "PASS")


def test_version_sync():
    import engine
    check("version: engine __version__ == 3.8.1", engine.__version__ == "3.8.1")
    rules_geo = json.load(open("rules/geo_rules.json", encoding="utf-8"))
    ids = {r["id"] for r in rules_geo["rules"]}
    check("rules: round-5 geo rules registered",
          {"GEO-SLOP-DETECT-026", "GEO-ENTITY-DEFINITION-027"} <= ids)
    rules_tech = json.load(open("rules/technical_rules.json", encoding="utf-8"))
    tids = {r["id"] for r in rules_tech["rules"]}
    check("rules: TECH-INTERSTITIAL-040 registered", "TECH-INTERSTITIAL-040" in tids)
    # Epistemic integrity: slop heuristic must stay Tier E
    slop_rule = next(r for r in rules_geo["rules"] if r["id"] == "GEO-SLOP-DETECT-026")
    check("epistemic: slop rule is Tier E", slop_rule["tier"].startswith("Tier E"))
    inter_rule = next(r for r in rules_tech["rules"] if r["id"] == "TECH-INTERSTITIAL-040")
    check("epistemic: interstitial rule is Tier B", inter_rule["tier"].startswith("Tier B"))


if __name__ == "__main__":
    print("--- Round-5 capability regression suite ---")
    test_slop_detection_units()
    test_interstitial_units()
    test_evidence_blocks()
    test_version_sync()
    if PASS:
        print("[SUCCESS] all round-5 capability checks passed")
        sys.exit(0)
    print("[FAILURE] one or more round-5 checks failed")
    sys.exit(1)
