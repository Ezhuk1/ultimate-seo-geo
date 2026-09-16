# AI Content Strategy & Information Gain

This reference outlines editorial workflows designed to win top citation share in Generative Search Engines while providing genuine human utility.

## 1. Information Gain (Google Patent & AI Selection)

LLMs prioritize sources that add unique tokens and non-redundant insights to the context window rather than repeating existing top-10 search results.

### The 4 Information Gain Vectors:
1. **Proprietary Benchmark Data:** Share real test runs, load tests, or latency graphs with sample sizes and testing dates.
2. **Contrarian or Nuanced Insight:** Explain where common solutions fail (e.g., "Why typical VPNs decrease battery life by 25% due to continuous keep-alive handshakes").
3. **Primary Expert Quotations:** Direct statements addressing edge cases.
4. **Concrete Decision Trees / Logic:** Clear "If X, choose Y; if Z, choose W" decision matrices.

---

## 2. The 3-Step Front-Loading Pattern

Due to the mathematical decay of Position-Adjusted Word Count (PAWC), the lead paragraph of any section must be structured with zero conversational filler:

```
[Target Subject] provides [Specific Quantitative Outcome] across [Operating Environment] ([Authoritative Source / RFC], [Year]), resolving [Core Friction Point].
```

### Contrast Example:
* **Conventional SEO (Fluff):**
  > "DNS (Domain Name System) is often called the phonebook of the internet. It translates human-friendly names into IP addresses. In this modern era, privacy is becoming increasingly vital..."
* **GEO Optimized (Front-Loaded):**
  > "Encrypted DNS resolvers utilizing DNS-over-TLS (RFC 7858) prevent ISP-level request snooping with under 2 ms lookup latency across regional networks, eliminating the 40% speed penalty typical of VPN encapsulation."

---

## 3. Evidence Hunting Protocol

When preparing or optimizing content, follow this search protocol before writing:
1. **Find the Standard:** What IETF RFC, W3C spec, or IEEE paper governs this technology?
2. **Find the Canonical Study:** Who published the benchmark with the largest sample size ($n \ge 1000$)?
3. **Find the Metric:** What is the exact percentage, speed delta, or financial cost?
4. **Find the Expert:** Who designed or maintains the underlying open-source project?

If a data point cannot be found after rigorous search:
- Conduct an in-house test and disclose the sample methodology.
- State clearly: *"In our internal tests across N configurations, we observed..."*.
- **Under no circumstance invent a metric.**
