# Technical SEO Checklist & Standards

This reference details the core technical foundation required for modern search indexation and crawl optimization.

## 1. Crawlability & Indexability
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

## 2. On-Page Semantic Structure
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

## 3. Core Web Vitals (CWV) Standards

| Metric | Target (Good) | Needs Improvement | Poor | Primary Root Causes |
|---|:---:|:---:|:---:|---|
| **LCP** (Largest Contentful Paint) | $\le 2.5\text{ s}$ | $2.5\text{ s} - 4.0\text{ s}$ | $> 4.0\text{ s}$ | Unoptimized hero images, slow TTFB, client-side JS blocking |
| **INP** (Interaction to Next Paint) | $\le 200\text{ ms}$ | $200\text{ ms} - 500\text{ ms}$ | $> 500\text{ ms}$ | Heavy main-thread JavaScript execution, un-debounced inputs |
| **CLS** (Cumulative Layout Shift) | $\le 0.1$ | $0.1 - 0.25$ | $> 0.25$ | Images without dimensions, dynamically injected ads/banners |

---

## 4. Social Metadata (Open Graph & Twitter)
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
