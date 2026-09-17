## Technical SEO Score: 92/100
        ## GEO Score: 85/100
        > Methodology Notice: LLM Heuristic Evaluation.
        - Observation Coverage: 70% (14 observable signals checked; real-user field data UNKNOWN).

        ### Evidence Ledger
        | Finding ID | Target / Selector | Observed Evidence | Status | Epistemic Tier | Confidence | Impact | Remediation |
        |---|---|---|:---:|:---:|:---:|:---:|---|
        | `TECH-CANONICAL-001` | `link[rel='canonical']` | `https://example.com` | PASS | Tier A (RFC 6596) | HIGH | — | None. |
        | `TECH-ROBOTS-002` | `/robots.txt` | Disallow: /api/ verified | PASS | Tier A (RFC 9309) | HIGH | — | None. |
        | `PERF-CRUX-FIELD-003` | Real-User CrUX Field Data | Unobserved in static HTML | UNKNOWN | Tier C (CrUX Data) | LOW | P2 | Inspect field telemetry via Search Console. |
        | `SYS-LOG-CRAWL-004` | Server Access Logs | Unobserved without server log access | UNKNOWN | Tier A (HTTP Logs) | LOW | P2 | Analyze crawler status codes from Nginx logs. |

        Scoring Invariant Note: Under our "Unknown != Failure" rule, unobserved criteria marked UNKNOWN do not penalize or reduce the Observable Technical SEO Score.