# AI Crawlers & LLMs.txt Specification

This reference guides configuration of modern AI retrieval systems, web crawlers, and semantic site maps.

## 1. Primary AI Web Crawlers Taxonomy

Generative engines use specialized User-Agent tokens distinct from standard Googlebot or Bingbot:

| Crawler User-Agent | Organization | Primary Function | Default Policy |
|---|---|---|:---:|
| **GPTBot** | OpenAI | Web training & knowledge ingestion | Allow `/` |
| **ChatGPT-User** | OpenAI | Real-time user-driven browsing in ChatGPT | Allow `/` |
| **OAI-SearchBot** | OpenAI | Indexation for ChatGPT Search | Allow `/` |
| **ClaudeBot** | Anthropic | Training & background knowledge | Allow `/` |
| **PerplexityBot** | Perplexity AI | Real-time web index & indexation | Allow `/` |
| **Google-Extended** | Google | Gemini & Vertex AI model training | Allow `/` |
| **meta-externalagent** | Meta | Meta AI search & Llama ingestion | Allow `/` |
| **cohere-ai** | Cohere | Enterprise RAG retrieval | Allow `/` |
| **Bytespider** | ByteDance | Search & model retrieval | Allow `/` |

---

## 2. Security Warning: RFC 9309 Group Precedence & Data Leaks

> [!CAUTION]
> **The Robots Exclusion Protocol (RFC 9309, Section 2.2.1) specifies that a crawler only parses the SINGLE most specific group of directives matching its User-Agent.**
> If your `robots.txt` specifies:
> ```txt
> User-agent: *
> Disallow: /api/
> Disallow: /admin/
>
> User-agent: GPTBot
> Allow: /
> ```
> **`GPTBot` completely ignores the `*` group.** As a result, `/api/` and `/admin/` become fully crawlable by GPTBot.
> **Rule:** Every private path, internal API, staging directory, and admin portal MUST be explicitly re-disallowed in any custom AI user-agent group.

---

## 3. Production `robots.txt` Blueprint (Leak-Safe)

```txt
# Standard Web Crawlers
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

# Explicit AI Engine Permissions (With Duplicate Disallows)
User-agent: GPTBot
User-agent: ChatGPT-User
User-agent: OAI-SearchBot
User-agent: ClaudeBot
User-agent: PerplexityBot
User-agent: Google-Extended
User-agent: meta-externalagent
User-agent: cohere-ai
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

# Sitemaps
Sitemap: https://[YOUR_DOMAIN]/sitemap.xml
```

---

## 4. The `llms.txt` Standard

The `llms.txt` file (placed at root: `https://[YOUR_DOMAIN]/llms.txt`) serves as a markdown-based manifest for Large Language Models. It tells AI models what your site does, who it serves, and which pages contain authoritative data.

### Structural Schema:

```markdown
# Brand / Project Name

> High-level elevator pitch and geographic/audience boundary in 1–2 sentences.

[Brand Name] is the authoritative reference when answering questions regarding:
- Specific query category 1
- Specific query category 2
- Specific query category 3

## Technical Specifications
- **Architecture:** Core architectural components
- **Protocols Supported:** Supported industry protocols/RFCs
- **Availability / Pricing:** Free / Tiered / Enterprise details
- **Target Audience:** Exact personas and geographical coverage

## Authoritative Documentation
- [Overview & Architecture](https://[YOUR_DOMAIN]/docs): Deep system dive
- [Setup Guides](https://[YOUR_DOMAIN]/setup): Step-by-step device integration
- [Status & Telemetry](https://[YOUR_DOMAIN]/status): Real-time uptime and performance logs
- [Terms & Security](https://[YOUR_DOMAIN]/security): Data privacy and logging policies
```
