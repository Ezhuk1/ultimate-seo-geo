# 🚀 Ultimate SEO & GEO All-In-One (`ultimate-seo-geo`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Skill Standard: AgentSkills](https://img.shields.io/badge/AgentSkills-1.0-emerald.svg)](SKILL.md)
[![Language](https://img.shields.io/badge/Language-English%20%7C%20Русский-purple.svg)](#language--язык)

> **The definitive, production-grade SEO and Generative Engine Optimization (GEO/AEO) system for AI agents.**  
> Audits technical SEO, maximizes AI citation probability (ChatGPT Search, Perplexity AI, Claude, Gemini, Google AI Overviews), builds unified Schema.org JSON-LD graphs, configures AI crawler protocols (`robots.txt` & `llms.txt`), and produces evidence-driven content plans.

---

### Language / Язык
* 🇬🇧 **English** (You are here)
* 🇷🇺 **[Русская версия (Russian Version)](README.ru.md)**

---

## 💡 Why This Skill Exists

Traditional SEO optimizes for Google's **PageRank** and blue links.  
**Generative AI Search (GEO / AEO) operates on completely different principles:**

1. **LLMs do not use PageRank to formulate answers.** They extract the most authoritative, structurally dense, and verifiable sentences in the retrieved context window.
2. **The Princeton GEO Paper (KDD 2024)** proved that weaker domains (Rank-5 to Rank-10) gained **+115% in generative AI visibility** simply by incorporating high-density evidence and structured quotations.
3. **Traditional keyword stuffing actively hurts** (causing a **−8% penalty** in AI citation likelihood).
4. **Position Matters Exponentially:** Under the **PAWC** (Position-Adjusted Word Count) metric, the first 150 words of an article carry **~5× more extraction weight** than trailing paragraphs.

`ultimate-seo-geo` combines cutting-edge AI citation science with rigorous technical on-page SEO into a single, cohesive workflow.

---

## ⚡ The 5 Operating Modes

| Mode | Trigger Phrases | Key Deliverables |
|---|---|---|
| **1. `audit`** | `audit site`, `check SEO`, `calculate GEO score`, `why did traffic drop` | Parallel scorecard: Technical SEO Score (0–100) + GEO Score (0–100) with prioritized P0/P1/P2 remediation steps. |
| **2. `optimize`** | `rewrite for AI`, `make ChatGPT cite this`, `front-load answer`, `improve PAWC` | Converts marketing fluff into high-PAWC, evidence-dense passages using the Princeton + AutoGEO rewrite patterns. |
| **3. `schema`** | `generate JSON-LD`, `add schema`, `rich snippets`, `FAQ schema`, `HowTo markup` | Generates a unified, validated `@graph` Schema.org JSON-LD script connecting Organization, WebSite, Service/Product, FAQ, and HowTo. |
| **4. `ai-files`** | `setup llms.txt`, `fix robots.txt for AI`, `allow GPTBot`, `AI bot access` | Generates clean `robots.txt` explicitly permitting AI search bots + structured `llms.txt` manifest at site root. |
| **5. `strategy`** | `AI content plan`, `topical authority map`, `keyword research`, `target AI queries` | Creates editorial clusters designed to capture long-tail conversational prompts in Perplexity and ChatGPT. |

---

## 📊 Scientific Foundation & Evidence Hierarchy

Empirical ranking of techniques by AI citation lift (Princeton / Georgia Tech KDD 2024):

```
┌──────────────────────────────────────────────────────────────┐
│  TECHNIQUE                          CITATION LIFT (PAWC)     │
├──────────────────────────────────────────────────────────────┤
│  1. Direct Expert Quotation         +41%  ██████████████████ │
│  2. Specific Statistics Addition    +30%  █████████████      │
│  3. Primary Source Citation         +28%  ████████████       │
│  4. Fluency & Direct Answers        +28%  ████████████       │
│  5. Technical Entity Precision      +18%  ████████           │
│  6. Easy-to-Understand Structure   +14%  ██████             │
│  7. Authoritative Tone              +10%  ████               │
│  8. Keyword Stuffing                -8%   ▼ PENALIZED        │
└──────────────────────────────────────────────────────────────┘
```

> **The Golden Rule:** **Fluency + Statistics** produces a combined lift exceeding **+35%**, outperforming any single tactic while maintaining 100% human readability.

---

## 🛠️ Installation & Setup

### Option A: Install in Google Antigravity (Global)
Clone or copy the directory directly into your global skills config:

```bash
# Windows PowerShell
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git "$env:USERPROFILE\.gemini\config\skills\ultimate-seo-geo"

# macOS / Linux
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git ~/.gemini/config/skills/ultimate-seo-geo
```

### Option B: Project-Level Installation (.agents/skills)
If you want the skill committed directly into your repository:

```bash
mkdir -p .agents/skills
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git .agents/skills/ultimate-seo-geo
```

### Option C: Claude Code / Cursor / Codex
Because `ultimate-seo-geo` follows the universal `SKILL.md` specification, simply copy the directory into your local agent skills folder:

```bash
# Claude Code
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git ~/.claude/skills/ultimate-seo-geo

# Cursor
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git ~/.cursor/skills/ultimate-seo-geo
```

---

## 🎯 Example Prompts

### 1. Running a Complete Audit
```text
Please run a full SEO and GEO audit on our landing page https://bezmezhau.com and give us a prioritized action plan.
```

### 2. Rewriting Content for High PAWC
```text
Rewrite the hero section and value proposition of my SaaS page to maximize citation in Perplexity AI and ChatGPT Search. Front-load the core answer in the first 150 words.
```

### 3. Generating Unified Schema.org JSON-LD
```text
Generate a unified Schema.org JSON-LD graph for our website with Organization, Service, FAQ, and HowTo step-by-step instructions. Link to RFC 7858 as the technical standard.
```

### 4. Deploying AI Infrastructure Files
```text
Generate a robots.txt file that allows GPTBot, ClaudeBot, and PerplexityBot, and construct a complete llms.txt file for our root domain.
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
│   ├── geo-framework.md              # Princeton KDD 2024, AutoGEO, PAWC formulas & engine matrix
│   ├── technical-seo-checklist.md    # Crawlability, Core Web Vitals, metadata, canonicals
│   ├── schema-templates.md           # Production-ready unified @graph JSON-LD templates
│   ├── ai-crawler-spec.md            # AI User-Agent taxonomy & llms.txt standard
│   └── content-strategy-ai.md        # Information Gain, front-loading, evidence hunting
└── evals/
    └── evals.json                    # Deterministic test cases and evaluation assertions
```

---

## 🛡️ License

Released under the [MIT License](LICENSE). Free for open-source, commercial, and enterprise applications.
