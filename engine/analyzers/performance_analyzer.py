"""
Deterministic Performance, Core Web Vitals & Asset Optimization Analyzer.

Evaluates DOM complexity, render-blocking resources, resource hints,
image modern format utilization, and optional CrUX field telemetry
via the Google PageSpeed Insights API.
"""

from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from urllib.parse import urlsplit


@dataclass
class PerformanceFinding:
    rule_id: str
    severity: str
    title: str
    message: str
    action_priority: str
    remediation_steps: List[str]
    impact_estimate: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CwvFieldMetrics:
    is_measured: bool = False
    lcp_ms: Optional[float] = None
    inp_ms: Optional[float] = None
    cls_score: Optional[float] = None
    tbt_ms: Optional[float] = None
    performance_score: Optional[int] = None
    source: str = "Google PageSpeed Insights API"
    raw_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceAnalysisResult:
    dom_nodes_count: int = 0
    max_dom_depth: int = 0
    script_tags_count: int = 0
    render_blocking_css: List[str] = field(default_factory=list)
    render_blocking_js: List[str] = field(default_factory=list)
    resource_hints: List[Dict[str, str]] = field(default_factory=list)
    hero_image: Optional[Dict[str, Any]] = None
    image_formats: Dict[str, int] = field(default_factory=lambda: {"modern": 0, "legacy": 0})
    cwv_field: CwvFieldMetrics = field(default_factory=CwvFieldMetrics)
    findings: List[PerformanceFinding] = field(default_factory=list)


def query_pagespeed_insights(url: str, api_key: str, timeout: float = 10.0) -> CwvFieldMetrics:
    """
    Fetches real-user CrUX field data and lab Lighthouse metrics via Google PSI API.
    Zero-dependency via urllib.request.
    """
    metrics = CwvFieldMetrics(is_measured=False)
    if not api_key or not url.startswith(("http://", "https://")):
        return metrics

    endpoint = (
        f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={urllib.parse.quote(url, safe='')}&key={urllib.parse.quote(api_key, safe='')}&strategy=mobile"
    )

    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "UltimateSeoGeoEngine/3.6.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        metrics.is_measured = True
        metrics.raw_metrics = data

        # Extract CrUX Field Metrics
        loading_exp = data.get("loadingExperience", {}).get("metrics", {})
        lcp_data = loading_exp.get("LARGEST_CONTENTFUL_PAINT_MS", {})
        if "percentile" in lcp_data:
            metrics.lcp_ms = float(lcp_data["percentile"])

        inp_data = loading_exp.get("INTERACTION_TO_NEXT_PAINT", {})
        if "percentile" in inp_data:
            metrics.inp_ms = float(inp_data["percentile"])

        cls_data = loading_exp.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {})
        if "percentile" in cls_data:
            metrics.cls_score = float(cls_data["percentile"]) / 100.0 if cls_data["percentile"] > 1 else float(cls_data["percentile"])

        # Extract Lab Metrics
        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        perf_cat = categories.get("performance", {})
        if "score" in perf_cat and perf_cat["score"] is not None:
            metrics.performance_score = int(round(float(perf_cat["score"]) * 100))

        audits = lighthouse.get("audits", {})
        tbt_audit = audits.get("total-blocking-time", {})
        if "numericValue" in tbt_audit and tbt_audit["numericValue"] is not None:
            metrics.tbt_ms = float(tbt_audit["numericValue"])

    except Exception:
        # Network timeout or invalid API key gracefully returns unmeasured
        metrics.is_measured = False

    return metrics


