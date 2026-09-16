# Evaluation Suite Changelog

All notable changes to the `ultimate-seo-geo` evaluation benchmark will be documented in this file.

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
