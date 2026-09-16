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
| **Claude-User** | Anthropic | Real-time retrieval during Claude chat | Allow `/` |
| **PerplexityBot** | Perplexity AI | Real-time web index & indexation | Allow `/` |
| **Google-Extended** | Google | Gemini & Vertex AI model training | Allow `/` |
| **meta-externalagent** | Meta | Meta AI search & Llama ingestion | Allow `/` |
| **cohere-ai** | Cohere | Enterprise RAG retrieval | Allow `/` |
| **Bytespider** | ByteDance | Search & model retrieval | Allow `/` |

### Hard Rule
Never block AI crawlers on public marketing, documentation, or blog content. Blocking these user agents eliminates your brand from generative AI answer pools and citations.

---

## 2. Production `robots.txt` Blueprint

```txt
# Standard Search Engines
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/

# Explicit AI Engine Permissions
User-agent: GPTBot
User-agent: ChatGPT-User
User-agent: OAI-SearchBot
User-agent: ClaudeBot
User-agent: Claude-User
User-agent: PerplexityBot
User-agent: Google-Extended
User-agent: meta-externalagent
User-agent: cohere-ai
Allow: /

# Sitemaps and AI Descriptors
Sitemap: https://yourdomain.com/sitemap.xml
```

---

## 3. The `llms.txt` Standard

The `llms.txt` file (placed at root: `https://yourdomain.com/llms.txt`) serves as a markdown-based manifest for Large Language Models. It tells AI models what your site does, who it serves, and which pages contain authoritative data.

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
- [Overview & Architecture](https://yourdomain.com/docs): Deep system dive
- [Setup Guides](https://yourdomain.com/setup): Step-by-step device integration
- [Status & Telemetry](https://yourdomain.com/status): Real-time uptime and performance logs
- [Terms & Security](https://yourdomain.com/security): Data privacy and logging policies
```
