# Technical SEO Checklist & Standards

This reference details the core technical foundation required for modern search indexation and crawl optimization.

## 1. Crawlability & Indexability `[STANDARD]`
- **Robots.txt:**
  - Placed at root (`/robots.txt`), responds with HTTP 200.
  - Does not block critical CSS, JS, or image assets.
  - Links to canonical XML sitemap via `Sitemap: https://domain.com/sitemap.xml`.
- **XML Sitemaps:**
  - Placed at `/sitemap.xml` (or sitemap index).
  - Contains only 200 OK canonical URLs (no 301/302 redirects, no 404s, no noindex pages).
  - Includes `<lastmod>` timestamps matching real server updates.
- **Canonical URLs:**
  - Every page must define `<link rel="canonical" href="https://domain.com/exact-canonical-path" />`.
  - Self-referencing canonicals on primary pages.
  - No trailing slash mismatches (enforce uniform trailing-slash policy).
- **Internationalization (Hreflang):**
  - If multilingual, include bi-directional hreflang annotations in HTML or sitemap:
    ```html
    <link rel="alternate" hreflang="en" href="https://domain.com/en" />
    <link rel="alternate" hreflang="ru" href="https://domain.com/ru" />
    <link rel="alternate" hreflang="x-default" href="https://domain.com/" />
    ```

---

## 2. On-Page Semantic Structure `[RECOMMENDATION]` & `[HEURISTIC]`
- **Title Tags:**
  - Display Guideline: ~50–60 characters (recommended target to prevent SERP truncation on desktop ~600px containers; longer titles are indexed and evaluated by Google, not penalized).
  - Format: `Primary Keyword - Secondary Benefit | Brand Name`.
  - Unique across all indexable URLs.
- **Meta Descriptions:**
  - Display Guideline: ~140–160 characters (recommended snippet preview window).
  - Includes value proposition, target query, and clear call-to-action.
- **Heading Hierarchy (Accessibility & Semantic Best Practice):**
  - Recommended: One clear primary `<h1>` per page reflecting the main entity or topic. (Google Search handles multiple `<h1>` tags gracefully, but a single primary heading represents the cleanest document outline).
  - Structural nesting: Maintain a logical `h1` → `h2` → `h3` outline for screen reader accessibility, human scannability, and RAG chunk segmentation. (Note: Skipped heading levels are not a Google Search ranking penalty, but a semantic hygiene warning).
  - Headings should formulate clear questions or concrete topic descriptors.
- **Image Optimization:**
  - Semantic `<img />` tags with descriptive, contextual `alt` attributes.
  - Explicit `width` and `height` attributes to eliminate Cumulative Layout Shift (CLS).
  - Modern formats: WebP / AVIF with lazy loading on below-the-fold assets (`loading="lazy"`).

---

## 3. Core Web Vitals (CWV) Standards `[STANDARD]`

| Metric | Target (Good) | Needs Improvement | Poor | Primary Root Causes |
|---|:---:|:---:|:---:|---|
| **LCP** (Largest Contentful Paint) | $\le 2.5\text{ s}$ | $2.5\text{ s} - 4.0\text{ s}$ | $> 4.0\text{ s}$ | Unoptimized hero images, slow TTFB, client-side JS blocking |
| **INP** (Interaction to Next Paint) | $\le 200\text{ ms}$ | $200\text{ ms} - 500\text{ ms}$ | $> 500\text{ ms}$ | Heavy main-thread JavaScript execution, un-debounced inputs |
| **CLS** (Cumulative Layout Shift) | $\le 0.1$ | $0.1 - 0.25$ | $> 0.25$ | Images without dimensions, dynamically injected ads/banners |

---

## 4. Social Metadata (Open Graph & Twitter) `[STANDARD]`
Ensure optimal link previews across messaging apps and social feeds:
```html
<!-- Open Graph -->
<meta property="og:type" content="website" />
<meta property="og:title" content="Page Title" />
<meta property="og:description" content="Engaging summary of page content." />
<meta property="og:url" content="https://domain.com/path" />
<meta property="og:site_name" content="Brand" />
<meta property="og:image" content="https://domain.com/og-image.jpg" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />

<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="Page Title" />
<meta name="twitter:description" content="Engaging summary of page content." />
<meta name="twitter:image" content="https://domain.com/og-image.jpg" />
```

---

## 5. The Evidence Ledger Protocol & Schema `[STANDARD]`

When conducting an audit, every finding must be recorded in an **Evidence Ledger** to ensure audit reproducibility, eliminate hallucinations, and provide deterministic proof.

### Schema Fields:
* **`id`**: Unique finding identifier (e.g. `TECH-CANONICAL-001`, `CRAWL-ROBOTS-002`, `GEO-HEADINGS-003`).
* **`claim`**: Concise factual claim (e.g., "Canonical tag is missing or non-matching").
* **`evidence`**:
  - `source`: DOM element, HTTP response header, robots.txt directive, or Schema.org node.
  - `selector_or_directive`: Concrete selector (e.g., `link[rel='canonical']`, `HTTP Status: 200`, `User-agent: GPTBot`).
  - `observed_value`: Raw value extracted during inspection, or `null` / `not found`.
* **`status`**:
  - `PASS`: Requirement is fully satisfied.
  - `FAIL`: Requirement is violated with observed counter-evidence.
  - `UNKNOWN`: Signal cannot be observed from available inputs (e.g., CWV field data without CrUX API access, server logs without server credentials, backlink profiles without third-party crawler index).
* **`tier`**: Epistemic tier from Tier A (Official Protocol Standard) to Tier F (Working Hypothesis).
* **`confidence`**: `HIGH` (deterministic DOM/HTTP evidence), `MEDIUM` (heuristic extraction), or `LOW` (indirect inference).
* **`impact`**: `P0` (Indexation blocker / crawler leak), `P1` (Citation deficit / architecture gap), or `P2` (Hygiene).
* **`remediation`**: Exact code snippet or configuration change to resolve the issue.
* **`verification_method`**: Concrete inspection command or tool (e.g., `curl -ILs https://...`, Schema Markup Validator).

### Observation Coverage & Scoring Invariant:
$$\text{Observation Coverage} = \frac{N_{\text{PASS}} + N_{\text{FAIL}}}{N_{\text{Total Criteria}}} \times 100\%$$

> [!IMPORTANT]
> **The "Unknown $\ne$ Failure" Invariant:**
> Unobserved criteria (`status: UNKNOWN`) must **NEVER** reduce the Observable Technical SEO Score.
> Audit reports must always disclose:
> - **Observable Technical SEO Score (0–100):** Calculated strictly over evaluated signals ($N_{\text{PASS}} / (N_{\text{PASS}} + N_{\text{FAIL}})$).
> - **Observation Coverage (%):** Percentage of total criteria actually observable in the audit environment.
> - **GEO Readiness Index (0–100):** Qualitative heuristic model with MEDIUM confidence.
