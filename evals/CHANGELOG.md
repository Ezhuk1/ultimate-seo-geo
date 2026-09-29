# Evaluation Suite Changelog

All notable changes to the `ultimate-seo-geo` evaluation benchmark will be documented in this file.

## [3.6.0] - 2026-09-29

### Added
- **Keyword Cannibalization Detection (`engine/analyzers/gsc_analyzer.py`):**
  - New `GscCannibalizationItem` and detection pass over GSC exports containing both query and page dimensions: groups rows by query, and when a query is served by multiple URLs (with total impressions above threshold), flags split authority with per-page impressions, best position, and top-page impression share.
  - Healthy pattern (one dominant URL holding $\\ge$60% of impressions already ranking top-3) is never flagged.
  - Contextual consolidation recommendations: canonicalize/301 secondary pages into a top-3 primary; pick a canonical target and repoint internal anchors when no URL owns the query.
  - Epistemic parity: exports carrying only one of the two dimensions record a `NOT MEASURED` note in the result and markdown summary instead of silently skipping the check (Unknown ≠ Failure).
- **Position-Aware CTR Underperformance Model (`engine/analyzers/gsc_analyzer.py`):**
  - New `EXPECTED_CTR_CURVE` anchor table + `expected_organic_ctr(position)` piecewise-linear interpolation (aggregate industry CTR benchmarks, tunable per niche).
  - Snippet underperformance now flags queries whose CTR is below 50% of the position-typical benchmark in addition to the existing static <2.0% floor — e.g. position 1 with 5% CTR is now caught. `GscQueryItem` gains `expected_ctr`; serialized items include `expected_ctr` and `ctr_deficit_pct`.
- **Engine Test Suite `test_v3_6_0_gsc_cannibalization_suite` (`evals/test_engine.py`):** 33rd deterministic suite covering curve interpolation, split-authority detection, healthy-dominance skip, position-aware CTR flagging, NOT MEASURED note, markdown rendering, and v3.3.0 backward compatibility.

### Fixed
- **Empty Snippet Underperformers Table in Markdown Summary (`engine/analyzers/gsc_analyzer.py`):**
  - `format_gsc_markdown_summary` emitted the "Snippet Underperformers" table header without ever rendering data rows. Rows now render with position, impressions, current vs expected CTR, and a recommended snippet fix, plus an expected-CTR heuristic footnote.

### Changed
- Version strings synchronized to 3.6.0 across `engine/__init__.py`, `engine/ledger.py`, `pyproject.toml`, `ultimate-seo-geo.json`, analyzer User-Agents, `evals/evals.json`, `evals/run_evals.py`, and README badges.

## [3.5.1] - 2026-09-28

### Fixed
- **Epistemic audit remediations (`engine/analyzers/html_analyzer.py`, `engine/analyzers/schema_analyzer.py`, `engine/analyzers/ga4_analyzer.py`, `engine/scoring.py`):**
  - Astro-island components with server-rendered text are no longer misclassified as CSR shells.
  - Schema `@id` references pointing to external URIs (e.g. Wikidata) are not flagged as broken refs.
  - GA4 summary adds an attribution caution footnote for `googlequicksearchbox` referrals.
  - Low observation coverage ratio computed correctly (<20% guard).
  - Covered by `test_v3_5_1_epistemic_audit_remediation_suite`.

## [3.5.0] - 2026-09-28

### Fixed
- **SSRF Guard Tuple Unpacking (`engine/analyzers/llms_analyzer.py`):**
  - Resolved critical vulnerability where `if not is_safe_target_url(...)` evaluated truthy for `(False, reason)` tuples, allowing internal and loopback IP addresses to bypass SSRF validation. Unpacks `is_safe, ssrf_reason = is_safe_target_url(...)`.
- **Distribution Package Data & Rules Inclusion (`pyproject.toml`, `engine/rules.py`):**
  - Updated `pyproject.toml` to package `rules/*.json` and `references/*.json` via `setuptools.package-data`. Resolved defect where standalone wheel installs had 0 rules in registry. Added multi-path fallback discovery in `engine/rules.py`.
- **Inverted Orphan Page Detection (`engine/indexability.py`):**
  - Fixed inverted logic in Vector 7 (Internal Links) where pages with zero *outbound* internal links were flagged as orphan candidates. Single-page inspection now classifies 0 outbound links as `terminal (0 outbound)` without false `AMBIGUOUS` penalties; true orphan candidate checks require crawl graph inbound link data (`inbound_internal_links_count == 0`).
