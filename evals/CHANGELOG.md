# Evaluation Suite Changelog

All notable changes to the `ultimate-seo-geo` evaluation benchmark will be documented in this file.

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
