# GEO Framework & Scientific Foundations

This reference document synthesizes foundational research on Generative Engine Optimization (GEO) and Answer Engine Optimization (AEO) for engineering production web content.

## 1. The Core Scientific Baseline

### A. Princeton / Georgia Tech Research (KDD 2024, arXiv:2311.09735)
* **Title:** *GEO: Generative Engine Optimization*
* **Core Insight:** LLM response generation does not rely on PageRank or traditional backlink volume when assembling answers. Instead, it measures semantic relevance, extractability, and authoritative weight.
* **The PAWC Metric (Position-Adjusted Word Count):**
  $$\text{Imp}_{\text{PAWC}}(c, r) = \frac{\sum |s| \cdot e^{-\text{pos}/\text{total}}}{\text{total\_words}}$$
  Because of the exponential decay curve, information placed in the first 10–15% of an article carries up to **5× greater extraction probability** by LLMs than information placed midway or near the conclusion.

### B. Empirical Method Ranking by Citation Lift
Experiments measuring visibility improvements across generative search engines:

| Rank | Technique | Visibility / PAWC Lift | Implementation Rule |
|:---:|---|:---:|---|
| **1** | **Quotation Addition** | **+41%** | Quote real, named industry experts with institutional affiliation. |
| **2** | **Statistics Addition** | **+30%** | Replace qualitative adjectives ("fast", "cheap") with verified numbers & units. |
| **3** | **Cite Sources** | **+28%** | Link directly to primary RFCs, whitepapers, benchmarks, or peer-reviewed data. |
| **4** | **Fluency Optimization** | **+28%** | Concise, high-readability sentences (Flesch-Kincaid grade 8–10). |
| **5** | **Technical Terminology** | **+18%** | Accurate technical entities and domain taxonomies. |
| **6** | **Easy-to-Understand** | **+14%** | Clear analogies and structured modular paragraphs (2–4 sentences). |
| **7** | **Authoritative Tone** | **+10%** | Direct, active voice without apologetic or hesitant phrasing. |
| **8** | **Unique Vocabulary** | **+6%** | Distinctive, non-generic naming for proprietary frameworks. |
| **9** | **Keyword Stuffing** | **−8% (Penalty)** | Repetitive keyword placement is penalized by generative models. |

**The Compound Champion:** **Fluency + Statistics** produces $\ge +35\%$ lift, beating every single isolated approach.

---

## 2. Democratization Effect (Punching Above Weight)

Table 2 of the Princeton GEO paper demonstrated a striking asymmetry:
* **Rank-1 Google sites** actually *lost* ~30% relative share in generative summaries when competing against evidence-rich lower-ranked sites.
* **Rank-5 to Rank-10 sites** gained **+115% visibility** when they introduced structured evidence, quotations, and explicit citations.
* **Takeaway:** Even if your domain lacks millions of high-DA backlinks, you can win top-tier AI citations by out-structuring and out-evidencing incumbents.

---

## 3. Generative Engine Divergence Matrix

Generative search engines do not share the same retrieval corpus or weighting:

| Engine | Primary Retrieval Bias | Key Citation Factors | Optimization Priority |
|---|---|---|---|
| **ChatGPT Search** | Wikipedia, major media, official docs | Entity verification, authoritative definitions, neutral tone | Schema `Organization`, clear definitions, Wikipedia cross-reference |
| **Perplexity AI** | Real-time web index, recent articles, Reddit | **Freshness (last 60–90 days)**, primary news/blogs, clear headers | Explicit `<time>` tags, `dateModified`, weekly/monthly updates |
| **Google AI Overviews** | Google index top 10, featured snippets | Semantic header hierarchy, tables, FAQ schema, Core Web Vitals | Strict H1→H2→H3, HTML `<table>`, JSON-LD `FAQPage` |
| **Claude** | Primary academic sources, official docs | Deep reasoning, nuanced tradeoffs, methodology transparency | Disclosing technical limitations, citing RFCs/papers |
| **Gemini** | Google Knowledge Graph, YouTube, forums | Entity recognition, structured step-by-step solutions | YouTube video schema, `HowTo` schema, Knowledge Graph reconciliation |

---

## 4. The GEO Signal Stack (Scoring Rubric)

### Pillar 1: Evidence Density (35% Weight)
- [ ] $\ge 5$ numbers with units per article/page.
- [ ] $\ge 1$ external citation per 500 words to primary authority.
- [ ] $\ge 2$ direct quotes from verified experts.
- [ ] $\ge 3$ named entities (real people with titles, verified organizations).
- [ ] $\ge 1$ proprietary benchmark, telemetry metric, or first-party test result.

### Pillar 2: Structure & Positioning (25% Weight)
- [ ] Direct answer provided within the first 150 words.
- [ ] TL;DR / Key Takeaways callout box near the top.
- [ ] Comparative data presented in clean markdown or HTML tables.
- [ ] Procedural workflows presented in numbered ordered lists.
- [ ] Paragraph lengths strictly capped at 2–4 sentences.

### Pillar 3: Authority & E-E-A-T (25% Weight)
- [ ] Author byline with real name, photo, title, and bio ($\ge 30$ words).
- [ ] `author.sameAs` in JSON-LD linking to LinkedIn, GitHub, or academic profile.
- [ ] Machine-readable `dateModified` timestamp updated within the last 60 days.
- [ ] Methodology and sample criteria explicitly stated.
- [ ] Known limitations and technical boundaries transparently acknowledged.

### Pillar 4: AI Infrastructure & Crawlability (15% Weight)
- [ ] Full server-side rendering (SSR) of critical text and data.
- [ ] `robots.txt` explicitly allows `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`.
- [ ] `llms.txt` deployed at domain root following the standardized specification.
- [ ] Schema.org JSON-LD graph validates without errors in Google Rich Results Test.