- **Security Hygiene Score Neutrality (`engine/scoring.py`):**
  - Fixed invariant breach where unmeasured targets received 50 free points (25 for HTTPS + 25 for mixed content). Security score now strictly adheres to "Unknown ≠ Failure" and pro-rates over measured components, assigning 0 / `NOT_MEASURED` when no security signals are observed.
- **Canonical Normalization Preserves Query String (`engine/indexability.py`):**
  - `_normalize_for_url_compare` now preserves query parameters instead of dropping them, preventing URLs with query strings from falsely registering as self-canonicals when pointing to parameterless canonicals.
- **Status Constant Collision (`engine/ledger.py`):**
  - Disambiguated `STATUS_NOT_MEASURED = "NOT_MEASURED"` (previously duplicated `STATUS_UNKNOWN = "UNKNOWN"`), restoring granular criteria breakdown in inspection reports.
- **Crawler Indexability Directive Parity (`engine/crawler.py`):**
  - `is_indexable` now evaluates both `<meta name="robots" content="noindex">` and `X-Robots-Tag: noindex` headers.
- **Prompt Injection Markdown Code Fence Exemption (`engine/analyzers/security_analyzer.py`):**
  - Sanitizes and exempts markdown code fences (```` ```...``` ````) and inline backticks from visible prompt injection detection, preventing false positive `P0_BLOCKER` findings on technical documentation and security advisories.

### Changed
- **Title SERP Pixel Width & Meta Description Thresholds (`engine/inspector.py`, `rules/technical_rules.json`):**
  - `TECH-TITLE-003` now directly evaluates desktop SERP pixel width (`estimate_title_pixel_width() > 580px`) alongside character count.
  - Softened meta description warning threshold from 100–165 to 70–165 characters to avoid penalizing concise, CTA-driven descriptions.
  - Softened `TECH-HREFLANG-033` missing `x-default` from a 5-point score penalty to a `STATUS_INFO` optimization advisory, aligned with Google Search Central specifications.
- **CSR Shell Detection & Bot-Specific Decoupling (`engine/analyzers/html_analyzer.py`, `engine/indexability.py`):**
  - Expanded mount element detection to include Angular (`<app-root>`), Astro (`<astro-island>`), Svelte, and Vue mount containers.
  - Differentiated indexation verdicts in `IndexabilityMatrix.to_dict()`: `bot_breakdown` distinguishes between Googlebot (rendering queue risk / delay) and non-rendering AI search bots (BLOCKED).
- **AI Crawlers Synchronization (`engine/analyzers/robots_simulator.py`):**
  - Added missing `Any` import to typing imports.
  - Added `meta-externalagent`, `Perplexity-User`, `cohere-ai`, and `MistralAI-User` to `KNOWN_AI_CRAWLERS`, harmonizing simulator with README robots blueprint.
- **GEO Readiness Index Framing & Content Depth Guard (`engine/scoring.py`):**
  - Applied Content Depth Guard to zero out all text dimensions (`dim_ans`, `dim_ent`, `dim_ev`, `dim_src`, `dim_chunk`) when substantive content is < 25 words, eliminating unearned high scores on stub pages.
  - Documented Tier E (Heuristic) status emphasizing that GEO index is a structural extractability checklist, not a guaranteed LLM citation prediction.

### Added
- **v3.5.0 Audit Remediation Test Suite (`evals/test_engine.py`, `evals/run_evals.py`):**
  - Added `test_v3_5_0_audit_remediation_suite` expanding engine test suite to 30 deterministic test suites (60/60 total passing across canonical evals, mutations, and engine integration).

## [3.4.0] - 2026-09-28

### Added
- **Autonomous Agent Readiness & Lighthouse Agentic Browsing (`engine/analyzers/html_analyzer.py`, `rules/technical_rules.json`):**
  - Added interactive accessibility analysis (`AGENT-A11Y-INTERACTIVE-002`, Tier A, W3C WAI-ARIA) verifying accessible names for buttons and form inputs, and detecting non-semantic `<div onclick>` fake buttons that disrupt autonomous browsing agents (Operator, Claude Computer Use).
  - Added Markdown content negotiation (`AGENT-MARKDOWN-NEGOTIATION-001`, Tier E) detecting `<link rel="alternate" type="text/markdown">` and `Accept: text/markdown` headers.
  - Added Fast-Track Indexing Protocol (`TECH-INDEXNOW-KEY-039`, Tier B) recommending IndexNow key hosting (`/{apiKey}.txt`) for instant push indexation to Bing, Yandex, and Seznam, with clear documentation distinguishing Google Search Console sitemap submission from the restricted Google Indexing API.
  - Added transparent pricing signal check (`has_pricing_link`) identifying accessible `/pricing` and `/pricing.md` endpoints for procurement agents.
  - Added `🤖 Autonomous Agent Readiness (Lighthouse Agentic Browsing)` executive section to markdown inspection reports.
