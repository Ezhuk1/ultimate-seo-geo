# Mode 1: Comprehensive Evidence-Driven Audit (`audit`)

This manual details the complete protocol for conducting technical SEO and Generative Engine Optimization (GEO) audits.

---

## 1. Automated Execution via Engine CLI

When environment tools (terminal or shell execution) are available, run the deterministic inspection engine directly:

```bash
# Single page deterministic inspection:
python -m engine.inspector <URL or file_path> [--format markdown|json|sarif]

# Multi-page BFS site crawl with link graph, crawl depth & orphan detection:
python -m engine.inspector https://example.com --crawl --max-pages 50 --depth 3

# CI/CD Quality Gate with SARIF export and threshold enforcement:
python -m engine.inspector https://example.com --strict --fail-on P0 --fail-on-score 80 --sarif report.sarif
```

The engine measures HTTP wire payloads with SHA-256 provenance, simulates RFC 9309 crawler permissions, validates the Schema.org `@graph` AST, evaluates GEO content extractability rules, and compiles the Evidence Ledger.

---

## 2. The Evidence Ledger Protocol `[STANDARD]`

Every audit MUST compile a structured Evidence Ledger table providing deterministic proof for each finding:

| Finding ID | Target / Selector | Observed Evidence | Status | Epistemic Tier | Confidence | Impact | Remediation |
|---|---|---|:---:|:---:|:---:|:---:|---|
| `TECH-CANONICAL-001` | `link[rel='canonical']` | `https://example.com/page` | PASS | Tier A (RFC 6596) | HIGH | — | None. |
| `TECH-ROBOTS-002` | `robots.txt` | Disallow: /admin/ | PASS | Tier A (RFC 9309) | HIGH | — | Maintained. |
| `GEO-ANSWER-FRONTLOAD-001`| `body > p:first-of-type` | Definition in first 35 words | PASS | Tier C (Princeton KDD) | MEDIUM | — | Compliant. |
| `PERF-CWV-FIELD-003` | CrUX API / Field Telemetry | Unobserved (no CrUX API key provided) | UNKNOWN | Tier C (Field Telemetry) | LOW | P2 | Inspect field LCP/INP via PageSpeed API. |
| `GEO-DEFINITION-004` | First 60 words of lead section | Direct answer formula present | PASS | Tier E (Heuristic) | MEDIUM | — | None. |

---

## 3. Observation Coverage & Dual Scoring Structure

1. **Observable Technical Score (0–100) [Confidence: HIGH — Deterministic Standards (Tier A/B)]:**
   - Evaluated exclusively against observed, verifiable technical criteria across 4 layers:
     - *Layer 1 (Protocol & Crawlability, Tier A/B):* HTTP status semantics (RFC 9110), robots.txt parsing syntax & 500KiB ceiling (RFC 9309), XML sitemap limits (50MB / 50k URLs).
     - *Layer 2 (Indexability & Directives, Tier B):* Meta robots and X-Robots-Tag indexability, canonical duplicate consolidation (RFC 6596; preserving query parameters in comparisons), hreflang reciprocity and ISO 639-1 / 3166-1 syntax (with missing `x-default` treated as advisory `STATUS_INFO`).
     - *Layer 3 (SERP Snippet Presentation & Experience, Tier E):* Desktop `<title>` pixel width ($\le$580px, character count auxiliary), `<meta name="description">` (70–165 characters, noting ~70% are rewritten dynamically by Google), and semantic single primary `<h1>` document outline.
     - *Layer 4 (Interface Accessibility, Tier A/WCAG):* Viewport zoom accessibility (WCAG 2.1 AA), distinct from search ranking criteria.
   - *Low-Coverage Caveat:* If observation coverage is low (e.g. only 1 or 2 criteria verified), the report MUST disclose the exact fraction ($N_{\text{PASS}} / (N_{\text{PASS}} + N_{\text{FAIL}})$) with an explicit caveat (*"Partial evaluation: 1/1 criteria passed; coverage 5%"*) and must not headline as an unconditional "Technical SEO Score 100/100".

