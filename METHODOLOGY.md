# Epistemic Methodology & Tier Hierarchy

**Version**: 3.1.0  
**Status**: Production Standard  
**Framework**: 6-Tier Epistemic Authority Model  

---

## 1. Core Principles

The `ultimate-seo-geo` platform evaluates technical SEO, Generative Engine Optimization (GEO), and security signals using strict epistemic segregation.

### 1.1 Zero Epistemic Inflation
A heuristic observation (such as optimal passage chunk length) must never be conflated with an official protocol standard (such as RFC 9110 or RFC 9309). Every rule, signal, and finding in the platform is permanently assigned an explicit authority tier.

### 1.2 "Unknown != Failure" Invariant
An unobserved signal (e.g., real-user CrUX field data when no API token is configured, or an unreachable external sitemap index) is classified as `UNKNOWN` or `NOT_MEASURED`. It carries strictly **0 score penalty** and does not lower the technical score.

### 1.3 Non-Causal AI Visibility Phrasing
Because generative engine ranking and retrieval depend on proprietary, non-deterministic neural weights, no audit finding may guarantee AI search inclusion. All GEO recommendations are phrased as probability enhancers supported by empirical correlation or document engineering best practices.

---

## 2. The 6 Epistemic Authority Tiers

| Tier | Category | Definition | Authority Source Examples | Score Impact Policy |
|---|---|---|---|---|
| **Tier A** | **Protocol / Standard** | Hard technical specifications governed by international standards bodies (IETF, W3C, sitemaps.org). Non-compliance breaks mechanical transport or machine parsing. | RFC 9110 (HTTP), RFC 9309 (Robots Exclusion), RFC 8288 (Web Linking), W3C HTML5 | Critical/Warning: Immediate technical penalty up to 25 pts. |
| **Tier B** | **Official Search Engine Documentation** | Explicit crawl, indexing, and rich-result requirements published by major search engines. | Google Search Central, Bing Webmaster Tools, OpenAI OAI-SearchBot documentation | Warning/Critical: Direct impact on indexability or search eligibility. |
| **Tier C** | **Empirical / Peer-Reviewed Research** | Statistically validated findings published in academic papers or large-scale dataset evaluations. | Aggarwal et al. (Princeton KDD 2024 GEO paper), Chrome UX Report | Information/Warning: Influences GEO Readiness Index. |
| **Tier D** | **Industry Evidence & Security Standards** | Standardized threat models, security best practices, and consensus industry benchmarks. | OWASP Top 10 for LLMs, HTTP Archive / Web Almanac | Critical/Warning: Segregated Security Hygiene score. |
| **Tier E** | **Practical Heuristics** | Document engineering rules of thumb derived from RAG architectures, token context windows, and SERP snippet displays. | Adaptive passage chunking (150–300w), inverted pyramid leads, title lengths (50–60 chars) | Advisory/Warning: Influences GEO chunking points; zero technical penalty. |
| **Tier F** | **Best-Practice Recommendations** | Editorial, stylistic, or accessibility enhancements that improve human UX and machine comprehension. | HTML semantic landmarks (`<main>`, `<nav>`), form labels, heading hierarchy | Info/Advisory: Low penalty weight (1–5 pts). |

---

## 3. Source Registry (`references/sources.json`)

All Tier A, B, and C rules reference verified IDs in `references/sources.json`. Every entry documents:
- `claim_id`: Unique identifier
- `source_title`: Publication name
- `source_url`: Verifiable canonical link
- `source_type`: `standard` | `official` | `research` | `industry` | `heuristic`
- `verified_at`: Timestamp of latest verification
- `confidence`: `high` | `medium` | `low`

---

## 4. Indexability Verdicts

The Indexability Matrix synthesizes 8 vectors (HTTP, Canonical, Meta Robots, X-Robots, Robots.txt, Sitemap, Internal Links, Rendered Content) into 4 deterministic verdicts:

1. **`INDEXABLE`**: All primary crawl and index vectors are clear.
2. **`BLOCKED`**: Hard barriers prevent indexing (HTTP error, meta noindex, robots disallow, empty CSR).
3. **`CONFLICTED`**: Webmaster directives contradict each other:
   - Sitemap includes URL, but `robots.txt` Disallow blocks it.
   - Page specifies `rel=canonical` to self, but delivers `X-Robots-Tag: noindex`.
   - HTML meta robots specifies `index`, but HTTP header specifies `noindex`.
4. **`AMBIGUOUS`**: Indeterminate signals requiring manual review (canonical pointing to external URL, URL redirect, orphan candidate).

---

## 5. AI Citation Experiment Methodology

The experimental layer (`engine/experiment.py`) evaluates real before/after query runs across AI search models:
- **Citation Rate**: \(\frac{\text{Queries Citing Target Domain}}{\text{Total Benchmark Queries}} \times 100\)
- **Brand Mention Rate**: \(\frac{\text{Answers Explicitly Mentioning Target Brand}}{\text{Total Benchmark Queries}} \times 100\)
- **Source Selection Rate (Top-3)**: \(\frac{\text{Queries Selecting Target in Top 3 Sources}}{\text{Total Benchmark Queries}} \times 100\)
- **Average Citation Rank**: Mean position of target domain in the citation array.
