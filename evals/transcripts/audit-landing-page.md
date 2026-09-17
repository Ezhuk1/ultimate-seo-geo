## Technical SEO Score: 88/100
        ## GEO Score: 82/100
        > Methodology Notice: This is an LLM Heuristic Evaluation based on current generative search retrieval models.
        - Observation Coverage: 80% (evaluated 16 observable signals; 4 field metrics UNKNOWN).

        ### Evidence Ledger
        | Finding ID | Target / Selector | Observed Evidence | Status | Epistemic Tier | Confidence | Impact | Remediation |
        |---|---|---|:---:|:---:|:---:|:---:|---|
        | `TECH-CANONICAL-001` | `link[rel='canonical']` | `https://example.com` | PASS | Tier A (RFC 6596) | HIGH | — | None. |
        | `TECH-ROBOTS-002` | `/robots.txt` AI blocks | Crawlers allowed, private disallows set | PASS | Tier A (RFC 9309) | HIGH | — | None. |
        | `TECH-CWV-FIELD-003` | CrUX API / Field Telemetry | Unobserved (no CrUX API key) | UNKNOWN | Tier C (CrUX Data) | LOW | P2 | Connect PageSpeed API for field metrics. |
        | `GEO-DEFINITION-004` | Lead section first 50 words | Definition syntax present | PASS | Tier E (Heuristic) | MEDIUM | — | None. |

        ### AI Infrastructure & Crawlability
        - robots.txt verified with RFC 9309 compliance.
        - llms.txt provides clean markdown documentation.

        ### Evidence Density
        - 8 verified metrics found with primary RFC citations.

        ### Structure & Position
        - First 150 words contain direct answer syntax and definition.

        ### Authority & E-E-A-T
        - Author Jane Doe linked with verified sameAs profiles.

        ### Prioritized Action Items
        - P0: Ensure /api/ routes are disallowed for all AI user agents.
        - P1: Add sameAs ORCID identifiers to technical authors.
        - P2: Structure procedural setup steps into HowTo schema.