2. **Observation Coverage Ratio (%) [Completeness Indicator]:**
   $$\text{Observation Coverage} = \frac{N_{\text{PASS}} + N_{\text{FAIL}}}{N_{\text{Total Criteria}}} \times 100\%$$
   - Unobserved criteria (e.g., real-user CrUX field data, server access logs, backlink graphs) are classified as `UNKNOWN` or `NOT_MEASURED` (strictly separated from measured statuses) and do **NOT** depress the Observable Score.

3. **Content Structural Extractability Check (0–100, formerly GEO Readiness Index) [Confidence: MEDIUM — Qualitative Heuristics (Tier E) & Benchmarks (Tier C)]:**
   - Evaluated across 8 weighted dimensions:
     - *Answerability (20%):* Direct definition / resolution syntax in opening 60 words `[RESEARCH]`.
     - *Evidence Density (20%):* Numerical statistics, percentages, and verifiable metrics with semantic relevance `[RESEARCH]`. Dates, phone numbers, and zip codes do NOT count as empirical evidence.
     - *Entity Clarity (15%):* Coreference independence across lead sentences and chunk openings (avoids ambiguous pronouns) `[HEURISTIC]`.
     - *Passage Extractability (15%):* Modular 100-200 word sections suited for vector retrieval `[HEURISTIC]`.
     - *Source Attribution (10%):* Authoritative citations, RFC standards, research refs `[RESEARCH]`.
     - *Schema & Entity Graph (10%):* Interconnected JSON-LD graph with stable @id anchors `[STANDARD]`.
     - *Freshness & Temporal (5%):* Publication/modification dates and temporal consistency `[DOCUMENTED]`.
     - *AI Crawler Access (5%):* Search & retrieval AI bots permitted in robots.txt `[STANDARD]`.
   - **Content Depth Guard:** Substantive content under 25 words zeroes out all 5 text-dependent dimensions (`dim_ans`, `dim_ent`, `dim_ev`, `dim_src`, `dim_chunk`), preventing stub pages or empty shells from earning unearned high scores.

4. **Independent Security & Prompt Injection Hygiene Score (0–100) [STANDARD / OWASP]:**
   - Strictly segregated dimension (HTTPS 25%, HSTS 25%, Mixed Content 25%, Security Headers 25%).
   - Adheres strictly to "Unknown $\ne$ Failure": if no security signals are observed or target is unmeasured, the score is 0 / `NOT_MEASURED` (zero free points; never awards free points for unmeasured targets).
   - **Prompt Injection Defense (`SEC-PROMPT-INJECTION-001`):** Autonomous scanning for indirect prompt injection vectors in crawled web text, protecting LLM synthesis contexts. Markdown code fences and backticks are exempted.

5. **Deterministic Indexability Matrix v2 [STANDARD]:**
   - Multi-vector verdict (`INDEXABLE`, `BLOCKED`, `AMBIGUOUS`, `CONFLICTED`) across HTTP status, Canonical URL (query string preserved), Meta Robots, `X-Robots-Tag: noindex`, Robots.txt, Sitemap, Internal Links, and Rendered Payload.
   - **Decoupled CSR Mount Shell Verdicts:** Report observations in two distinct layers:
     - *Layer 1 (Raw HTML Observation):* Verify whether substantive text is present (>100 words) or missing (<25 words).
     - *Layer 2 (Engine Extraction Risk):* If substantive text is missing from raw HTML, record *High Extraction Risk (Unknown)* for non-rendering AI crawlers and *Rendering Queue Latency Risk* for Googlebot evergreen Chromium. Never declare unconditional `BLOCKED` without confirming missing content.
   - **Link Graph Topology:** Classifies 0 outbound internal links on single-page inspection as `terminal (0 outbound)`. Reserves orphan candidate warnings (`AMBIGUOUS`) for crawl graph verification where `inbound_internal_links_count == 0`.

