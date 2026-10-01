#!/usr/bin/env python3
"""
Deterministic regression suite for external-audit round 3 hardening.
Run: python evals/test_engine_round3.py
Covers: scoring category gate, local-file unmeasured wire signals,
freshness naive/aware, empty JSON-LD verdict, experiment hostname matching,
GSC package (BOM, ZeroDivision, aliasing, pos=0, avg_position, healthy-dominant,
curve to 20), redirect-loop detector, disabled_rules consistency, Vary/IndexNow
rules, sarif URI, version sync.
"""

import json
import os
import re
import subprocess
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


def test_scoring_category_gate():
    from engine.ledger import LedgerBuilder
    from engine.scoring import calculate_scores
    b = LedgerBuilder(target_url="https://x.com/a")
    for rid, cat in (("SEC-PROMPT-INJECTION-001", "security"),
                     ("GEO-AI-BOT-POLICY-007", "geo"),
                     ("TECH-ROBOTS-002", "technical")):
        b.add_evidence(rule_id=rid, category=cat, title="t", status="CRITICAL",
                       confidence="VERIFIED", observed="x", expected="y", message="m")
    res = calculate_scores(b.build())
    deds = {d["rule_id"] for d in res.deductions}
    check("scoring: security CRITICAL deducted", "SEC-PROMPT-INJECTION-001" in deds)
    check("scoring: geo CRITICAL deducted", "GEO-AI-BOT-POLICY-007" in deds)
    check("scoring: critical_count counts all categories", res.critical_count == 3)


def test_local_file_wire_signals():
    html = ('<!DOCTYPE html><html><head><title>T</title></head><body><main><h1>H</h1>'
            '<p>Body text content for the analyzer.</p></main></body></html>')
    tf = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    tf.write(html)
    tf.close()
    try:
        r = subprocess.run(
            [sys.executable, "-m", "engine.inspector", tf.name, "--format", "json"],
            capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout)
        sigs = d.get("signals", {})
        check("local file: target_is_https unmeasured",
              sigs["target_is_https"]["is_measured"] is False)
        check("local file: hsts unmeasured",
              sigs["http_hsts_present"]["is_measured"] is False)
        sh = d["scores"].get("security_hygiene")
        sh = sh if isinstance(sh, dict) else {}
        check("local file: security score not a measured HTTPS failure",
              sh.get("score") not in (0, 25))
    finally:
        os.unlink(tf.name)


def test_freshness_tz_mix():
    from engine.analyzers.freshness_analyzer import analyze_freshness
    try:
        res = analyze_freshness(
            visible_text="Enough body text for the analyzer.",
            schema_entities=[{"@type": "Article", "datePublished": "2026-01-15T10:00:00"}],
            http_headers={"Last-Modified": "Wed, 21 Oct 2026 07:28:00 GMT"})
        check("freshness: naive schema date + aware HTTP date no crash", True)
        check("freshness: future HTTP date detected", res.has_discrepancy)
    except TypeError:
        check("freshness: naive schema date + aware HTTP date no crash", False)


def test_empty_json_ld():
    from engine.analyzers.schema_analyzer import analyze_json_ld
    r = analyze_json_ld([])
    check("schema: no blocks -> UNKNOWN structure", r.schema_org_structure == "UNKNOWN")
    check("schema: no blocks -> not ELIGIBLE", r.google_rich_result_eligibility == "UNKNOWN")


def test_experiment():
    from engine.experiment import _normalize_domain, evaluate_citation_benchmark, CitationQuerySample
    check("experiment: www.webow.com -> webow.com", _normalize_domain("www.webow.com") == "webow.com")
    check("experiment: wwww.com -> wwww.com", _normalize_domain("wwww.com") == "wwww.com")
    s = CitationQuerySample(query_id="q1", query_text="q", engine="gpt",
                            answer_text="answer", sources=["https://notexample.com/page"])
    m = evaluate_citation_benchmark([s], target_brand="Example", target_domain="example.com")
    d = m.to_dict() if hasattr(m, "to_dict") else m.__dict__
    check("experiment: notexample.com is NOT a citation of example.com",
          d.get("citation_rate_pct") == 0.0)
    s2 = CitationQuerySample(query_id="q2", query_text="q", engine="gpt",
                             answer_text="answer", sources=["https://www.example.com/page"])
    m2 = evaluate_citation_benchmark([s2], target_brand="Example", target_domain="example.com")
    d2 = m2.to_dict() if hasattr(m2, "to_dict") else m2.__dict__
    check("experiment: www.example.com IS a citation of example.com",
          d2.get("citation_rate_pct") == 100.0)