def analyze_performance(
    html_data: Dict[str, Any],
    target_url: str = "",
    psi_api_key: Optional[str] = None
) -> PerformanceAnalysisResult:
    """
    Evaluates DOM health, render-blocking resources, and performance signals.
    """
    res = PerformanceAnalysisResult()

    dom_stats = html_data.get("dom_stats", {})
    res.dom_nodes_count = dom_stats.get("nodes_count", 0)
    res.max_dom_depth = dom_stats.get("max_depth", 0)
    res.script_tags_count = dom_stats.get("script_tags_count", 0)

    perf_assets = html_data.get("performance_assets", {})
    res.render_blocking_css = perf_assets.get("render_blocking_css", [])
    res.render_blocking_js = perf_assets.get("render_blocking_js", [])
    res.resource_hints = perf_assets.get("resource_hints", [])
    res.hero_image = perf_assets.get("hero_image")
    res.image_formats = perf_assets.get("image_formats", {"modern": 0, "legacy": 0})

    # 1. PERF-DOM-005: DOM Size & Nesting Limits (HTTP Archive standards)
    dom_issues = []
    if res.dom_nodes_count > 1500:
        dom_issues.append(f"DOM nodes count ({res.dom_nodes_count}) exceeds recommended 1500 limit")
    if res.max_dom_depth > 32:
        dom_issues.append(f"DOM nesting depth ({res.max_dom_depth}) exceeds recommended 32 levels")
    if res.script_tags_count > 50:
        dom_issues.append(f"Total script tags count ({res.script_tags_count}) exceeds recommended 50 limit")

    if dom_issues:
        res.findings.append(PerformanceFinding(
            rule_id="PERF-DOM-005",
            severity="WARNING",
            title="Excessive DOM Tree Complexity",
            message="; ".join(dom_issues),
            action_priority="P2_MEDIUM",
            remediation_steps=[
                "Simplify page component hierarchy and eliminate redundant nesting wrapper <div> tags.",
                "Consolidate script bundles to reduce DOM overhead and memory footprint."
            ],
            impact_estimate="High memory consumption, delayed interaction latency (INP), and increased style recalculation time.",
            details={"nodes": res.dom_nodes_count, "depth": res.max_dom_depth, "scripts": res.script_tags_count}
        ))

    # 2. PERF-RENDER-BLOCK-003: Render-Blocking CSS and Synchronous JS
    # A single external stylesheet is the standard bundler pattern (Next.js /
    # Vite / Astro emit one CSS bundle); making it async risks FOUC and is a
    # build-tool concern, not a page-authoring defect. Escalate to WARNING
    # only for >=2 stylesheets or any synchronous script.
    css_count = len(res.render_blocking_css)
    js_count = len(res.render_blocking_js)
    if css_count + js_count > 0:
        css_note = f"{css_count} render-blocking stylesheet(s)" if res.render_blocking_css else ""
        js_note = f"{js_count} synchronous script(s) in <head>" if res.render_blocking_js else ""
        combined_note = " and ".join(filter(None, [css_note, js_note]))
        escalates = js_count > 0 or css_count >= 2
        if escalates:
            message = f"Document contains {combined_note} delaying initial paint."
        else:
            message = (
                f"Document contains {combined_note}. A single bundled stylesheet is the "
                "standard build-tool pattern; deferring it risks FOUC. Verify with field "
                "Core Web Vitals data before restructuring the bundle."
            )
        res.findings.append(PerformanceFinding(
            rule_id="PERF-RENDER-BLOCK-003",
            severity="WARNING" if escalates else "INFO",
            title="Render-Blocking CSS/JS Assets in <head>",
            message=message,
            action_priority="P1_HIGH" if escalates else "P3_LOW",
            remediation_steps=[
                "Add `defer` or `async` to non-critical `<script>` tags inside `<head>`.",
                "Inline critical above-the-fold CSS and load non-critical stylesheets asynchronously via `rel='preload'` or `media='print'` onload switch."
            ],
            impact_estimate="Delays First Contentful Paint (FCP) and Largest Contentful Paint (LCP) by blocking browser main thread rendering.",
            details={"blocking_css": res.render_blocking_css, "blocking_js": res.render_blocking_js}
        ))

    # 3. PERF-RESOURCE-HINTS-006: Hero Image Priority & Lazy Loading Anti-pattern
    if res.hero_image:
        loading_val = res.hero_image.get("loading", "")
        fetch_val = res.hero_image.get("fetchpriority", "")
        if loading_val == "lazy":
            res.findings.append(PerformanceFinding(
                rule_id="PERF-RESOURCE-HINTS-006",
                severity="WARNING",
                title="LCP Hero Image Lazy Loading Anti-Pattern",
                message="Candidate hero image has `loading='lazy'`. Lazy loading the primary above-the-fold image delays LCP.",
                action_priority="P1_HIGH",
                remediation_steps=[
                    "Remove `loading='lazy'` from the primary hero/LCP image.",
                    "Add `fetchpriority='high'` to ensure the browser prioritizes download immediately."
                ],
                impact_estimate="Directly penalizes Largest Contentful Paint (LCP) Core Web Vital score.",
                details={"hero_src": res.hero_image.get("src")}
            ))
        elif fetch_val != "high":
            # Informational hint
            res.findings.append(PerformanceFinding(
                rule_id="PERF-RESOURCE-HINTS-006",
                severity="INFO",
                title="Missing fetchpriority='high' on Hero Image",
                message="Above-the-fold hero image candidate does not specify `fetchpriority='high'`.",
                action_priority="P3_LOW",
                remediation_steps=[
                    "Add `fetchpriority='high'` to the primary above-the-fold `<img>` or `<link rel='preload' as='image'>` tag."
                ],
                impact_estimate="Minor LCP optimization opportunity.",
                details={"hero_src": res.hero_image.get("src")}
            ))

    # 4. TECH-IMAGE-MODERN-038: Modern Image Formats (WebP / AVIF)
    mod_count = res.image_formats.get("modern", 0)
    leg_count = res.image_formats.get("legacy", 0)
    tot_imgs = mod_count + leg_count
    if tot_imgs >= 3 and mod_count == 0:
        res.findings.append(PerformanceFinding(
            rule_id="TECH-IMAGE-MODERN-038",
            severity="WARNING",
            title="Absence of Modern Image Formats (WebP/AVIF)",
            message=f"All {tot_imgs} image(s) use legacy formats (JPEG/PNG/GIF) with 0 modern formats (WebP/AVIF/SVG).",
            action_priority="P2_MEDIUM",
            remediation_steps=[
                "Convert image assets to WebP or AVIF format using sharp, squoosh, or CDN image optimization.",
                "Use `<picture>` with `<source type='image/webp'>` fallback for maximum browser support."
            ],
            impact_estimate="Excessive network transfer payload and slower mobile rendering.",
            details={"modern": mod_count, "legacy": leg_count}
        ))

    # 5. Core Web Vitals Field API (CrUX)
    effective_api_key = psi_api_key or os.environ.get("PAGESPEED_API_KEY", "")
    if effective_api_key and target_url and not target_url.startswith("file://") and "localhost" not in target_url:
        res.cwv_field = query_pagespeed_insights(target_url, effective_api_key)

    return res