- **Google Analytics 4 (GA4) AI-Referral Analyzer (`engine/analyzers/ga4_analyzer.py`, `--ga4-csv`):**
  - Pure Python stdlib analyzer for GA4 Traffic Acquisition CSVs (handling multi-locale headers and numeric formats).
  - Identifies and quantifies actual inbound referral traffic from ChatGPT, Perplexity AI, Claude, Google Gemini / AI Overviews (`googlequicksearchbox`), Microsoft Copilot, Meta AI, and You.com.
  - Calculates AI referral traffic share percentage, engaged sessions, engagement rate, and average session duration.
  - Integrates executive summary into CLI audit reports with explicit non-guarantee disclosures.
- **Google Search Console Content Decay Analysis (`engine/analyzers/gsc_analyzer.py`):**
  - Added `analyze_gsc_decay` detecting queries losing $\ge$ 20% clicks or impressions comparing historical baseline data against recent periods.
  - Generates Content Decay Alert tables highlighting URLs and queries requiring content refreshes and temporal updates.
- **Advanced GEO & Citation Testing Methodology (`SKILL.md`):**
  - Added Scientific Citation Testing Protocol: repeating prompts 3–5 times in clean unauthenticated sessions across models, evaluating citation stability and sentiment (Endorsed vs Neutral vs Negative).
  - Added "Citation $\ne$ Recommendation" guardrail: separating mere mentions from true recommendations.
  - Added honest guardrail for `/llms.txt`: clarifying that structured catalogs facilitate LLM context ingest but do not guarantee search rankings or citations.
  - Added The "Don't-Do" Anti-Pattern list (never block CSS/JS in robots.txt, never inject hidden text, never fabricate social proof or fake expert quotes, never cloak for user agents).
  - Added Brand Off-Page Footprint audit across primary AI training & retrieval sources (Reddit, Wikipedia, YouTube, LinkedIn, Quora, GitHub).
- **Evaluation & Test Harness (`evals/test_engine.py`, `evals/run_evals.py`):**
  - Added `test_v3_4_0_agentic_ga4_suite` expanding engine test suite to 29 deterministic test suites (59/59 total passing across canonical evals, mutations, and engine integration).

## [3.3.0] - 2026-09-28

### Added
- **Epistemic Honesty Guardrails (`SKILL.md`):**
  - Codified core epistemic principles: "Observations are not causes", honest-sizing (hypothetical potential visits only, zero invented revenue/conversion metrics), explicit date + geographic context on all checks, and strict separation between tools-reported data (`[VERIFIED_FACT]`) and agent heuristics (`[HEURISTIC_ESTIMATE]`).
  - Added 4-point Pre-Flight Self-Review Protocol ensuring audits do not make speculative causal claims or present estimates as facts.
- **Shortlist -> Decision Reporting Protocol (`SKILL.md`, `engine/inspector.py`):**
  - Redesigned executive recommendations into `🚀 Your Next SEO Move (Top Priorities)` formatted with deterministic `Do this:` actionable steps and `Why:` causal rationale (observed gap, category/priority, plausible benefit, and main uncertainty).
  - Added `📋 What Else We Checked (Deferred Opportunities)` section listing candidate issues that were evaluated but deferred with explicit rationale to keep user focus on highest-leverage actions.
- **Persistent Project Context (`engine/project_context.py`, `--project-context`):**
  - Added pure Python standard library `ProjectContext` manager supporting `seo-project-context.json` or `.seo-context.json`.
  - Maintains persistent dossier: business overview, target audience, key pages with roles, competitors, and 30-day research cache.
  - Automatically identifies prior audits within 30 days to avoid redundant re-analysis and displays baseline reuse notice in executive scorecard.