def test_gsc_package():
    from engine.analyzers.gsc_analyzer import analyze_gsc_csv, expected_organic_ctr
    # BOM
    r = analyze_gsc_csv("\ufeffЗапрос,Показы,Клики,CTR,Позиция\nтест,100,5,5.0,5.0\n")
    check("gsc: BOM + Russian header parsed", r.is_valid and r.total_rows == 1)
    # ZeroDivision
    try:
        analyze_gsc_csv("query,page,clicks,impressions,ctr,position\nq,/a,0,0,0,5.0\nq,/b,0,0,0,9.0\n",
                        min_impressions=0)
        check("gsc: zero-impression cannibalization no ZeroDivision", True)
    except ZeroDivisionError:
        check("gsc: zero-impression cannibalization no ZeroDivision", False)
    # aliasing
    r3 = analyze_gsc_csv("query,clicks,impressions,ctr,position\nwidget,0,100,0,6.0\n")
    sd, qw = r3.striking_distance[0], r3.quick_wins[0]
    check("gsc: striking entry keeps striking_distance type", sd.opportunity_type == "striking_distance")
    check("gsc: quick_win entry is a separate object", sd is not qw)
    # empty position
    r4 = analyze_gsc_csv("query,clicks,impressions,ctr,position\nq1,0,400,0,0.0\n")
    check("gsc: empty position cell not flagged as underperformer",
          not any(q.position == 0.0 for q in r4.ctr_opportunities))
    # avg_position: zero-impression row carries no weight
    r5 = analyze_gsc_csv("query,clicks,impressions,ctr,position\nzero,0,0,0,9.9\nreal,10,100,10,1.0\n")
    check("gsc: avg_position ignores zero-impression rows", abs(r5.average_position - 1.0) < 0.01)
    # healthy-dominant on #8
    r6 = analyze_gsc_csv("query,page,clicks,impressions,ctr,position\nq,/dominant,1,100,1.0,8.0\nq,/secondary,0,30,0,2.0\n")
    check("gsc: dominant URL on #8 still flagged (healthy-skip by own position)",
          r6.cannibalization_count == 1)
    # curve covers 5-20
    check("gsc: expected_ctr at position 15 present", expected_organic_ctr(15.0) is not None)
    check("gsc: expected_ctr beyond 20 still None", expected_organic_ctr(25.0) is None)


def test_redirect_loop():
    from engine.analyzers.http_analyzer import _has_redirect_loop
    chain6 = [{"code": 301, "from": f"https://x.com/p{i}", "to": f"https://x.com/p{i+1}"} for i in range(6)]
    check("http: 6-hop acyclic migration is NOT a loop", not _has_redirect_loop(chain6))
    check("http: self-loop detected", _has_redirect_loop([{"code": 301, "from": "https://x.com/a", "to": "https://x.com/a"}]))
    loop = [{"code": 301, "from": "https://x.com/a", "to": "https://x.com/b"},
            {"code": 301, "from": "https://x.com/b", "to": "https://x.com/a"}]
    check("http: 2-hop real cycle detected", _has_redirect_loop(loop))


def test_disabled_rules_consistency():
    html = ('<!DOCTYPE html><html><head><title>' + "T" * 80 + '</title>'
            '<meta name="description" content="x"></head><body><main><h1>H</h1>'
            '<p>Body text content for the analyzer with enough words to pass checks.</p></main></body></html>')
    tf = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    tf.write(html)
    tf.close()
    try:
        from engine.config import EngineConfig
        from engine.inspector import run_inspection
        baseline_ledger, _ = run_inspection(tf.name)
        cfg = EngineConfig(disabled_rules=["TECH-TITLE-003"])
        led, _ = run_inspection(tf.name, config=cfg)
        fids = [f.rule_id for f in led.findings]
        eids = {e.rule_id for e in led.evidence}
        base_fids = [f.rule_id for f in baseline_ledger.findings]
        check("disabled_rules: baseline has the rule, disabled run does not (findings)",
              "TECH-TITLE-003" in base_fids and "TECH-TITLE-003" not in fids)
        check("disabled_rules: rule absent from evidence", "TECH-TITLE-003" not in eids)
        check("disabled_rules: metadata built consistently (criteria table present)",
              "criteria_observed" in led.metadata)
    finally:
        os.unlink(tf.name)


def test_vary_and_indexnow():
    from engine.ledger import LedgerBuilder
    import engine.inspector as insp
    src = open(insp.__file__, encoding="utf-8").read()
    check("inspector: Vary parsed per-token, not substring",
          '"accept" in _vary_tokens' in src and '"accept" in headers.get("vary"' not in src)
    check("inspector: IndexNow requires structured meta/link marker",
          "indexnow\" in str(body_text).lower()" not in src and "<meta[^>]+indexnow" in src)
    check("inspector: top_findings sorted by priority",
          "top_findings = sorted(" in src)


def test_sarif_uri():
    from engine.sarif import format_sarif_json
    from engine.ledger import LedgerBuilder
    b = LedgerBuilder(target_url=r"C:\Users\ezhik\Downloads\p.html")
    b.add_evidence(rule_id="TECH-ROBOTS-002", category="technical", title="t", status="CRITICAL",
                   confidence="VERIFIED", observed="x", expected="y", message="m")
    s = json.loads(format_sarif_json(b.build()))
    uri = s["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    check("sarif: local Windows path becomes file:// URI", uri.startswith("file:///"))
    check("sarif: no invented example.com fallback", "https://example.com" not in uri)


def test_version_sync():
    import engine.config as cfg
    cfg_src = open(cfg.__file__, encoding="utf-8").read()
    check("config: no stale 3.4.0/3.3.0 versions",
          not re.search(r"3\.(3|4)\.0", cfg_src))
    crawl_src = open("engine/crawler.py", encoding="utf-8").read()
    check("crawler: UA version synced", "UltimateSeoGeoCrawler/3.6.0" in crawl_src
          and "UltimateSeoGeoCrawler/2.1" not in crawl_src)


if __name__ == "__main__":
    print("--- Round-3 hardening regression suite ---")
    test_scoring_category_gate()
    test_local_file_wire_signals()
    test_freshness_tz_mix()
    test_empty_json_ld()
    test_experiment()
    test_gsc_package()
    test_redirect_loop()
    test_disabled_rules_consistency()
    test_vary_and_indexnow()
    test_sarif_uri()
    test_version_sync()
    if PASS:
        print("[SUCCESS] all round-3 hardening checks passed")
        sys.exit(0)
    print("[FAILURE] one or more round-3 checks failed")
    sys.exit(1)
