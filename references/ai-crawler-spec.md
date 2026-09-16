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
| **Claude-SearchBot** | Anthropic | Real-time search indexation for Claude | Allow `/` |
| **Claude-User** | Anthropic | Real-time user-driven browsing in Claude | Allow `/` |
| **PerplexityBot** | Perplexity AI | Real-time web index & indexation | Allow `/` |
| **Perplexity-User** | Perplexity AI | Real-time user-driven query retrieval | Allow `/` |
| **meta-externalagent** | Meta | Llama model training & ingestion (case-insensitive) | Allow `/` |
| **meta-externalfetcher** | Meta | Real-time web retrieval & link previews | Allow `/` |
| **cohere-ai** | Cohere | Enterprise RAG retrieval | Allow `/` |
| **Bytespider** | ByteDance | Search & model retrieval | Conditional (Often rate-limited/blocked due to high fetch velocity) |
| *Google-Extended* | Google | *Control token* (evaluated by Googlebot for Gemini/Vertex training; does not crawl and does not affect AI Overviews) | Opt-out only (`Disallow: /`) |
| *Applebot-Extended* | Apple | *Control token* (evaluated for Apple Intelligence model training; does not crawl and does not affect Siri/Spotlight search) | Opt-out only (`Disallow: /`) |

---

## 2. Security Warning: RFC 9309 Group Precedence & Data Leaks

> [!CAUTION]
> **The Robots Exclusion Protocol (RFC 9309, Section 2.2.1) specifies that a crawler matches only the group corresponding to its product token. If a matching group exists, the crawler obeys ONLY that group and completely ignores the generic `*` group.**
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
> [!NOTE]
> Grouping multiple `User-agent:` lines into a single record is fully compliant with RFC 9309 (Section 2.2.1) and supported by all major modern search and AI crawlers.

```txt
# Standard Web Crawlers
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

# Explicit AI Engine Permissions (With Duplicate Disallows per RFC 9309)
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
# Optional: Add Bytespider if targeting ByteDance / Doubao search (omit if protecting against aggressive scrapers):
# User-agent: Bytespider
# Note: Google-Extended and Applebot-Extended are opt-out control tokens for model training, NOT HTTP fetchers.
# They do NOT affect indexing or citation in Google AI Overviews or Siri/Spotlight.
# Add "User-agent: Google-Extended" or "User-agent: Applebot-Extended" + "Disallow: /" only if opting out of AI model training.
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

## 4. The `llms.txt` Proposal (Community Emerging)

The `llms.txt` format (originated by Jeremy Howard / Answer.AI) is an emerging de-facto community proposal, not a formalized IETF or W3C standard. Placed at root (`https://[YOUR_DOMAIN]/llms.txt`), it serves as a markdown-based manifest for Large Language Models. It tells AI models what your site does, who it serves, and which pages contain authoritative data.

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
