# Evaluation Suite Changelog

All notable changes to the `ultimate-seo-geo` evaluation benchmark will be documented in this file.

## [1.3.0] - 2026-09-17

### Added
- `adversarial-fabrication-rejection` test case validating strict enforcement of the Zero Fabrication rule.
- `safety_check` internal mode asserting that the agent refuses prompts to invent fake quotes, credentials, or fabricated statistics.
- Test runner and schema validation harness (`evals/run_evals.py`).

### Changed
- Cleaned redundant superstring `"AI Infrastructure & Crawlability"` from `contains_any_section` assertion in `audit-landing-page`.
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