- **Google Search Console (GSC) Striking Distance Analyzer (`engine/analyzers/gsc_analyzer.py`, `--gsc-csv`):**
  - Pure Python stdlib CSV performance analyzer handling varied export locales and dialects (comma, semicolon, tab; English and Russian header aliases).
  - Automatically isolates high-leverage "Striking Distance" queries (positions 5.0–20.0 with $\ge$50 impressions) for immediate on-page lift.
  - Detects Page 1 Snippet Underperformers (positions $\le$10.0 with low CTR < 2.0%) flagging title pixel width and meta description rewrite opportunities.
  - Generates executive markdown summary table and integrates directly with audit reports and JSON metadata.
- **Evaluation & Test Harness (`evals/test_engine.py`, `evals/run_evals.py`):**
  - Added `test_v3_3_0_openseo_integration_suite` expanding engine test suite to 28 deterministic test suites (58/58 total passing across canonical evals, mutations, and engine integration).

## [3.2.0] - 2026-09-26

### Added
- **Performance & Core Web Vitals Suite (`engine/analyzers/performance_analyzer.py`):**
  - Added DOM size and maximum depth tracking (`PERF-DOM-005`, Tier E) per HTTP Archive benchmarks (warns at >1500 nodes or >32 depth).
  - Added `<head>` render-blocking resource detection (`PERF-RENDER-BLOCK-003`, Tier E) detecting synchronous stylesheets and scripts without `defer`/`async`.
  - Added hero image priority and resource hint checks (`PERF-RESOURCE-HINTS-006`, Tier E) flagging anti-patterns such as `loading="lazy"` on LCP hero image and validating `fetchpriority="high"`.
  - Added next-gen image format evaluation (`TECH-IMAGE-MODERN-038`, Tier E) calculating WebP/AVIF vs legacy JPEG/PNG asset distribution.
  - Added Google PageSpeed Insights API integration (`PERF-CWV-PSI-001` / `PERF-CWV-FIELD-007`, Tier C) evaluating real-user CrUX metrics with zero penalty when unmeasured (`UNKNOWN != FAILURE`).
- **Modern Technical SEO & Hygiene (`engine/inspector.py`, `rules/technical_rules.json`):**
  - Added robots.txt `Sitemap:` directive validation (`TECH-ROBOTS-SITEMAP-034`, Tier A) per RFC 9309.
  - Added URL structure hygiene check (`TECH-URL-STRUCTURE-037`, Tier B) flagging uppercase paths, path depth > 4, underscores, and session ID parameters (`jsessionid`, `phpsessid`, `aspsessionid`).
- **On-Page & Architecture Heuristics (`engine/analyzers/html_analyzer.py`, `engine/analyzers/content_analyzer.py`):**
  - Added title pixel width estimation (`estimate_title_pixel_width`) and H1 semantic parity (`CONTENT-TITLE-QUALITY-001`, Tier B) based on desktop Google SERP ~580px limit.
  - Added interrogative heading analysis and direct concise answer extraction (`CONTENT-QUESTION-HEADINGS-002`, Tier C) for PAA/AEO visibility.
  - Added extractable elements evaluation (`CONTENT-EXTRACTABLE-003`, Tier E) identifying tables, lists, and TL;DR summary blocks.
  - Added substantive content-to-boilerplate ratio calculation (`CONTENT-TEXT-RATIO-004`, Tier E).
  - Added Schema date vs visibly rendered date parity check (`CONTENT-DATE-VISIBLE-005`, Tier B).
- **GEO / AEO (Generative Engine Optimization) (`engine/analyzers/llms_analyzer.py`, `engine/scoring.py`):**
  - Implemented Position-Adjusted Word Weighting (`compute_pawc`, `GEO-PAWC-SCORE-001`, Tier C) applying exponential decay $W(s) = F(s) \cdot e^{-\alpha \cdot \frac{pos(s)}{N}}$ to factual assertions per Princeton KDD 2024.
  - Implemented `/llms.txt` specification parser (`GEO-LLMS-TXT-CHECK-006`, Tier E) verifying H1 title, blockquote summary, and structured documentation links.
  - Added `--generate-llms-txt` CLI argument compiling standard-compliant `/llms.txt` directly from inspected target metadata and internal link graph.
  - Added Search Retrieval AI crawler policy validator (`GEO-AI-BOT-POLICY-007`, Tier B) inspecting `OAI-SearchBot`, `PerplexityBot`, and `Claude-SearchBot` permissions.
  - Added statistical claims outbound source grounding (`GEO-CITATION-LINKS-008`, Tier C) verifying external reference links.
