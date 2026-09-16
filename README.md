# 🚀 Ultimate SEO & GEO All-In-One (`ultimate-seo-geo`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Skill Standard: AgentSkills](https://img.shields.io/badge/AgentSkills-1.0-emerald.svg)](SKILL.md)
[![Language](https://img.shields.io/badge/Language-English%20%7C%20Русский-purple.svg)](#language--язык)

> **The definitive, production-grade SEO and Generative Engine Optimization (GEO/AEO) system for AI agents.**  
> Audits technical SEO, maximizes AI citation probability (ChatGPT Search, Perplexity AI, Claude, Gemini, Google AI Overviews), builds unified Schema.org JSON-LD graphs, configures leak-safe AI crawler protocols (`robots.txt` & `llms.txt`), and produces evidence-driven content plans.

---

### Language / Язык
* 🇬🇧 **English** (You are here)
* 🇷🇺 **[Русская версия (Russian Version)](README.ru.md)**

---

## 💡 Why This Skill Exists

Traditional SEO optimizes for Google's **PageRank** and blue links.  
**Generative AI Search (GEO / AEO) operates on completely different principles:**

1. **LLMs do not use PageRank to formulate answers.** They extract the most authoritative, structurally dense, and verifiable sentences in the retrieved context window.
2. **The Princeton GEO Paper (KDD 2024)** proved that weaker domains (Rank-5 to Rank-10) gained **+115% in generative AI visibility** simply by incorporating high-density evidence, quotations, and verified metrics.
3. **Traditional keyword stuffing actively hurts** (causing a **−8% penalty** in AI citation likelihood).
4. **Position Matters Exponentially:** Under the **PAWC** (Position-Adjusted Word Count) metric:
   $$\text{PAWC}(c, q) = \sum_{s \in S_c} \frac{|s|}{L_r} \cdot e^{-\alpha \cdot \frac{\text{pos}(s)}{N_r}}$$
   Because sentence extraction weight decays exponentially ($\sim 2.7\times$ under baseline $\alpha = 1.0$, and up to $5\times$ in steeper regimes), front-loading answers in the first 150 words serves as a proven editorial heuristic to ensure lead facts populate the opening sentences ($\text{pos}(s)=0$) of synthesized AI answers.

> **Methodology Note:** The 0–100 scores provided in audit mode represent **expert qualitative heuristic evaluations** based on the Princeton KDD 2024 rubrics. For deterministic Core Web Vitals and network measurements, pair this audit with automated tools (`lighthouse-cli`, `curl -I`).

---

## ⚡ The 5 Operating Modes

| Mode | Trigger Phrases | Key Deliverables |
|---|---|---|
| **1. `audit`** | `audit site`, `check SEO`, `calculate GEO score`, `why did traffic drop` | Dual qualitative scorecard: Technical SEO Score (0–100) + GEO Score (0–100) with prioritized P0/P1/P2 remediation steps. |
| **2. `optimize`** | `rewrite for AI`, `make ChatGPT cite this`, `front-load answer`, `improve PAWC` | Converts marketing fluff into high-PAWC, evidence-dense passages using the Princeton KDD 2024 rewrite patterns. |
| **3. `schema`** | `generate JSON-LD`, `add schema`, `rich snippets`, `FAQ schema`, `HowTo markup` | Generates a unified, validated `@graph` Schema.org JSON-LD script connecting Organization, WebSite, WebPage, Service/Product, FAQ, and HowTo (optimized for LLM answer extraction). |
| **4. `ai-files`** | `setup llms.txt`, `fix robots.txt for AI`, `allow GPTBot`, `AI bot access` | Generates leak-safe `robots.txt` explicitly permitting AI search bots while protecting private routes + structured `llms.txt` manifest (community proposal). |
| **5. `strategy`** | `AI content plan`, `topical authority map`, `keyword research`, `target AI queries` | Creates editorial clusters designed to capture long-tail conversational prompts in Perplexity and ChatGPT. |

---

## 🛡️ Security: Leak-Safe `robots.txt` Blueprint

Per **RFC 9309**, specific User-Agent blocks override the generic `*` group. If an AI group has `Allow: /` without explicit disallows, private paths are unintentionally exposed to AI bots. `ultimate-seo-geo` enforces the leak-safe pattern:

```txt
# Standard Crawlers
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

# Explicit AI Crawlers (With Inherited Private Disallows)
User-agent: GPTBot
User-agent: ChatGPT-User
User-agent: OAI-SearchBot
User-agent: ClaudeBot
User-agent: PerplexityBot
User-agent: meta-externalagent
User-agent: meta-externalfetcher
User-agent: cohere-ai
# Note: Google-Extended is an opt-out control token for Gemini/Vertex training, not an HTTP crawler.
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

Sitemap: https://[YOUR_DOMAIN]/sitemap.xml
```

---

## 📊 Scientific Foundation & Evidence Hierarchy

Empirical ranking of techniques by AI citation lift (Princeton / Georgia Tech KDD 2024):

```
┌──────────────────────────────────────────────────────────────┐
│  TECHNIQUE                          CITATION LIFT (PAWC)     │
├──────────────────────────────────────────────────────────────┤
│  1. Direct Expert Quotation (≥2)    +41%  ██████████████████ │
│  2. Specific Statistics Addition    +30%  █████████████      │
│  3. Primary Source Citation         +28%  ████████████       │
│  4. Fluency & Direct Answers        +28%  ████████████       │
│  5. Technical Entity Precision      +18%  ████████           │
│  6. Easy-to-Understand Structure   +14%  ██████             │
│  7. Authoritative Tone              +10%  ████               │
│  8. Unique Vocabulary                +6%  ██                 │
│  9. Keyword Stuffing                -8%   ▼ PENALIZED        │
└──────────────────────────────────────────────────────────────┘
```

> **The Golden Rule:** **Fluency + Statistics** produces a combined lift exceeding **+35%**, outperforming any single tactic while maintaining 100% human readability.

### 🔑 The 3 Modern GEO Principles (2025–2026 Research)

1. **Brand Mentions > Backlinks:** A study of 75,000 brands (Ahrefs, Dec 2025) proved that unlinked brand mentions on **YouTube (~0.737 correlation)**, **Reddit**, and **Wikipedia** correlate **3× more strongly** with AI citations than traditional PageRank or Domain Rating.
2. **Passage-Level Citability (134–167 Words):** AI RAG architectures extract discrete chunks. Self-contained answer blocks of 134–167 words with **low pronoun density (< 2%)** eliminate contextual ambiguity and maximize verbatim extraction probability.
3. **Platform Divergence:** Only **11% of domains** are cited concurrently by both ChatGPT Search and Google AI Overviews for identical queries, requiring engine-specific tuning (Reddit/freshness for Perplexity; YouTube/tables for AI Overviews; Wikipedia/entities for ChatGPT).

---

## 🛠️ Installation & Setup

### Option A: Install in Google Antigravity (Global)
```bash
# Windows PowerShell
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git "$env:USERPROFILE\.gemini\config\skills\ultimate-seo-geo"

# macOS / Linux
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git ~/.gemini/config/skills/ultimate-seo-geo
```

### Option B: Project-Level Installation (.agents/skills)
```bash
mkdir -p .agents/skills
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git .agents/skills/ultimate-seo-geo
```

---

## 📁 Repository Structure

```
ultimate-seo-geo/
├── SKILL.md                          # Master agent skill definition & mode routing
├── README.md                         # English documentation (this file)
├── README.ru.md                      # Полная русскоязычная документация
├── LICENSE                           # MIT License
├── .gitignore                        # Git ignore rules
├── references/
│   ├── geo-framework.md              # Princeton KDD 2024, rigorous PAWC math & engine matrix
│   ├── technical-seo-checklist.md    # Crawlability, Core Web Vitals, metadata, canonicals
│   ├── schema-templates.md           # Unified @graph JSON-LD master templates (WebPage, Service, FAQ, HowTo)
│   ├── ai-crawler-spec.md            # RFC 9309 leak prevention & llms.txt proposal
│   └── content-strategy-ai.md        # Information Gain, front-loading, evidence hunting
└── evals/
    └── evals.json                    # Heuristic & structured test cases with negative safety checks
```

---

## 🛡️ License

Released under the [MIT License](LICENSE). Free for open-source, commercial, and enterprise applications.
