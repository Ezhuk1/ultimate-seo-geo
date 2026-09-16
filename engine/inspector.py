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
import argparse
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List

from .analyzers.http_analyzer import analyze_target_http
from .analyzers.html_analyzer import analyze_target_html
from .analyzers.robots_simulator import parse_robots_txt, simulate_ai_crawlers
from .analyzers.schema_analyzer import analyze_json_ld, validate_schema_snippet
from .analyzers.content_analyzer import analyze_content
from .ledger import (
    LedgerBuilder,
    EvidenceLedger,
    CONFIDENCE_VERIFIED,
    CONFIDENCE_HEURISTIC,
    CONFIDENCE_UNVERIFIABLE,
    STATUS_PASS,
    STATUS_WARNING,
    STATUS_CRITICAL,
    STATUS_INFO,
    STATUS_NOT_MEASURED,
)
from .scoring import calculate_scores, ScoreBreakdown


def run_inspection(
    target: str,
    custom_robots_txt: Optional[str] = None,
    timeout: float = 15.0
) -> tuple[EvidenceLedger, ScoreBreakdown]:
    """
    Executes full deterministic audit on URL or local file and returns ledger + score.
    """
    builder = LedgerBuilder(target_url=target)

    # 1. Fetch / Read Target via HTTP/File Analyzer
    http_res = analyze_target_http(target, timeout=timeout)
    status_code = http_res["status_code"]
    headers = http_res["headers"]
    body_text = http_res["raw_content"]
    response_time_ms = http_res["response_time_ms"]
    robots_content: Optional[str] = custom_robots_txt

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
        ledger = builder.build()
        return ledger, calculate_scores(ledger)

    # Attempt to fetch robots.txt if target is remote and not provided
    if not http_res["is_local"] and not robots_content:
        parsed = urlparse(http_res.get("final_url", target))
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rob_res = analyze_target_http(robots_url, timeout=timeout)
        if rob_res["status_code"] == 200 and rob_res["raw_content"]:
            robots_content = rob_res["raw_content"]

    builder.set_raw(status_code, headers, body_text, response_time_ms, robots_content)

    # 2. HTML Inspection
    html_data = analyze_target_html(body_text, base_url=target)

    # 3. Schema Inspection
    schema_data = analyze_json_ld(html_data["json_ld_raw_blocks"])

    # 4. Content & GEO Inspection
    content_data = analyze_content(
        html_data.get("visible_text", html_data.get("visible_text_preview", "")),
        headings=html_data["headings"].get("outline", [])
    )

    # 5. Robots Inspection
    robots_sim: Optional[Dict[str, Any]] = None
    if robots_content:
        robots_ast = parse_robots_txt(robots_content)
        robots_sim = simulate_ai_crawlers(robots_ast)

    # 6. Record Signals
    builder.add_signal("http_status_code", "HTTP Status Code", status_code, unit="code")
    builder.add_signal("http_response_time_ms", "Response Time", response_time_ms, unit="ms")
    builder.add_signal("html_title_length", "Title Character Length", html_data["title"]["length"], unit="chars")
    builder.add_signal("html_meta_desc_length", "Meta Description Length", html_data["meta_description"]["length"], unit="chars")
    builder.add_signal("html_h1_count", "H1 Headings Count", html_data["headings"]["h1_count"], unit="count")
    builder.add_signal("html_canonical_present", "Canonical URL Present", html_data["canonical"]["present"])
    builder.add_signal("html_images_total", "Total Images", html_data["images"]["total_count"], unit="count")
    builder.add_signal("html_images_missing_alt", "Images Missing Alt", html_data["images"]["missing_alt"], unit="count")
    builder.add_signal("schema_scripts_count", "JSON-LD Scripts Count", schema_data.total_scripts, unit="count")
    builder.add_signal("schema_entity_count", "Schema Entities Count", len(schema_data.entities), unit="count")
    builder.add_signal("schema_has_unified_graph", "Schema Unified @graph Used", schema_data.has_unified_graph)
    builder.add_signal("content_total_words", "Visible Word Count", content_data.total_words, unit="words")
    builder.add_signal("robots_txt_present", "Robots.txt Present", robots_content is not None)

    # Unmeasured Field Signal (Crucial for Invariant Demonstration)
    builder.add_signal(
        signal_id="cwv_real_user_lcp_p75",
        name="Core Web Vitals Real-User LCP (P75)",
        value=None,
        is_measured=False,
        unit="ms",
        source="CrUX API (Unmeasured - Requires Field Dataset / API key)"
    )

    # 7. Evaluate Rules -> EVIDENCE & FINDINGS

    # TECH-CANONICAL-001
    canonical_val = html_data["canonical"]["value"]
    if not canonical_val:
        builder.add_evidence(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            title="Canonical Link Element",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed="None",
            expected="Absolute URL in <link rel='canonical'>",
            message="Missing canonical tag. High risk of duplicate content and split page rank."
        )
        builder.add_finding(
            rule_id="TECH-CANONICAL-001",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Missing Canonical Tag",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=[
                f"Add `<link rel=\"canonical\" href=\"{target}\" />` to the `<head>` section.",
                "Ensure self-referencing canonical URL uses absolute HTTPS format."
            ],
            impact_estimate="Prevents search and AI crawlers from consolidating canonical signals."
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
            message="Canonical tag present."
        )

    # TECH-TITLE-003
    t_len = html_data["title"]["length"]
    title_text = html_data["title"]["value"]
    if t_len == 0:
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=0,
            expected="30-60 characters",
            message="Page has no <title> tag."
        )
        builder.add_finding(
            rule_id="TECH-TITLE-003",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Missing Title Tag",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P0_BLOCKER",
            remediation_steps=["Add a concise descriptive `<title>` (30-60 chars) with primary entity and brand."],
            impact_estimate="Direct loss of search engine snippet generation and LLM query matching."
        )
    elif t_len < 30 or t_len > 65:
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{t_len} chars ('{title_text}')",
            expected="30-60 characters",
            message=f"Title length ({t_len} chars) is outside optimal 30-60 character display window."
        )
        builder.add_finding(
            rule_id="TECH-TITLE-003",
            category="technical",
            severity=STATUS_WARNING,
            title="Suboptimal Title Length",
            confidence=CONFIDENCE_HEURISTIC,
            action_priority="P2_MEDIUM",
            remediation_steps=[f"Adjust title from {t_len} characters to 45-58 characters."],
            impact_estimate="Risk of SERP pixel truncation or weak entity grounding."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-TITLE-003",
            category="technical",
            title="HTML Title Tag Length",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{t_len} chars ('{title_text}')",
            expected="30-60 characters",
            message="Title length is within ideal limits."
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
            expected="120-160 characters",
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
    elif d_len < 100 or d_len > 165:
        builder.add_evidence(
            rule_id="TECH-META-DESC-004",
            category="technical",
            title="Meta Description",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_HEURISTIC,
            observed=f"{d_len} chars",
            expected="120-160 characters",
            message=f"Meta description length ({d_len} chars) is outside optimal 120-160 window."
        )
    else:
        builder.add_evidence(
            rule_id="TECH-META-DESC-004",
            category="technical",
            title="Meta Description",
            status=STATUS_PASS,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"{d_len} chars",
            expected="120-160 characters",
            message="Meta description length is optimal."
        )

    # TECH-H1-OUTLINE-005
    h1_count = html_data["headings"]["h1_count"]
    if h1_count != 1:
        builder.add_evidence(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            title="H1 Heading Count",
            status=STATUS_WARNING,
            confidence=CONFIDENCE_VERIFIED,
            observed=h1_count,
            expected="Exactly 1 H1 heading",
            message=f"Page has {h1_count} <h1> elements (expected exactly 1 for clear semantic outline)."
        )
        builder.add_finding(
            rule_id="TECH-H1-OUTLINE-005",
            category="technical",
            severity=STATUS_WARNING,
            title="Multiple or Missing H1 Headings",
            confidence=CONFIDENCE_VERIFIED,
            action_priority="P2_MEDIUM",
            remediation_steps=["Refactor headings so that there is strictly one <h1> representing the primary page entity."],
            impact_estimate="Weakens document hierarchical outline for AI section extractors."
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
    builder.add_signal("html_is_csr_shell", "Client-Side Rendering (CSR) Empty Shell Detected", csr_info.get("is_csr_shell", False))
    if csr_info.get("is_csr_shell", False):
        mounts_str = ", ".join(csr_info.get("mount_elements", [])) or "JS bundle container"
        w_count = csr_info.get("visible_word_count", 0)
        builder.add_evidence(
            rule_id="TECH-CSR-SHELL-008",
            category="technical",
            title="Client-Side Rendering (CSR) Empty Shell Invisibility",
            status=STATUS_CRITICAL,
            confidence=CONFIDENCE_VERIFIED,
            observed=f"CSR mount [{mounts_str}] with only {w_count} visible word(s)",
            expected="Server-rendered semantic HTML payload",
            message="Empty Client-Side Rendering (CSR) shell detected. Fast AI search crawlers (GPTBot, ClaudeBot, PerplexityBot) do NOT execute client-side JavaScript. This page is completely invisible to AI search engines."
        )
        builder.add_finding(
            rule_id="TECH-CSR-SHELL-008",
            category="technical",
            severity=STATUS_CRITICAL,
            title="Client-Side Rendering (CSR) Empty Shell Invisibility",
            confidence=CONFIDENCE_VERIFIED,
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

    # TECH-ROBOTS-AI-002
    if robots_sim:
        blocked_ai = [b for b, res in robots_sim.items() if not res["root_allowed"]]
        if blocked_ai:
            builder.add_evidence(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                title="Robots.txt AI Crawler Access",
                status=STATUS_WARNING,
                confidence=CONFIDENCE_VERIFIED,
                observed=f"Blocked crawlers: {', '.join(blocked_ai)}",
                expected="Explicit policy allowing AI search crawlers (PerplexityBot, ClaudeBot, GPTBot)",
                message=f"AI search/retrieval crawlers blocked in robots.txt: {', '.join(blocked_ai)}."
            )
            builder.add_finding(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                severity=STATUS_WARNING,
                title="AI Crawlers Disallowed in Robots.txt",
                confidence=CONFIDENCE_VERIFIED,
                action_priority="P1_HIGH",
                remediation_steps=[
                    "Verify if blocking AI crawlers is deliberate business policy.",
                    "If GEO visibility is desired, allow User-agent: GPTBot, ClaudeBot, PerplexityBot in robots.txt."
                ],
                impact_estimate="Zero citations in ChatGPT Search, Claude, and Perplexity AI engines."
            )
        else:
            builder.add_evidence(
                rule_id="TECH-ROBOTS-AI-002",
                category="technical",
                title="Robots.txt AI Crawler Access",
                status=STATUS_PASS,
                confidence=CONFIDENCE_VERIFIED,
                observed="All major AI crawlers allowed access to root",
                expected="Allow AI search crawlers",
                message="Robots.txt permits AI search and answer bots."
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

    if not schema_data.findings and schema_data.entities:
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

    if content_data.opening_has_direct_answer:
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

    if content_data.monolithic_chunks_count == 0 and content_data.total_chunks > 0:
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

    if content_data.pronoun_lead_count <= 2:
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

    # UNMEASURED FIELD EVIDENCE (Demonstrates strict "Unknown != Failure" invariant)
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

    ledger = builder.build()
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
    md.append(f"| **GEO Readiness Index** | **{scores.geo_readiness_index} / 100** ({scores.geo_maturity_tier}) | Direct answer frontloading, chunking, coreference, Schema graph |")
    md.append(f"| **Observation Coverage** | **{scores.observation_coverage_pct}%** ({ledger.metadata['signals_measured']}/{ledger.metadata['signals_total']} signals) | Empirical completeness of audit scope |")
    md.append("")

    md.append("> [!NOTE]")
    md.append("> **Evidence Ledger Invariant: 'Unknown != Failure'**  ")
    md.append(f"> Exactly {scores.not_measured_count} unmeasured external signal(s) (e.g., CWV CrUX field data) were detected. In compliance with the Evidence Protocol, unmeasured signals carry 0 penalty and are explicitly segregated from verified defects.")
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
    md.append("| Category | Rule ID | Status | Confidence | Observed Value | Expected Contract |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for ev in ledger.evidence:
        status_badge = (
            "[CRITICAL]" if ev.status == STATUS_CRITICAL
            else ("[WARNING]" if ev.status == STATUS_WARNING
            else ("[PASS]" if ev.status == STATUS_PASS
            else ("[NOT_MEASURED]" if ev.status == STATUS_NOT_MEASURED else "[INFO]")))
        )
        obs_str = str(ev.observed).replace("\n", " ")[:60]
        exp_str = str(ev.expected).replace("\n", " ")[:60]
        md.append(f"| `{ev.category}` | `{ev.rule_id}` | `{status_badge}` | `{ev.confidence}` | {obs_str} | {exp_str} |")
    md.append("")

    return "\n".join(md)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Ultimate SEO & GEO Autonomous Inspection Engine v2.1.0")
    parser.add_argument("target", nargs="?", default=None, help="Target URL (https://...) or local HTML file path")
    parser.add_argument("--validate-schema", nargs="?", const="stdin", default=None, help="Validate standalone Schema.org JSON-LD snippet (file path, raw JSON string, or stdin)")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format (markdown or json)")
    parser.add_argument("--output", help="Optional output file path to write results")
    parser.add_argument("--robots", help="Optional custom robots.txt file or URL")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP request timeout in seconds")

    args = parser.parse_args()

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

    custom_robots = None
    if args.robots:
        if os.path.exists(args.robots):
            with open(args.robots, "r", encoding="utf-8", errors="replace") as f:
                custom_robots = f.read()
        else:
            custom_robots = args.robots

    try:
        ledger, scores = run_inspection(args.target, custom_robots_txt=custom_robots, timeout=args.timeout)
    except Exception as exc:
        sys.stderr.write(f"Error executing inspection: {exc}\n")
        sys.exit(1)

    if args.format == "json":
        res_dict = ledger.to_dict()
        res_dict["scores"] = scores.__dict__
        import json
        output_str = json.dumps(res_dict, indent=2, default=str)
    else:
        output_str = format_markdown_report(ledger, scores)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Inspection report saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