6. **Answer Engine Optimization (AEO & Direct Answers) (0–100) [RESEARCH / STANDARD / HEURISTIC]:**
   - Direct Answer Definition (25 pts): Definition frontloaded in opening 40–60 words (`GEO-ANSWER-FRONTLOAD-001`).
   - Question Headings (20 pts): H2/H3 natural question phrasing immediately followed by direct 40–60 word answer paragraphs (`CONTENT-QUESTION-HEADINGS-002`).
   - Section Inverted Pyramid (15 pts): Core takeaway/conclusion stated at the beginning of each subsection (`GEO-SECTION-PYRAMID-024`).
   - Passage Autonomy (15 pts): Standalone chunks free of unresolved pronouns/coreferences (`GEO-COREFERENCE-INDEPENDENCE-003`, `GEO-ADAPTIVE-CHUNKING-002`).
   - Citation Deep-Link Anchors (10 pts): Explicit section IDs for precise AI quote deep-linking (`GEO-ANCHOR-DEEPLINK-023`).
   - Extractable Formats (10 pts): Tabular or step-by-step summary structures (`CONTENT-EXTRACTABLE-003`).
   - Machine & Voice Markup (5 pts): `SpeakableSpecification` (`SCHEMA-SPEAKABLE-027`), FAQPage, or HowTo markup for assistive and voice engines.

---

## 4. Prioritized Remediation Plan with Falsifiability Checks

* **P0 (Critical / Blockers):** Confirmed crawl blockouts on business-critical pages (`noindex` on primary landing page, robots.txt disallowing search bots from entire site), active server 5xx errors, confirmed open unauthenticated access to sensitive endpoints, or contradictory indexing directives (`CONFLICTED`).
  - *Leading Indicator:* Server log confirms 200 OK without crawl obstruction; conflicting directives resolved.
* **P1 (High Extraction & Snippet Impact):** Evidence deficit on research articles, missing structured Schema `@graph`, missing `dateModified` on time-sensitive guides, poor direct answer positioning, pronoun ambiguity in lead sentences, social preview title conflict (`SOCIAL-PREVIEW-SYNC-033`).
  - *Leading Indicator:* Schema Validator passes 0 errors; social link previews render correct metadata.
* **P2 (Hygiene & Polish):** Missing canonical on unique pages without parameter duplicates, missing image dimensions/alt tags, missing Open Graph / Twitter metadata, unobserved field metrics, missing `dateModified` on evergreen reference pages.
  - *Leading Indicator:* Clean social cards; zero CLS warnings.

---

## 5. Executive Reporting Protocol: Shortlist -> Decision & "Do this / Why"

Do not bury the reader in raw crawler output. Structure strategic feedback around high-impact triage:
1. **Shortlist Candidates First:** Identify 5–8 candidate issues across crawl blockers, underperforming high-demand pages, and direct answer gaps.
2. **Select Top 1–3 Next Moves ("Your Next SEO Move"):** Prioritize only the 1–3 highest-leverage actions with a credible path to tangible gain.
3. **Action Format ("Do this / Why"):**
   - **Do this:** 2–4 concise bullets starting with active verbs naming the exact page, selector, or attribute to change.
   - **Why:** 2–4 bullets detailing the observed gap, target searcher intent, plausible benefit, and main uncertainty (*main uncertainty* stays paired with benefit).
4. **"What Else We Checked" Table:** Move all rejected or deferred candidate issues into a compact table with an honest decision reason.

---

## 6. Pre-Flight Self-Review Protocol

Before delivering the final audit report or advice, execute a strict 4-point self-review:
1. **Check Evidence Grounding:** Does the leading recommendation cite verified raw observations from the Evidence Ledger?
2. **Review the Rejected Runner-Up:** Does the "What else we checked" table provide a credible, business-grounded reason why the leading recommendation beats the runner-up?
3. **Enforce Brevity:** Eliminate paragraph-length bullets and consulting jargon. Ensure bullets are 8–20 words with one idea each.
4. **Check Guardrails:** Are all scenarios labeled as hypothetical? Are all dates and locales explicit? Are there zero fabricated conversion rates or revenue claims?