- **Schema Validation (`rules/schema_rules.json`):**
  - Added author `Person` byline parity (`SCHEMA-AUTHOR-LINK-012`, Tier B) verifying declared Schema author against rendered HTML text across both root and nested entity nodes.
- **Evaluation & Test Harness (`evals/test_engine.py`, `evals/run_evals.py`):**
  - Added `test_v3_2_0_performance_geo_pawc_suite` expanding engine test suite to 27 deterministic suites (57/57 total passing across canonical evals, mutations, and engine integration).

## [3.1.1] - 2026-09-26

### Fixed & Remediated
- **Crawler Broken Links Tracking (`engine/crawler.py`):**
  - Resolved bug where `broken_links` was never populated during site crawls. HTTP 4xx/5xx responses are now logged with status codes, depth, and inbound referring sources, and rendered in markdown and JSON reports.
- **End-to-End EngineConfig Wiring (`engine/inspector.py`, `engine/config.py`):**
  - Unified duplicate `CrawlConfig` classes between `config.py` and `crawler.py` with synchronized rate limit delays.
  - Wired `EngineConfig.load()` into CLI execution: `cfg.disabled_rules` now suppresses evidence deductions from the ledger, `cfg.crawl` populates crawl defaults, and `cfg.strict_mode` enforces CI quality gates against custom thresholds.
- **SSRF Hardening & Safe Redirects (`engine/security_utils.py`, `engine/analyzers/http_analyzer.py`):**
  - Fixed critical SSRF vulnerability: implemented `is_safe_target_url` validation across all initial targets and every HTTP redirect hop in `SafeRedirectTracker`. Prevents access to loopback, link-local (cloud metadata `169.254.169.254`), private RFC 1918 networks, and IPv6 mapped addresses.
- **Cloudflare Challenge False Positive Elimination (`engine/analyzers/http_analyzer.py`):**
  - Removed false-positive challenge detection on 403/503 responses that merely contain the ubiquitous `cf-ray` header. Now exclusively detects genuine challenges via `cf-mitigated: challenge` or specific challenge body markers.
- **Prompt Injection Exemption for Documentation (`engine/analyzers/security_analyzer.py`):**
  - Added smart content exemptions for `<code>`, `<pre>`, `<kbd>`, `<samp>`, and `<blockquote>` blocks, preventing false positive security penalties on technical blogs, tutorials, and cybersecurity articles citing injection payloads.
- **Refined CSR Empty Shell & Soft-404 Detection (`engine/analyzers/html_analyzer.py`):**
  - Prevented compact SSR pages (e.g. Next.js/Nuxt landing pages with rendered H1 and concise copy) from being falsely marked as empty CSR shells or non-indexable.
  - Refined soft-404 detection to avoid false positives on troubleshooting guides discussing 404 errors.
- **Scoring Invariant & Version Sync (`engine/scoring.py`, `engine/sarif.py`, `engine/__init__.py`):**
  - Restored invariant: missing schema is now registered in `unknown_dimensions` for the `schema_graph` component.
  - Resolved version drift across `engine/__init__.py`, SARIF driver, and User-Agents to `v3.1.1`.
- **Honest Positioning & Boundaries (`README.md`, `README.ru.md`):**
  - Added explicit "Scope & Boundaries" section detailing core strengths (On-page technical, Schema AST, internal link graph, prompt injection defense, Princeton GEO model) vs non-goals (external backlink profiling, live SERP rank tracking, CrUX field measurements).

## [3.1.0] - 2026-09-18

### Added
- **Epistemic Tier System & Source Registry (`references/sources.json`, `METHODOLOGY.md`):**
  - Standardized all rules and evidence ledger findings with strict 6-tier classification (`Tier A`..`Tier F`) and explicit linkage to verified primary sources (RFCs, W3C, Schema.org, Google Search Central, Princeton KDD, OWASP).
  - Deterministic anti-inflation validator (`validate_epistemic_integrity()`) preventing promotion of heuristics or unofficial tips to standard protocols.
- **Web Content Prompt Injection Defense (`engine/analyzers/security_analyzer.py`):**
  - Scans crawled web content for adversarial prompt injection payloads targeting LLMs: direct instruction overrides, role hijacks, delimiter attacks (`[INST]`, `<|im_start|>`), and hidden CSS elements (`display:none`, `font-size:0`, invisible comments).
  - Segregated `SEC-PROMPT-INJECTION-001` critical security finding and sanitization utility (`sanitize_for_llm()`).
