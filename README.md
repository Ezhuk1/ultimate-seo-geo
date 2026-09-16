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

## 💡 Why This Skill Exists: Evidence-Driven Architecture

Modern AI Search combines **traditional retrieval** with **generative synthesis**:
1. **The Two-Stage Pipeline:** Traditional SEO (crawling, technical indexability, PageRank) determines whether your page enters the top candidate search pool (e.g. Google's top-5 to top-10 results). Once candidates are retrieved, **GEO governs synthesis**: the LLM extracts and cites facts from candidates exhibiting the highest evidence density and structural clarity.
2. **The Democratization Effect:** The Princeton GEO Paper (KDD 2024, Table 2) evaluated candidate retrieval within Google top-5 results, proving that Rank-5 Google results using the *Cite Sources* technique gained **+115.1% in generative AI visibility** (while Rank-1 sites dropped **-30.3%**), demonstrating that superior evidence density can surpass higher-ranking candidates within the synthesis pool.
3. **Position Matters Exponentially (The PAWC Metric):**  
   $$\text{PAWC}(c, q) = \sum_{s \in S_c} \frac{|s|}{L_r} \cdot e^{-\alpha \cdot \frac{\text{pos}(s)}{N_r}}$$
   Because sentence citation weight decays exponentially ($\sim 2.7\times$ under baseline $\alpha = 1.0$) across the *synthesized LLM response*, front-loading direct answers serves as an editorial RAG chunking heuristic: it maximizes the likelihood that an extracted passage contains a standalone assertion that populates opening answer sentences ($\text{pos}(s)=0$).

```
                 TARGET
                   │
                   ▼
             ┌───────────┐
             │ DISCOVERY │ (URL, HTML, Codebase)
             └─────┬─────┘
                   ↓
        ┌─────────────────────┐
        │ OBSERVABLE SIGNALS  │ (DOM selectors, HTTP status, headers, robots, schema)
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │ EVIDENCE LEDGER     │ (Finding ID, Selector, Raw Value, PASS/FAIL/UNKNOWN, Tier)
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │ 6-TIER RULE ENGINE  │ (Tier A Standards to Tier F Hypotheses)
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │ CONFIDENCE ENGINE   │ (Observable Score vs Observation Coverage %)
        └──────────┬──────────┘
                   ↓
             FINAL REPORT
```

> **The Evidence Ledger & Scoring Invariant:**
> 1. **Evidence Ledger Protocol:** Audits do not output subjective impressions. Every finding must record an exact DOM selector or HTTP header, observed value, and epistemic tier (`Tier A` through `Tier F`).
> 2. **"Unknown $\ne$ Failure":** When field data (CrUX telemetry, server logs, backlink index) is unobservable, it is marked `UNKNOWN` and does **not** penalize the score. Reports disclose:
>    - **Observable Technical Score (0–100):** Evaluated solely over verifiable signals (High Confidence).
>    - **Observation Coverage (%):** Percentage of total criteria observable from available inputs.
>    - **GEO Readiness Index (0–100):** Qualitative heuristic model (Medium Confidence).

---

## ⚡ The 5 Operating Modes

| Mode | Trigger Phrases | Key Deliverables |
|---|---|---|
| **1. `audit`** | `audit site`, `check SEO`, `calculate GEO score`, `why did traffic drop` | Evidence Ledger table, Observable Technical Score (0–100, High Confidence), Observation Coverage %, and GEO Readiness Index (0–100, Medium Confidence) with prioritized P0/P1/P2 remediation steps. |
| **2. `optimize`** | `rewrite for AI`, `make ChatGPT cite this`, `front-load answer`, `improve PAWC` | Converts marketing fluff into high-PAWC, evidence-dense passages using the Princeton KDD 2024 rewrite patterns. |
| **3. `schema`** | `generate JSON-LD`, `add schema`, `rich snippets`, `FAQ schema`, `HowTo markup` | Generates a unified, validated `@graph` Schema.org JSON-LD script connecting Organization, WebSite, WebPage, Service/Product, FAQ, and HowTo (optimized for LLM answer extraction; Note: Google completely discontinued FAQ rich results on May 7, 2026). |
| **4. `ai-files`** | `setup llms.txt`, `fix robots.txt for AI`, `allow GPTBot`, `AI bot access` | Generates indexation-safe `robots.txt` explicitly permitting AI search bots while protecting private routes + structured `llms.txt` manifest (community proposal). |
| **5. `strategy`** | `AI content plan`, `topical authority map`, `keyword research`, `target AI queries` | Creates editorial clusters designed to capture long-tail conversational prompts in Perplexity and ChatGPT. |

*(Note: In addition to the 5 user-facing modes above, the skill includes the `safety_check` internal evaluation harness to prevent hallucination).*

---

## 🛡️ Crawl Governance: Indexation-Safe `robots.txt` Blueprint

Per **RFC 9309**, specific User-Agent blocks override the generic `*` group. If an AI group has `Allow: /` without explicit disallows, private paths are unintentionally exposed to AI crawler indexing. *(Note: Per RFC 9309 §1, robots exclusion is crawl control, NOT access security; true protection requires HTTP 401/403 authentication, WAF rules, and network ACLs).* `ultimate-seo-geo` enforces the indexation-safe pattern:

```txt
# Standard Crawlers
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

# Explicit AI Crawlers (With Duplicate Disallows per RFC 9309)
User-agent: GPTBot
User-agent: ChatGPT-User
User-agent: OAI-SearchBot
User-agent: ClaudeBot
User-agent: Claude-SearchBot
User-agent: Claude-User
User-agent: PerplexityBot
User-agent: Perplexity-User
User-agent: meta-externalagent
User-agent: meta-externalfetcher
User-agent: cohere-ai
# Note: Google-Extended and Applebot-Extended are opt-out control tokens for model training, NOT HTTP fetchers.
# They do NOT affect indexing or citation in Google AI Overviews or Siri/Spotlight.
# Add "User-agent: Google-Extended" or "User-agent: Applebot-Extended" + "Disallow: /" only if opting out of AI model training.
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

Empirical ranking of techniques by AI citation lift ([Princeton / Georgia Tech KDD 2024, arXiv:2311.09735](https://arxiv.org/abs/2311.09735)):

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

> **Benchmark Scope Note `[RESEARCH]`:** These percentages reflect empirical observations from controlled benchmark environments across synthetic test queries (Aggarwal et al., 2024, Table 1), not universal guarantees for production web ranking.
>
> **Strategy Combination Lift:** In Section 5.3 of the Princeton study, combining **Fluency Optimization + Statistics Addition** outperformed the best individual strategy by **>5.5%** on the 200-query benchmark subset.

### 🔑 The 3 Modern GEO Principles (2025–2026 Research)

1. **Off-Page Brand Footprint & Candidate Retrieval `[RESEARCH]`:** In observational studies across 75,000 established brands ($DR > 40$, Ahrefs), unlinked brand mentions on conversational platforms (**YouTube ~0.737 correlation**, Reddit, Wikipedia) showed high correlation with generative engine citations, reinforcing entity grounding in Stage 2 synthesis. Traditional backlinks remain essential for Stage 1 candidate retrieval.
2. **Passage-Level Citability & Coreference Independence `[HEURISTIC]`:** Practical RAG engineering heuristic. Self-contained answer blocks (~100–200 words) with explicit entity naming rather than ambiguous pronouns eliminate reference ambiguity and maximize verbatim extraction probability.
3. **Platform Divergence & Query-Dependent Freshness `[RESEARCH]` & `[HEURISTIC]`:** Cross-engine comparative studies indicate that only **~11% of domains** are cited concurrently by both ChatGPT Search and Google AI Overviews for identical queries. Optimization requires tuning for platform biases and query volatility (volatile/pricing vs evergreen/RFC specifications).

---

## 🖥️ Autonomous Inspection Engine CLI (v2.0.0)

`ultimate-seo-geo` includes a built-in, autonomous deterministic inspection engine with **zero external dependencies** (pure Python 3.10+ standard library). It inspects targets in <500ms and compiles a cryptographically hashed Evidence Ledger:

```bash
# Audit a live website with AI bot simulation
python -m engine.inspector https://example.com

# Audit a local HTML build artifact or template
python -m engine.inspector path/to/page.html

# Output machine-readable JSON for CI/CD quality gates
python -m engine.inspector https://example.com --format json --output audit-report.json

# Test against a custom robots.txt configuration
python -m engine.inspector https://example.com --robots path/to/custom-robots.txt
```

### Deterministic Engine Capabilities
- **RFC 9309 AI Crawler Access Simulator:** Parses robots.txt AST and computes deterministic access rights for `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`, and search bots using longest-match and Allow-precedence rules.
- **Schema.org AST & Graph Analyzer:** Verifies JSON-LD syntax, validates unified `@graph` cross-references via `@id`, catches orphaned entities, and validates Google Merchant offer price formats.
- **Content & GEO Readiness Analyzer:** Quantifies direct answer frontloading in the opening block, detects conversational fluff, analyzes passage chunking distributions, and checks coreference independence.
- **Evidence Ledger Protocol:** Enforces the 4-layer pipeline (`RAW` -> `SIGNAL` -> `EVIDENCE` -> `FINDING`) with SHA-256 payload provenance.
- **Strict "Unknown != Failure" Invariant:** Unobserved signals (e.g., real-user CrUX field data when API keys are absent) are recorded with 0 penalty and segregated from verified defects.

---

## 🛠️ Installation & Setup

### Option A: Install in Google Antigravity (Global)
```bash
# Windows PowerShell (Antigravity 2.0 / current AGY)
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git "$env:USERPROFILE\.gemini\antigravity\skills\ultimate-seo-geo"

# macOS / Linux
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git ~/.gemini/antigravity/skills/ultimate-seo-geo

# (Legacy global path: ~/.gemini/config/skills/ultimate-seo-geo)
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
├── engine/                           # Autonomous Deterministic Inspection Engine (Python stdlib)
│   ├── inspector.py                  # CLI runner & Markdown/JSON report generator
│   ├── ledger.py                     # 4-Layer Evidence Ledger Protocol & SHA-256 provenance
│   ├── scoring.py                    # Multi-dimensional score engine & Invariant guards
│   └── analyzers/
│       ├── http_analyzer.py          # HTTP/HTTPS & local file payload observer
│       ├── html_analyzer.py          # HTML parser for canonical, meta, headings, links
│       ├── robots_simulator.py       # RFC 9309 AST parser & AI crawler simulator
│       ├── schema_analyzer.py        # Schema.org AST, @graph & price validator
│       └── content_analyzer.py       # Direct answer, chunking & coreference analyzer
├── rules/                            # Declarative rule contracts
│   ├── technical_rules.json          # Canonical, robots, title, meta, H1 contracts
│   ├── schema_rules.json             # Syntax, graph interconnect, price format contracts
│   └── geo_rules.json                # Direct answer, chunking, coreference contracts
├── references/
│   ├── geo-framework.md              # Princeton KDD 2024, rigorous PAWC math & engine matrix
│   ├── technical-seo-checklist.md    # Crawlability, Core Web Vitals, metadata, canonicals
│   ├── schema-templates.md           # Unified @graph JSON-LD master templates
│   ├── ai-crawler-spec.md            # RFC 9309 leak prevention & llms.txt proposal
│   └── content-strategy-ai.md        # Information Gain, front-loading, evidence hunting
└── evals/
    ├── evals.json                    # Heuristic & structured test cases with negative safety checks
    ├── run_evals.py                  # Test runner & assertion harness
    ├── test_engine.py                # Automated engine integration suite
    └── CHANGELOG.md                  # Comprehensive benchmark & engine changelog
```

---

## 🛡️ License

Released under the [MIT License](LICENSE). Free for open-source, commercial, and enterprise applications.

