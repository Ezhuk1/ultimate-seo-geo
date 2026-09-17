# 🚀 Ultimate SEO & GEO All-In-One (`ultimate-seo-geo`)

[![Version: 3.0.0](https://img.shields.io/badge/Version-3.0.0-blue.svg)](evals/CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B%20%7C%20Zero--Dep-success.svg)](engine/)
[![Skill Standard: AgentSkills](https://img.shields.io/badge/AgentSkills-1.0-emerald.svg)](SKILL.md)
[![Language](https://img.shields.io/badge/Language-English%20%7C%20Русский-purple.svg)](#language--язык)

> **The definitive, production-grade SEO and Generative Engine Optimization (GEO/AEO) intelligence platform for AI agents & CI/CD pipelines.**  
> Combines an **autonomous, deterministic inspection engine** (pure Python stdlib, zero dependencies) with an **evidence-driven AI reasoning agent**. Audits technical SEO, detects client-side rendering (CSR) invisibility, maximizes generative citation probability (ChatGPT Search, Perplexity AI, Claude, Gemini, Google AI Overviews), evaluates E-E-A-T trust signals & content freshness, crawls site architecture & internal links, validates unified Schema.org `@graph` ASTs, and enforces CI/CD quality gates via OASIS SARIF v2.1.0.

---

### Language / Язык
* 🇬🇧 **English** (You are here)
* 🇷🇺 **[Русская версия (Russian Version)](README.ru.md)**

---

## 💡 Architecture: The Two-Stage Retrieval & Synthesis Model

Modern AI Search operates in **two interconnected stages**:

```
                       ┌─────────────────────────────────────────────────────────┐
                       │                       TARGET URL                        │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: CANDIDATE RETRIEVAL (Traditional Technical SEO)                                                        │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Indexability Matrix: Multi-signal verdict (HTTP 200, Canonical, Robots, Sitemap, Internal links)             │
│ • Crawlability & Site Architecture (Polite BFS Crawler, crawl depth, orphan candidate identification)          │
│ • Canonicalization (RFC 6596) & Document Outline (Single H1, semantic H2-H6 hierarchy)                         │
│ • Server-Side Rendering (SSR/SSG): Detection of empty CSR shells (div#root) blinding fast AI scrapers          │
│ • Segregated Security Hygiene Score: HTTPS, HSTS, zero mixed content, security headers (0..100)                │
│ • Duplicate Content & Similarity: 64-bit SimHash, Hamming distance, and Jaccard token clustering                │
│ ──► Result: Entry into the top candidate pool (e.g., Google Top-5 or Perplexity Retrieval Context Window)       │
└───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: GENERATIVE SYNTHESIS (Generative Engine Optimization / GEO)                                            │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • 8-Component Weighted GEO Score: Answerability (20%), Evidence Density (20%), Entity Clarity (15%),             │
│   Passage Extractability (15%), Source Attribution (10%), Schema Graph (10%), Freshness (5%), AI Access (5%)   │
│ • E-E-A-T & Trust Profile: Author bio, sameAs authority links, organization credentials, YMYL disclaimers       │
│ • Freshness & Temporal Consistency: Publication/modification alignment, sitemap date consistency, stale flags   │
│ • Knowledge Graph Grounding: Hardened Schema.org @graph with 4-tier rich result eligibility verdict             │
│ • AI Crawler Governance: Search Retrieval vs Model Training vs User Fetch bot classification                    │
│ ──► Result: Generative synthesis preferentially quotes, cites, and links your content in the final AI answer     │
└───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │         EVIDENCE LEDGER REPORT & SCORECARD              │
                       │ (Observable Score 0-100, Security 0-100, GEO Index 0-100│
                       │       OASIS SARIF v2.1.0 & Historical Score Delta)      │
                       └─────────────────────────────────────────────────────────┘
```

### Key Research Foundations:
1. **The Democratization Effect (Princeton KDD 2024, Table 2):** Within candidate retrieval pools (Google Top-5), Rank-5 results optimizing evidence density (*Cite Sources*) gained **+115.1% in generative visibility**, while Rank-1 dropped **-30.3%**, proving that superior evidence density can win synthesis over higher-ranked candidates.
2. **Exponential Citation Weight Decay (The PAWC Metric):**  
   $$\text{PAWC}(c, q) = \sum_{s \in S_c} \frac{|s|}{L_r} \cdot e^{-\alpha \cdot \frac{\text{pos}(s)}{N_r}}$$  
   Sentence citation weight decays exponentially ($\sim 2.7\times$ under $\alpha = 1.0$) across the *synthesized LLM response*. Front-loading definitions and facts maximizes placement in lead sentences ($\text{pos}(s)=0$).
3. **The "Unknown $\ne$ Failure" Invariant:** Unobservable criteria (real-user CrUX field data without API keys, internal server access logs) are recorded as `UNKNOWN` with **0 penalty**, segregated from verified defects.

---

## 🖥️ Autonomous Inspection Engine CLI (`engine/`)

The built-in deterministic inspection engine requires **zero external pip dependencies** (built strictly on Python 3.10+ standard library) and runs in **<50ms**:

```bash
# 1. Audit a live website with AI bot access simulation, Indexability Matrix & E-E-A-T
python -m engine.inspector https://example.com

# 2. Multi-page polite BFS site crawl (crawls link graph, calculates depth & orphan pages)
python -m engine.inspector https://example.com --crawl --max-pages 50 --depth 3

# 3. Pre-flight standalone Schema.org JSON-LD validator
python -m engine.inspector --validate-schema path/to/schema.json

# 4. CI/CD Quality Gate with SARIF export and exit-code thresholds
python -m engine.inspector https://example.com \
  --strict \
  --fail-on P0 \
  --fail-on-score 80 \
  --sarif code-scanning.sarif \
  --previous-audit previous.json

# 5. Output machine-readable JSON with full Evidence Ledger & Provenance SHA-256
python -m engine.inspector https://example.com --format json --output audit.json
```

### Deterministic Capabilities
- **Deterministic Indexability Matrix:** Evaluates HTTP status, canonical consistency, meta robots, X-Robots-Tag, robots.txt, sitemaps, internal links, and rendered payload into a definitive indexability verdict.
- **Site-Level Crawler & Similarity Analysis:** Polite BFS crawler with rate limits, SSRF guardrails, crawl depth tracking, orphan page candidate discovery, and 64-bit SimHash near-duplicate clustering.
- **8-Component GEO Readiness Index:** Evaluates Answerability, Evidence Density, Entity Clarity, Passage Extractability, Source Attribution, Schema Graph, Freshness, and AI Crawler Access with confidence and measured dimension tracking.
- **E-E-A-T & Trust Profile:** Evaluates author bio, verified `sameAs` entity links (Wikidata, ORCID, LinkedIn), organization credentials, transparency touchpoints (About/Contact/Editorial), YMYL detection & disclaimers, and first-hand experience markers.
- **Freshness & Temporal Consistency:** Validates publication/modification dates, sitemap `lastmod` alignment, HTTP `Last-Modified`, content hashes, date discrepancies, and flags stale content (>2 years).
- **Hardened Schema.org Validator:** Validates unified `@graph` ASTs, detects duplicate `@id` definitions, enforces required properties for high-value types (Article, Product, Org, FAQ, Breadcrumbs), and provides a 4-tier rich result eligibility verdict.
- **OASIS SARIF v2.1.0 Exporter:** Turnkey integration with GitHub Code Scanning, GitLab CI, and automated security/quality dashboards.
- **Segregated Security Hygiene Score:** Independent 0..100 dimension for HTTPS wire, HSTS headers, mixed content, and security headers.
- **Historical Monitoring & Delta Comparison:** Automatically computes score deltas, resolved issues, and introduced defects against previous audit files.

---

## ⚡ The 5 Operating Modes

When using as an AI Agent Skill (in Antigravity, Claude Code, Cursor, Codex), the skill routes requests into 5 specialized operational modes:

| Mode | Trigger Phrases | Key Deliverables |
|---|---|---|
| **1. `audit`** | `audit site`, `check SEO`, `calculate GEO score`, `why did traffic drop` | Deterministic CLI inspection, Evidence Ledger, Observable Technical Score (0–100, High Confidence), Observation Coverage %, and GEO Readiness Index (0–100, Medium Confidence) with prioritized P0/P1/P2 remediation steps. |
| **2. `optimize`** | `rewrite for AI`, `make ChatGPT cite this`, `front-load answer`, `improve PAWC` | Converts marketing fluff into high-PAWC, evidence-dense passages using Princeton KDD 2024 rewrite patterns. |
| **3. `schema`** | `generate JSON-LD`, `add schema`, `rich snippets`, `FAQ schema`, `HowTo markup` | Generates a unified, validated `@graph` Schema.org JSON-LD script connecting Organization, WebSite, WebPage, Service/Product, FAQ, and HowTo (with pre-flight verification via `--validate-schema`). |
| **4. `ai-files`** | `setup llms.txt`, `fix robots.txt for AI`, `allow GPTBot`, `AI bot access` | Generates indexation-safe `robots.txt` explicitly permitting AI search bots while protecting private routes + structured `llms.txt` manifest. |
| **5. `strategy`** | `AI content plan`, `topical authority map`, `keyword research`, `target AI queries` | Creates editorial clusters designed to capture long-tail conversational prompts in Perplexity and ChatGPT. |

*(Note: The internal `safety_check` evaluation harness enforces strict rejection of data/credential fabrication prompts).*

---

## 📚 Strict Just-In-Time (JIT) Reference Loading

To guard against context window bloat (40,000+ tokens) and prevent **"lost in the middle"** degradation during AI agent pairing, `SKILL.md` enforces **Strict JIT Reference Loading**:

| Active Mode | Document Loaded into Context | Content & Purpose |
|---|---|---|
| **`audit`** | `references/technical-seo-checklist.md` + `references/geo-framework.md` | *Note:* If CLI engine is executed, reference documents are not loaded into context at all! |
| **`optimize`** | `references/geo-framework.md` | Princeton KDD lift table, PAWC formulation, chunking heuristics |
| **`schema`** | `references/schema-templates.md` | Master `@graph` templates (WebSite, WebPage, Service, HowTo, FAQ) |
| **`ai-files`** | `references/ai-crawler-spec.md` | RFC 9309 crawler specs, leak prevention blueprints, `llms.txt` spec |
| **`strategy`** | `references/content-strategy-ai.md` | Information Gain, search intent mapping, source attribution rules |

> **Context Protection Rule:** Eager parallel loading of uninvoked reference files is strictly prohibited.

---

## 🛡️ Crawl Governance: Indexation-Safe `robots.txt` Blueprint

Per **RFC 9309**, specific User-Agent blocks override the generic `*` group. If an AI group has `Allow: /` without explicit disallows, private paths are unintentionally exposed to AI crawler indexing:

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
# Note: Google-Extended and Applebot-Extended are opt-out tokens for model training, NOT HTTP fetchers.
# They do NOT affect indexing or citation in Google AI Overviews or Siri/Spotlight.
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

### The 6-Tier Epistemic Hierarchy
Findings in the Evidence Ledger are classified by epistemic certainty:
- **Tier A:** Official Protocol Standards (RFC 9309, RFC 6596, Schema.org W3C).
- **Tier B:** Peer-Reviewed Academic Research (Princeton KDD 2024).
- **Tier C:** Large-Scale Industry Empirical Datasets (Ahrefs 75k brands, CrUX).
- **Tier D:** Reproducible Controlled Experiments (Ablation tests, A/B ranking tests).
- **Tier E:** Practitioner Engineering Heuristics (RAG chunking ~100-200 words, direct answer frontloading, coreference independence).
- **Tier F:** Working Hypotheses & Edge Observations.

---

## 🛠️ Installation & Setup

### Option A: Install in Google Antigravity (Global)
```bash
# Windows PowerShell (Antigravity 2.0 / current AGY)
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git "$env:USERPROFILE\.gemini\antigravity\skills\ultimate-seo-geo"

# macOS / Linux
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git ~/.gemini/antigravity/skills/ultimate-seo-geo
```

### Option B: Project-Level Installation (.agents/skills)
```bash
mkdir -p .agents/skills
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git .agents/skills/ultimate-seo-geo
```

---

## 🧪 Verification & Quality Benchmarks

Run the complete evaluation suite, assertion harness, mutation guards, and engine tests:
```bash
python evals/run_evals.py
```

Expected output:
```text
==================================================
 ultimate-seo-geo Test Runner & Assertion Harness
==================================================
Suite: ultimate-seo-geo-evals (v2.1.0) - 10 test cases

[OK] Schema & reference file integrity: PASS
--- 1. Canonical Fixture Evaluation ---
  [PASS] 10/10 canonical evals passed
--- 2. Negative Mutation & Anti-Regression Suite ---
  [PASS] 9/9 negative mutation guards passed
--- 3. Autonomous Inspection Engine (v2.1.0) Integration Suite ---
  [PASS] test_clean_page_inspection             -> Deterministic assertion passed
  [PASS] test_defective_page_detection          -> Deterministic assertion passed
  [PASS] test_robots_simulator_rfc9309          -> Deterministic assertion passed
  [PASS] test_unknown_signal_invariant          -> Deterministic assertion passed
  [PASS] test_csr_shell_detection               -> Deterministic assertion passed
  [PASS] test_schema_standalone_validator       -> Deterministic assertion passed

[SUCCESS] All evaluation fixtures, assertions, mutation guards, and Engine v2.1.0 tests are healthy.
```

---

## 📁 Repository Structure

```
ultimate-seo-geo/
├── SKILL.md                          # Master agent skill definition, mode routing & JIT loading rules
├── README.md                         # English documentation (this file)
├── README.ru.md                      # Полная русскоязычная документация
├── LICENSE                           # MIT License
├── .gitignore                        # Git ignore rules (with Python cache filters)
├── engine/                           # Autonomous Deterministic Inspection Engine (Python stdlib)
│   ├── inspector.py                  # CLI runner, --validate-schema & Markdown/JSON generator
│   ├── ledger.py                     # 4-Layer Evidence Ledger Protocol & SHA-256 provenance
│   ├── scoring.py                    # Multi-dimensional score engine & Invariant guards
│   └── analyzers/
│       ├── http_analyzer.py          # HTTP/HTTPS & local file payload observer
│       ├── html_analyzer.py          # HTML parser for canonical, CSR shell, meta, headings, links
│       ├── robots_simulator.py       # RFC 9309 AST parser & AI crawler simulator
│       ├── schema_analyzer.py        # Schema.org AST, @graph, broken @id & ISO date validator
│       └── content_analyzer.py       # Direct answer, chunking & coreference analyzer
├── rules/                            # Declarative rule contracts
│   ├── technical_rules.json          # Canonical, robots, CSR shell, title, meta, H1 contracts
│   ├── schema_rules.json             # Syntax, graph interconnect, broken @id, price & date contracts
│   └── geo_rules.json                # Direct answer, chunking, coreference contracts
├── references/                       # Domain manuals loaded strictly Just-In-Time
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