- **Indexability Matrix v2 (`engine/indexability.py`):**
  - Added `CONFLICTED` state with explicit multi-signal conflict detection (e.g. sitemap inclusion vs robots.txt disallow, self-canonical vs noindex, HTTP header vs meta tag robots).
- **AI Citation Benchmark Experimental Layer (`engine/experiment.py`):**
  - Structured tracking of citation experiments (`experiments/sample_before.json`, `experiments/sample_after.json`) with strict non-causal disclaimers preserving epistemic integrity.
- **Unified Engine Configuration (`ultimate-seo-geo.json`, `engine/config.py`):**
  - Centralized configurable thresholds, timeouts, and scoring parameters with graceful fallback defaults.
- **Expanded Test Harness (53 automated tests passing):**
  - 10/10 Canonical fixture evals.
  - 20/20 Negative mutation and adversarial defense tests.
  - 23/23 Deterministic engine integration tests.

## [3.0.0] - 2026-09-17

### Added
- **Full Roadmap Completion (`todo.md` Weeks 1, 2, 3, 4):**
  - **Site-Level Crawler & Architecture Graph:** Polite BFS site crawler (`--crawl`, `--max-pages`, `--depth`) with SSRF protection, crawl depth tracking, orphan page discovery, and 64-bit SimHash/Jaccard near-duplicate content clustering.
  - **Deterministic Indexability Matrix:** Multi-signal evaluation (HTTP, canonical, meta robots, X-Robots-Tag, robots.txt, sitemaps, internal links, rendered content) into an unambiguous indexability verdict.
  - **Princeton KDD 2024 8-Component GEO Model:** Answerability (20%), Evidence density (20%), Entity clarity (15%), Passage extractability (15%), Source attribution (10%), Schema graph (10%), Freshness (5%), and AI crawler access (5%) with epistemic confidence rating.
  - **E-E-A-T & Trust Profile:** Author bio, verified `sameAs` entity links, organization credentials, transparency touchpoints (About/Contact/Editorial), YMYL detection & disclaimers, and first-hand experience markers.
  - **Freshness & Temporal Consistency:** Validates publication/modification dates, sitemap `lastmod` alignment, HTTP `Last-Modified`, content hashes, date discrepancies, and flags stale content (>2 years).
  - **Hardened Schema.org Validator:** Validates unified `@graph` ASTs, detects duplicate `@id` definitions, enforces required properties for high-value types (Article, Product, Org, FAQ, Breadcrumbs), and provides a 4-tier rich result eligibility verdict.
  - **OASIS SARIF v2.1.0 Exporter:** Turnkey GitHub Code Scanning & CI integration (`--sarif` or `--format sarif`).
  - **Production CI/CD Quality Gates:** Added `--strict`, `--fail-on <P0|P1|P2|CRITICAL|WARNING>`, `--fail-on-score <threshold>`, and `--previous-audit <audit.json>` for automated delta scoring and regressions tracking.
  - **Segregated Security Hygiene Score:** Independent 0..100 dimension for HTTPS wire, HSTS headers, mixed content, and security headers.
  - **Expanded Engine Integration Suite:** 17/17 engine tests, 10/10 canonical evals, 9/9 mutation tests passing 100%.

## [2.1.0] - 2026-09-17

### Added
- **CSR Empty Shell Detection (`TECH-CSR-SHELL-008`):** Deterministic detection of client-side rendered mounts (`div#root`, `div#app`, `div#__next`) with empty/sparse text. Warns of complete invisibility to fast AI search crawlers (`GPTBot`, `ClaudeBot`, `PerplexityBot`) that do not execute client-side JavaScript.
- **Standalone Schema.org AST Validator CLI (`--validate-schema`):** Pre-flight validation of JSON-LD snippets before presentation to users, catching broken `@id` cross-references (`SCHEMA-BROKEN-REF-005`), invalid ISO 8601 date formats (`SCHEMA-DATE-FORMAT-006`), and non-numeric price formats (`SCHEMA-PRICE-FORMAT-003`).
- **Strict Just-In-Time (JIT) Reference Loading in `SKILL.md`:** Prohibits eager loading of all 5 reference manuals simultaneously. Limits reference reading strictly to the single targeted file needed for the active mode, protecting agent context window from "lost in the middle" degradation.
- **New Integration Tests:** Added `test_csr_shell_detection` and `test_schema_standalone_validator` to `evals/test_engine.py` (6/6 engine tests passing).

