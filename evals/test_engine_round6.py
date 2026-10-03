#!/usr/bin/env python3
"""
Deterministic regression suite for round-6 false-positive hardening (v3.8.1).
Run: python evals/test_engine_round6.py
Covers: noModule fallback scripts excluded from render-blocking accounting,
LCP hero candidate filtered by explicit image dimensions.
Root cause (bezmezhau.com, 2026-10-04): a 112x112 below-the-fold QR code was
flagged as "hero image with loading=lazy" and a legacy noModule polyfill chunk
was counted as a synchronous render-blocking script.
"""

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


PAGE_SHELL = (
    "<!DOCTYPE html><html><head>{head}<title>FP Fixture</title></head>"
    "<body><main><h1>WidgetFlow</h1>"
    "<p>WidgetFlow is an invoice-matching tool for finance teams that reconciles "
    "supplier invoices against purchase orders. {imgs}</p>"
    "<p>Filler supporting context paragraph keeps the fixture above thin-content "
    "thresholds so unrelated rules stay quiet.</p>"
    "</main></body></html>"
)


def _analyze(head: str, imgs: str):
    from engine.analyzers.html_analyzer import analyze_target_html
    html = PAGE_SHELL.format(head=head, imgs=imgs)
    return analyze_target_html(html, base_url="https://x.com/")


def _run_full(head: str, imgs: str):
    from engine.inspector import run_inspection
    html = PAGE_SHELL.format(head=head, imgs=imgs)
    tf = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    tf.write(html)
    tf.close()
    try:
        ledger, _score = run_inspection(tf.name)
        return {e.rule_id: e.status for e in ledger.evidence}
    finally:
        os.unlink(tf.name)


def test_nomodule_not_render_blocking():
    # Synchronous external script must still be flagged...
    r = _analyze('<script src="/_next/static/app.js"></script>', "")
    check("render-block: sync external script still flagged",
          r["performance_assets"]["render_blocking_js"] == ["/_next/static/app.js"])
    # ...but a noModule legacy fallback must not be counted: evergreen crawlers
    # never fetch it, so it cannot delay FCP/LCP.
    r2 = _analyze('<script src="/_next/static/polyfills.js" nomodule></script>', "")
    check("render-block: nomodule fallback excluded",
          r2["performance_assets"]["render_blocking_js"] == [])
    # async/defer and module scripts remain non-blocking (baseline regression).
    r3 = _analyze('<script src="/a.js" async></script><script src="/b.js" defer></script>'
                  '<script src="/c.js" type="module"></script>', "")
    check("render-block: async/defer/module still non-blocking",
          r3["performance_assets"]["render_blocking_js"] == [])
    # Escalation: multiple blocking stylesheets still warn end-to-end.
    ev4 = _run_full('<link rel="stylesheet" href="/a.css"><link rel="stylesheet" href="/b.css">', "")
    check("render-block: two blocking stylesheets still escalate to WARNING",
          ev4.get("PERF-RENDER-BLOCK-003") == "WARNING")


def test_hero_dimension_filter_units():
    # Explicitly tiny below-the-fold images (QR codes, icons) are not heroes.
    qr = '<img src="/qr-code.png" alt="QR" width="112" height="112" loading="lazy">'
    r = _analyze("", qr)
    check("hero: 112x112 QR not a hero candidate",
          r["performance_assets"]["hero_image"] is None)
    # Mixed sizes: tiny first image skipped, large eager/lazy image still a candidate.
    mixed = ('<img src="/qr.png" alt="QR" width="96" height="96" loading="lazy">'
             '<img src="/banner.jpg" alt="Banner" width="1200" height="630" loading="lazy">')
    r2 = _analyze("", mixed)
    hero2 = r2["performance_assets"]["hero_image"]
    check("hero: large image after tiny one still detected",
          hero2 is not None and hero2.get("src") == "/banner.jpg")
    # Undimensioned images remain candidates (Unknown != Failure): a cover
    # without width/height markup must not silently lose LCP guidance.
    cover = '<img src="/cover.jpg" alt="Cover" loading="lazy">'
    r3 = _analyze("", cover)
    hero3 = r3["performance_assets"]["hero_image"]
    check("hero: undimensioned lazy image still flagged as candidate",
          hero3 is not None and hero3.get("src") == "/cover.jpg")
    # One dimension present and small -> rejected (icon strip 24px wide).
    icon = '<img src="/icon.png" alt="icon" width="24" loading="lazy">'
    r4 = _analyze("", icon)
    check("hero: single small dimension rejected",
          r4["performance_assets"]["hero_image"] is None)
    # px suffix tolerated in dimension parsing.
    pximg = '<img src="/px.png" alt="px" width="50px" height="50px" loading="lazy">'
    r5 = _analyze("", pximg)
    check("hero: px-suffixed small dimensions rejected",
          r5["performance_assets"]["hero_image"] is None)


def test_fp_end_to_end():
    # The exact bezmezhau.com false positive: Next.js page with a noModule
    # polyfill + one below-the-fold QR code. Both deductions must disappear.
    head = ('<script src="/_next/static/chunks/abc.js" async></script>'
            '<script src="/_next/static/chunks/poly.js" noModule></script>'
            '<link rel="stylesheet" href="/_next/static/chunks/global.css" data-precedence="next"/>')
    qr = '<img src="/dalink-qr-code.png" alt="QR" width="112" height="112" loading="lazy">'
    ev = _run_full(head, qr)
    check("e2e: PERF-RESOURCE-HINTS-006 not WARNING on QR-only page",
          ev.get("PERF-RESOURCE-HINTS-006") != "WARNING")
    rb_css = ev.get("PERF-RENDER-BLOCK-003")
    check("e2e: no render-blocking JS finding (nomodule excluded, CSS alone tolerated)",
          rb_css != "WARNING")
    # Guard: a genuinely lazy large hero must still be flagged end-to-end.
    ev2 = _run_full("", '<img src="/hero.jpg" alt="Hero" width="1600" height="900" loading="lazy">')
    check("e2e: lazy large hero still WARNING", ev2.get("PERF-RESOURCE-HINTS-006") == "WARNING")


if __name__ == "__main__":
    print("--- Round-6 false-positive hardening suite (v3.8.1) ---")
    test_nomodule_not_render_blocking()
    test_hero_dimension_filter_units()
    test_fp_end_to_end()
    if PASS:
        print("[SUCCESS] all round-6 false-positive hardening checks passed")
        sys.exit(0)
    print("[FAILURE] one or more round-6 checks failed")
    sys.exit(1)