## [2.0.0] - 2026-09-17

### Added
- **Autonomous Inspection Engine (`engine/`):** Full-fledged, zero-dependency (pure standard library Python 3.10+) deterministic execution engine.
- **CLI Inspector Runner (`engine/inspector.py`):** Execute audits directly via `python -m engine.inspector <target> [--format markdown|json] [--output path]`.
- **RFC 9309 Crawler Simulator (`engine/analyzers/robots_simulator.py`):** Deterministic AST parser and access simulator for `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`, and search bots with longest-match and Allow-precedence rules.
- **Schema.org AST Analyzer (`engine/analyzers/schema_analyzer.py`):** JSON-LD syntax validator, `@graph` entity AST indexer, orphaned entity detector, and Google Merchant Offer price format validator.
- **Content & GEO Readiness Analyzer (`engine/analyzers/content_analyzer.py`):** Direct answer detector, adaptive passage chunking analyzer, and coreference independence checker.
- **Declarative Rule Contracts (`rules/`):** Machine-readable contract definitions in `technical_rules.json`, `schema_rules.json`, and `geo_rules.json`.
- **Automated Engine Integration Suite (`evals/test_engine.py`):** 4 new automated integration tests covering clean page inspection, defective page detection, RFC 9309 simulation, and unmeasured signal score invariants.

## [1.6.0] - 2026-09-17

### Added
- **Evidence Ledger Protocol & Schema:** Mandatory structured tabular output in Mode 1 (`audit`) containing `Finding ID`, `Target / Selector`, `Observed Evidence`, `Status (PASS/FAIL/UNKNOWN)`, `Epistemic Tier (Tier A-F)`, `Confidence`, `Impact`, and actionable `Remediation`.
- **6-Tier Evidence Hierarchy:** Formalized epistemic ladder from Tier A (Official Protocol Standards) to Tier F (Working Hypotheses) with strict Epistemic Promotion Invariant preventing elevation of Tier E/F heuristics to Tier A/B status.
- **"Unknown != Failure" Scoring Invariant:** Unobservable criteria (CrUX real-user telemetry without API keys, server access logs, third-party backlink indices) are explicitly marked `UNKNOWN` and do not penalize the Observable Technical SEO Score.
- **Observation Coverage Ratio:** Reports disclose the percentage of total criteria actually verifiable from available inputs ($N_{\text{PASS}} + N_{\text{FAIL}} / N_{\text{Total}}$).
- **New Diagnostic Evals (10 total):**
  - `audit-unobserved-field-data-unknown`: verifies that unobserved field telemetry is correctly marked `UNKNOWN` without score penalties.
  - `tier-hierarchy-anti-inflation`: verifies that RAG chunking is classified as Tier E (Heuristic) and rejects false attribution to official RFC/Google standards.
- **New Negative Mutation Tests (9 total):**
  - `mutation_audit_missing_evidence_ledger`: rejects audits lacking the required Evidence Ledger.
  - `mutation_false_standard_tier_inflation`: rejects attempts to falsely promote Tier E heuristics to official RFC standards.

### Changed
- Bumped evals suite and test harness to v1.6.0.
- Synchronized Evidence-Driven Architecture diagram across `README.md`, `README.ru.md`, and `SKILL.md`.

## [1.5.0] - 2026-09-17

### Added
- Automated negative mutation and anti-regression testing suite in `evals/run_evals.py` verifying that leaky robots configurations, invalid schema prices, disconnected `@graph` entities, keyword-stuffed text, accepted fake stats, out-of-bounds scores, and unhandled eval IDs are reliably rejected.
- Robust, fixed-width sentence splitting heuristic protecting numeric decimals (`1.84ms`) and abbreviations (`Dr.`, `Mr.`, `RFC`) from splitting errors.
- Comprehensive English stopword filtering in keyword density validation to eliminate false positives on common connecting words.
- Active validation of 100% of declared assertion keys (`score_ranges`, `graph_interconnected`, `no_multiple_scripts`, `robots_has_ai_crawlers`, `robots_disallow_leak_prevention`, `llms_txt_markers`, `contains_clusters`, `cluster_count`, `per_topic_requirements`, `fabricated_stats_unendorsed`).
- Distinct author ORCID identifiers for multi-author Schema samples (`0000-0001-5432-9876` for Alex Mercer, `0000-0002-1825-0097` for Jane Doe).

### Changed
- Corrected Princeton KDD 2024 academic citations in `references/geo-framework.md` to Section 5.3 ("Analysis of Strategy Combinations"): Fluency Optimization + Statistics Addition delivers >5.5% relative gain over the best single individual strategy on the 200-query benchmark subset.
- Removed speculative claims attributing sub-additivity to "attention mechanisms and overlapping token attribution" and unsupported "+35% to +44%" figures.
- Restricted Democratization Effect claims strictly to Google top-5 candidates evaluated in Princeton paper Table 2 (Rank 1: -30.3%, Rank 5: +115.1%), eliminating unsupported "Rank 6-10" mentions.
- Synchronized Google Search FAQ rich results policy across `SKILL.md`, `README.md`, `README.ru.md`, and `references/schema-templates.md` to document the May 7, 2026 complete discontinuation across all domains.
- Harmonized mode taxonomy: clarified 5 operational user-facing modes (`audit`, `optimize`, `schema`, `ai-files`, `strategy`) + 1 internal evaluation harness mode (`safety_check`).
- Fixed silent pass on unknown `eval_id`s in `run_evals.py`: now fails fast with an explicit error.
- Bumped test suite version to 1.5.0.

## [1.4.0] - 2026-09-17

### Added
- Epistemological Classification Matrix with explicit badges (`[STANDARD]`, `[RESEARCH]`, `[HEURISTIC]`, `[RECOMMENDATION]`) across all references, checklists, and scorecards.
- Dual audit confidence ratings: `Technical SEO Score: High Confidence (Deterministic Standards)` vs `GEO Score: Medium Confidence (Qualitative Heuristics)`.
- Benchmark generalization disclaimer explicitly qualifying Princeton KDD 2024 experimental lift deltas on synthetic test queries.
- Adaptive passage chunking (~100–200 words) replacing rigid word count dogmatism.
- Coreference independence and entity disambiguation replacing arbitrary pronoun density ratios.
- Differentiated query-dependent freshness guidelines (volatile/pricing vs evergreen/RFC specifications).
- Explicit `[EXAMPLE — REPLACE WITH REAL BENCHMARK]` placeholders in Schema templates.

### Changed
- Re-derived PAWC formulation to strictly clarify exponential attention decay over sentences in the synthesized LLM response $r$, clarifying that source lead front-loading is an editorial RAG chunking heuristic.
- Separated Crawl Governance and indexation control (RFC 9309) from Security and access authorization (RFC 9110 / HTTP 401/403).
- Updated assertion in `rewrite-for-pawc-evidence` from `contains_numerical_metrics` to `contains_verified_metrics_or_placeholders`, maintaining 100% Zero Fabrication compliance.
- Nuanced Ahrefs brand footprint study regarding established domains ($DR > 40$) and the continued necessity of backlinks for Stage 1 candidate retrieval.

## [1.3.0] - 2026-09-17

### Added
- `adversarial-fabrication-rejection` test case validating strict enforcement of the Zero Fabrication rule.
- `safety_check` internal mode asserting that the agent refuses prompts to invent fake quotes, credentials, or fabricated statistics.
- `audit-api-docs-quote-exemption` regression test ensuring technical documentation and API pages are not penalized for omitting human quotes.
- `diagnose-robots-noindex-conflict` edge-case test verifying diagnosis of robots.txt blocking noindex tag evaluation per RFC 9309.
- Test runner and schema validation harness (`evals/run_evals.py`) with formal deterministic regexes for currency, quote count, and keyword density thresholds.

### Changed
- Cleaned redundant superstring `"AI Infrastructure & Crawlability"` from `contains_any_section` assertion in `audit-landing-page`.
- Replaced third-party test domain with RFC 2606 `https://example.com` in `audit-landing-page`.
- Synchronized passage citability assertions and platform divergence criteria with Princeton KDD 2024 and Ahrefs brand footprint studies.

## [1.2.0] - 2026-09-16

### Added
- `heuristic_notice_present` assertion requiring qualitative LLM audit disclaimers.
- Markdown token matching assertions for Schema JSON-LD outputs.

## [1.1.0] - 2026-09-16

### Added
- Assertion for RFC 9309 duplicate disallow rules in `generate-robots-txt`.

## [1.0.0] - 2026-09-16

### Added
- Initial baseline evaluation suite covering the 5 core operational modes: `audit`, `optimize`, `schema`, `ai-files`, and `strategy`.
