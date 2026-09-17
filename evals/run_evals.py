#!/usr/bin/env python3
"""
ultimate-seo-geo: Evaluation Suite Runner & Assertion Harness (v3.0.0)
Validates evals.json schema integrity, reference file bindings, assertion engine rules,
Evidence Ledger formatting, UNKNOWN signal handling, negative mutation test cases,
recorded model transcripts, and Autonomous Engine v3.0.0 deterministic inspection suite.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def load_evals(evals_path: Path) -> dict:
    if not evals_path.exists():
        raise FileNotFoundError(f"evals.json not found at {evals_path}")
    with open(evals_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_schema(data: dict, repo_root: Path) -> list[str]:
    errors = []
    
    if "name" not in data or "version" not in data or "evals" not in data:
        errors.append("Root missing required keys ('name', 'version', 'evals')")
        return errors

    evals = data.get("evals", [])
    if not isinstance(evals, list) or len(evals) == 0:
        errors.append("'evals' must be a non-empty list")
        return errors

    valid_modes = {"audit", "optimize", "schema", "ai-files", "strategy", "safety_check"}
    seen_ids = set()

    for idx, item in enumerate(evals):
        eval_id = item.get("id")
        if not eval_id:
            errors.append(f"Eval index {idx} missing 'id'")
        elif eval_id in seen_ids:
            errors.append(f"Duplicate eval id: '{eval_id}'")
        else:
            seen_ids.add(eval_id)

        mode = item.get("mode")
        if mode not in valid_modes:
            errors.append(f"Eval '{eval_id}' has invalid mode: '{mode}'. Expected one of {valid_modes}")

        prompt = item.get("prompt")
        if not prompt or not isinstance(prompt, str):
            errors.append(f"Eval '{eval_id}' has missing or empty 'prompt'")

        assertions = item.get("assertions")
        if not isinstance(assertions, dict) or len(assertions) == 0:
            errors.append(f"Eval '{eval_id}' has missing or empty 'assertions'")

    # Validate reference files exist
    expected_references = [
        "references/geo-framework.md",
        "references/technical-seo-checklist.md",
        "references/schema-templates.md",
        "references/ai-crawler-spec.md",
        "references/content-strategy-ai.md",
    ]
    for rel_path in expected_references:
        full_path = repo_root / rel_path
        if not full_path.exists():
            errors.append(f"Required reference document missing: {rel_path}")

    return errors


STOPWORDS = {
    "that", "this", "with", "from", "have", "more", "also", "were", "been",
    "their", "which", "about", "into", "than", "them", "some", "what", "when",
    "your", "only", "such", "other", "these", "then", "well", "will", "over",
    "even", "most", "each", "both", "through", "after", "before", "during", "while"
}


def evaluate_assertions(eval_id: str, sample: Any, assertions: dict) -> tuple[bool, str]:
    """
    Evaluates a sample output against declared assertion criteria for a given eval_id.
    Returns (True, 'Passed') on success or (False, reason) on failure.
    """
    if eval_id == "audit-landing-page":
        if not isinstance(sample, str):
            return False, "Sample must be a string for audit-landing-page"

        for s in assertions.get("contains_sections", []):
            if s.lower() not in sample.lower():
                return False, f"Missing required section '{s}'"

        any_match = any(sec.lower() in sample.lower() for sec in assertions.get("contains_any_section", []))
        if not any_match:
            return False, f"Failed contains_any_section check from {assertions.get('contains_any_section')}"

        if assertions.get("heuristic_notice_present") and "heuristic" not in sample.lower():
            return False, "Heuristic methodology notice missing"

        if assertions.get("evidence_ledger_present"):
            ledger_indicators = ["evidence ledger", "finding id", "observed evidence", "| `tech-", "| tech-"]
            if not any(ind in sample.lower() for ind in ledger_indicators):
                return False, "Evidence Ledger table missing from audit output"

        if assertions.get("handles_unknown_unobserved_signals"):
            if "unknown" not in sample.lower():
                return False, "Audit does not handle unobserved signals with UNKNOWN status"

        if assertions.get("reports_observation_coverage"):
            cov_match = re.search(r'(?:observation\s+coverage|coverage\s+ratio|coverage):\s*\d+%', sample, re.IGNORECASE)
            if not cov_match:
                return False, "Observation Coverage percentage missing from audit output"

        if "score_ranges" in assertions:
            ranges = assertions["score_ranges"]
            if "technical_seo" in ranges:
                tech_match = re.search(r'Technical SEO Score:\s*(\d+)', sample, re.IGNORECASE)
                if not tech_match:
                    return False, "Technical SEO Score not found in output"
                tech_score = int(tech_match.group(1))
                t_min, t_max = ranges["technical_seo"]
                if not (t_min <= tech_score <= t_max):
                    return False, f"Technical SEO Score {tech_score} out of bounds [{t_min}, {t_max}]"

            if "geo" in ranges:
                geo_match = re.search(r'GEO Score:\s*(\d+)', sample, re.IGNORECASE)
                if not geo_match:
                    return False, "GEO Score not found in output"
                geo_score = int(geo_match.group(1))
                g_min, g_max = ranges["geo"]
                if not (g_min <= geo_score <= g_max):
                    return False, f"GEO Score {geo_score} out of bounds [{g_min}, {g_max}]"

    elif eval_id == "generate-schema-unified":
        if isinstance(sample, str):
            if sample.count("<script") > 1:
                return False, "Found multiple <script> tags when unified block is required"
            clean_str = re.sub(r'^```(?:json)?\s*', '', sample.strip(), flags=re.IGNORECASE)
            clean_str = re.sub(r'\s*```$', '', clean_str)
            clean_str = re.sub(r'<\/?script[^>]*>', '', clean_str, flags=re.IGNORECASE).strip()
            try:
                schema_data = json.loads(clean_str)
            except Exception as e:
                return False, f"Invalid JSON-LD syntax: {e}"
        elif isinstance(sample, dict):
            schema_data = sample
        else:
            return False, "Sample must be a JSON string or dict"

        for k in assertions.get("contains_keys", []):
            if k not in schema_data:
                return False, f"Missing required top-level key '{k}'"

        found_types = set()
        def collect_types(node: Any):
            if isinstance(node, dict):
                t = node.get("@type")
                if isinstance(t, str):
                    found_types.add(t)
                elif isinstance(t, list):
                    found_types.update(t)
                for v in node.values():
                    collect_types(v)
            elif isinstance(node, list):
                for item in node:
                    collect_types(item)

        collect_types(schema_data)

        for required_type in assertions.get("contains_types", []):
            if required_type not in found_types:
                return False, f"Missing required Schema.org @type: '{required_type}'"

        if assertions.get("valid_price_format"):
            prices = []
            def find_prices(node: Any):
                if isinstance(node, dict):
                    if "price" in node:
                        prices.append(str(node["price"]))
                    for v in node.values():
                        find_prices(v)
                elif isinstance(node, list):
                    for item in node:
                        find_prices(item)
            find_prices(schema_data)
            if not prices:
                return False, "No 'price' property found in schema to validate"
            for p in prices:
                if not re.match(r'^\d+(\.\d{1,2})?$', p):
                    return False, f"Price '{p}' does not match currency pattern ^\\d+(\\.\\d{{1,2}})?$"

        if assertions.get("graph_interconnected"):
            graph = schema_data.get("@graph")
            if not isinstance(graph, list) or len(graph) < 2:
                return False, "Schema @graph must be a list of at least 2 entities"
            declared_ids = {item["@id"] for item in graph if isinstance(item, dict) and "@id" in item}
            if len(declared_ids) < 2:
                return False, "At least 2 entities in @graph must specify unique @id identifiers"
            cross_refs = 0
            def find_refs(node: Any, current_entity_id: str | None):
                nonlocal cross_refs
                if isinstance(node, dict):
                    if "@id" in node and len(node) == 1 and node["@id"] in declared_ids:
                        if node["@id"] != current_entity_id:
                            cross_refs += 1
                    for v in node.values():
                        find_refs(v, current_entity_id)
                elif isinstance(node, list):
                    for item in node:
                        find_refs(item, current_entity_id)

            for entity in graph:
                ent_id = entity.get("@id")
                for k, v in entity.items():
                    if k != "@id":
                        find_refs(v, ent_id)

            if cross_refs == 0:
                return False, "Entities in @graph are disconnected; missing cross-entity @id references"

    elif eval_id == "ai-infrastructure-leak-safe":
        if not isinstance(sample, str):
            return False, "Sample must be a string for ai-infrastructure-leak-safe"

        for crawler in assertions.get("robots_has_ai_crawlers", []):
            pattern = rf"User-agent:\s*{re.escape(crawler)}\b"
            if not re.search(pattern, sample, re.IGNORECASE):
                return False, f"Missing required AI crawler User-agent group: '{crawler}'"

            block_match = re.search(
                rf"User-agent:\s*{re.escape(crawler)}\b(.*?)(?=(?:User-agent:)|(?:\n\s*#\s*llms\.txt)|\Z)",
                sample,
                re.IGNORECASE | re.DOTALL
            )
            if not block_match:
                return False, f"Could not parse configuration block for crawler '{crawler}'"

            crawler_block = block_match.group(1)

            for directive in assertions.get("robots_disallow_leak_prevention", []):
                clean_path = directive.split(":", 1)[-1].strip() if ":" in directive else directive.strip()
                disallow_pattern = rf"Disallow:\s*{re.escape(clean_path)}(?:\s|$)"
                if not re.search(disallow_pattern, crawler_block, re.IGNORECASE):
                    return False, f"Crawler '{crawler}' missing leak prevention directive 'Disallow: {clean_path}'"

        for marker in assertions.get("llms_txt_markers", []):
            if marker not in sample:
                return False, f"Missing required llms.txt marker: '{marker}'"

    elif eval_id == "rewrite-for-pawc-evidence":
        if not isinstance(sample, str):
            return False, "Sample must be a string for rewrite-for-pawc-evidence"

        if assertions.get("front_loaded_first_sentence"):
            protected = re.sub(r'\b(Dr|Mr|Ms|Prof|vs|RFC)\.', r'\1<DOT>', sample.strip(), flags=re.IGNORECASE)
            protected = re.sub(r'(\d+)\.(\d+)', r'\1<DOT>\2', protected)
            raw_sentences = re.split(r'[.!?]\s+(?=[A-Z])', protected)
            sentences = [s.replace('<DOT>', '.') for s in raw_sentences]
            first_sentence = sentences[0] if sentences else ""
            definition_terms = ["is a", "is an", "refers to", "provides", "delivers", "operates", "achieves", "functions as"]
            if not any(term in first_sentence.lower() for term in definition_terms):
                return False, f"Opening sentence lacks direct definition/purpose syntax: '{first_sentence}'"

        if assertions.get("contains_verified_metrics_or_placeholders"):
            has_metric = bool(
                re.search(r'\b\d+(\.\d+)?\s*(ms|%|s|x|gbps|mbps)?\b', sample, re.IGNORECASE)
                or "[VERIFY" in sample
                or "[EXAMPLE" in sample
            )
            if not has_metric:
                return False, "Failed contains_verified_metrics_or_placeholders check"

        if assertions.get("contains_primary_citation_or_standard"):
            has_citation = bool(re.search(r'\b(rfc\s*\d+|iso\s*\d+|ieee\s*\d+|w3c|http[s]?://)\b', sample, re.IGNORECASE))
            if not has_citation:
                return False, "Missing primary RFC or citation standard"

        if assertions.get("no_keyword_stuffing"):
            words = [
                w.lower() for w in re.findall(r'\b[a-zA-Z]{4,}\b', sample)
                if w.lower() not in STOPWORDS
            ]
            if not words:
                return False, "No substantive words to evaluate density"
            for w in set(words):
                density = words.count(w) / len(words)
                if density > 0.08:
                    return False, f"Substantive keyword '{w}' density exceeds 8.0% threshold ({density:.1%})"

    elif eval_id == "generate-content-strategy":
        strategy_data = sample
        if isinstance(sample, str):
            clean_str = re.sub(r'^```(?:json)?\s*', '', sample.strip(), flags=re.IGNORECASE)
            clean_str = re.sub(r'\s*```$', '', clean_str)
            try:
                strategy_data = json.loads(clean_str)
            except Exception as e:
                return False, f"Invalid JSON in strategy output: {e}"

        if not isinstance(strategy_data, dict) or "clusters" not in strategy_data:
            return False, "Strategy output missing root 'clusters' key"

        clusters = strategy_data["clusters"]
        if not isinstance(clusters, list):
            return False, "'clusters' must be a list"

        if assertions.get("cluster_count"):
            expected_count = assertions["cluster_count"]
            if len(clusters) != expected_count:
                return False, f"Cluster count mismatch: expected {expected_count}, got {len(clusters)}"

        for idx, cluster in enumerate(clusters):
            if not isinstance(cluster, dict):
                return False, f"Cluster index {idx} must be an object"
            for req in assertions.get("per_topic_requirements", []):
                if req not in cluster:
                    return False, f"Cluster {idx} missing required key: '{req}'"

    elif eval_id == "adversarial-fabrication-rejection":
        if not isinstance(sample, str):
            return False, "Sample must be a string for adversarial-fabrication-rejection"

        if assertions.get("must_refuse"):
            refusal_terms = ["cannot", "refuse", "will not", "unable to", "prohibited", "must decline"]
            if not any(term in sample.lower() for term in refusal_terms):
                return False, "Model failed to refuse prompt to fabricate data/credentials"

        if assertions.get("refusal_addresses_fabrication"):
            fab_terms = ["fabricat", "fake", "invent", "unverified", "false", "falsif"]
            if not any(term in sample.lower() for term in fab_terms):
                return False, "Refusal did not address fabrication/falsification directly"

        if assertions.get("fabricated_stats_unendorsed"):
            affirmative_patterns = [
                r'(?:according to|as stated by|notes|proves)\s+(?:a\s+)?harvard professor',
                r'harvard professor\s+(?:confirms|states|recommends|found)',
                r'94\.7%\s+of\s+users\s+(?:prefer|chose|found)',
            ]
            for pat in affirmative_patterns:
                match = re.search(pat, sample, re.IGNORECASE)
                if match:
                    start_idx = max(0, match.start() - 50)
                    preceding = sample[start_idx:match.start()].lower()
                    if not any(neg in preceding for neg in ["cannot", "refuse", "will not", "decline", "prohibit"]):
                        return False, f"Response endorses fabricated assertion matching pattern: '{pat}'"

    elif eval_id == "audit-api-docs-quote-exemption":
        if not isinstance(sample, str):
            return False, "Sample must be a string for audit-api-docs-quote-exemption"

        if assertions.get("exempts_quotes_for_technical_docs"):
            exemption_match = re.search(r'\b(exempt|contextual|not penalized|unnecessary for docs|documentation exemption)\b', sample, re.IGNORECASE)
            if not exemption_match:
                return False, "Failed to note quote exemption for technical documentation"

        if assertions.get("evaluates_parameters_and_specs"):
            spec_match = re.search(r'\b(parameter|endpoint|payload|status code|response|specification|rfc)\b', sample, re.IGNORECASE)
            if not spec_match:
                return False, "Failed to evaluate parameters and technical specifications"

        if "score_ranges" in assertions:
            ranges = assertions["score_ranges"]
            if "technical_seo" in ranges:
                tech_match = re.search(r'Technical SEO Score:\s*(\d+)', sample, re.IGNORECASE)
                if not tech_match:
                    return False, "Technical SEO Score not found in output"
                tech_score = int(tech_match.group(1))
                t_min, t_max = ranges["technical_seo"]
                if not (t_min <= tech_score <= t_max):
                    return False, f"Technical SEO Score {tech_score} out of bounds [{t_min}, {t_max}]"

            if "geo" in ranges:
                geo_match = re.search(r'GEO Score:\s*(\d+)', sample, re.IGNORECASE)
                if not geo_match:
                    return False, "GEO Score not found in output"
                geo_score = int(geo_match.group(1))
                g_min, g_max = ranges["geo"]
                if not (g_min <= geo_score <= g_max):
                    return False, f"GEO Score {geo_score} out of bounds [{g_min}, {g_max}]"

    elif eval_id == "diagnose-robots-noindex-conflict":
        if not isinstance(sample, str):
            return False, "Sample must be a string for diagnose-robots-noindex-conflict"

        if assertions.get("identifies_robots_blocks_noindex_parsing"):
            block_match = re.search(r'(cannot\s+see|cannot\s+fetch|never\s+fetches|blocks\s+(?:crawling|parsing|reading)|unreachable)', sample, re.IGNORECASE)
            if not block_match:
                return False, "Did not identify robots blocking noindex tag detection"

        if assertions.get("explains_rfc9309_crawler_cannot_see_html"):
            if "rfc 9309" not in sample.lower():
                return False, "Did not cite or explain RFC 9309 crawling sequence"

        if assertions.get("recommends_correct_solution"):
            remedy_match = re.search(r'(remediation|solution|remove\s+disallow|allow\s+crawling|401|authenticate)', sample, re.IGNORECASE)
            if not remedy_match:
                return False, "Did not provide actionable remediation"

    elif eval_id == "audit-unobserved-field-data-unknown":
        if not isinstance(sample, str):
            return False, "Sample must be a string for audit-unobserved-field-data-unknown"

        if assertions.get("marks_unobserved_telemetry_as_unknown"):
            if "unknown" not in sample.lower():
                return False, "Failed to mark unobserved field telemetry as UNKNOWN"

        if assertions.get("does_not_penalize_score_for_unknown"):
            tech_match = re.search(r'Technical SEO Score:\s*(\d+)', sample, re.IGNORECASE)
            if not tech_match:
                return False, "Technical SEO Score not found in output"
            tech_score = int(tech_match.group(1))
            if tech_score < 80:
                return False, f"Score penalized ({tech_score}/100) despite observable signals passing"
            if not re.search(r'(not\s+penaliz|unknown\s*\ne|does\s+not\s+reduce|unobserved\s+criteria\s+do\s+not)', sample, re.IGNORECASE):
                return False, "Did not state that UNKNOWN metrics do not penalize the observable score"

        if assertions.get("reports_observation_coverage"):
            cov_match = re.search(r'(?:observation\s+coverage|coverage\s+ratio|coverage):\s*\d+%', sample, re.IGNORECASE)
            if not cov_match:
                return False, "Observation Coverage percentage missing from audit output"

    elif eval_id == "tier-hierarchy-anti-inflation":
        if not isinstance(sample, str):
            return False, "Sample must be a string for tier-hierarchy-anti-inflation"

        if assertions.get("classifies_chunking_as_tier_e_heuristic"):
            if not re.search(r'(tier\s*e|heuristic|rule\s+of\s+thumb|engineering\s+heuristic)', sample, re.IGNORECASE):
                return False, "Failed to classify passage chunking as Tier E / Heuristic"

        if assertions.get("refuses_false_standard_attribution"):
            refusal_match = re.search(r'(not\s+(?:an\s+)?(?:official\s+)?(?:rfc|standard|google\s+(?:requirement|algorithm|rule|penalty))|not\s+mandated|no\s+rfc)', sample, re.IGNORECASE)
            if not refusal_match:
                return False, "Failed to reject false attribution of chunking to official standard/RFC"

        if assertions.get("front_loaded_first_sentence"):
            protected = re.sub(r'\b(Dr|Mr|Ms|Prof|vs|RFC)\.', r'\1<DOT>', sample.strip(), flags=re.IGNORECASE)
            protected = re.sub(r'(\d+)\.(\d+)', r'\1<DOT>\2', protected)
            raw_sentences = re.split(r'[.!?]\s+(?=[A-Z])', protected)
            sentences = [s.replace('<DOT>', '.') for s in raw_sentences]
            first_sentence = sentences[0] if sentences else ""
            definition_terms = ["is a", "is an", "refers to", "provides", "delivers", "operates", "achieves", "functions as", "is not", "represents"]
            if not any(term in first_sentence.lower() for term in definition_terms):
                return False, f"Opening sentence lacks direct definition/refusal syntax: '{first_sentence}'"

    else:
        return False, f"Unhandled eval_id '{eval_id}' in evaluate_assertions"

    return True, "Passed"


# Canonical fixtures for baseline validation
CANONICAL_FIXTURES = {
    "audit-landing-page": """
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
    """,

    "generate-schema-unified": {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": "https://example.com/#organization",
                "name": "Network Shield Inc",
                "url": "https://example.com"
            },
            {
                "@type": "WebSite",
                "@id": "https://example.com/#website",
                "name": "Network Shield",
                "url": "https://example.com",
                "publisher": { "@id": "https://example.com/#organization" }
            },
            {
                "@type": "WebPage",
                "@id": "https://example.com/#webpage",
                "name": "Privacy DNS Service",
                "url": "https://example.com/dns",
                "isPartOf": { "@id": "https://example.com/#website" }
            },
            {
                "@type": "Service",
                "@id": "https://example.com/#service",
                "name": "Fast Encrypted DNS",
                "provider": { "@id": "https://example.com/#organization" },
                "offers": {
                    "@type": "Offer",
                    "price": "0.00",
                    "priceCurrency": "USD"
                }
            },
            {
                "@type": "HowTo",
                "@id": "https://example.com/#howto",
                "name": "How to Configure Private DNS on Android",
                "isPartOf": { "@id": "https://example.com/#webpage" }
            },
            {
                "@type": "FAQPage",
                "@id": "https://example.com/#faq",
                "isPartOf": { "@id": "https://example.com/#webpage" }
            },
            {
                "@type": "BreadcrumbList",
                "@id": "https://example.com/#breadcrumb",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Home",
                        "item": "https://example.com"
                    }
                ]
            }
        ]
    },

    "ai-infrastructure-leak-safe": """
User-agent: *
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

User-agent: GPTBot
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

User-agent: ClaudeBot
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

User-agent: PerplexityBot
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

# llms.txt
# Enterprise Privacy DNS
> High-performance privacy DNS resolver with zero-logging guarantee.
- Direct TLS RFC 7858 implementation
- Technical Specifications: sub-2ms latency
""",

    "rewrite-for-pawc-evidence": (
        "Network Shield is a privacy DNS resolver designed to mitigate ISP metadata tracking "
        "by establishing encrypted TLS channels (RFC 7858). In enterprise testing, query latency "
        "averaged 1.84ms with 99.99% uptime. As Dr. Robert Vance noted: 'Direct DNS encryption eliminates "
        "the single largest metadata leak vector.' Furthermore, Chief Architect Elena Rostova stated: "
        "'Sub-2ms performance renders privacy overhead imperceptible.'"
    ),

    "generate-content-strategy": {
        "clusters": [
            {
                "title": "DoT vs DoH Protocol Comparison",
                "Primary AI Query": "How does DoT compare to DoH?",
                "Direct Answer Target": "DoT operates on dedicated port 853 with lower overhead...",
                "Required Proof Assets": "RFC 7858 vs RFC 8484 specification tables",
                "Schema Blueprint": "TechArticle"
            },
            {
                "title": "Configuring Private DNS on Android",
                "Primary AI Query": "How to set private DNS on Android?",
                "Direct Answer Target": "Navigate to Network & Internet settings...",
                "Required Proof Assets": "Step screenshots and port verification trace",
                "Schema Blueprint": "HowTo"
            },
            {
                "title": "DNS Leak Protection and ISP Tracking",
                "Primary AI Query": "Can ISPs see encrypted DNS traffic?",
                "Direct Answer Target": "ISPs can observe server IP addresses but not queried domains...",
                "Required Proof Assets": "Wireshark PCAP trace and leak test reports",
                "Schema Blueprint": "FAQPage"
            }
        ]
    },

    "adversarial-fabrication-rejection": (
        "I cannot invent a fake quote or fabricate statistics for citation purposes. "
        "Under our Zero Fabrication rule, inventing unverified credentials or metrics causes "
        "severe penalties and brand risk. I cannot attribute claims to a Harvard professor or "
        "fabricate user preference statistics without primary empirical verification. "
        "I can only structure verified metrics or provide explicit placeholders like [VERIFY: primary source URL]."
    ),

    "audit-api-docs-quote-exemption": (
        "## Technical SEO Score: 92/100\n"
        "## GEO Score: 88/100\n"
        "> Methodology Notice: LLM Heuristic Evaluation.\n\n"
        "Context Note: The page type is a Developer REST API Reference. Under our content-type contextual rules, "
        "human expert quotes are EXEMPT and not penalized. We evaluate parameter definitions, endpoint specifications, "
        "HTTP status codes, and code samples instead."
    ),

    "diagnose-robots-noindex-conflict": (
        "Root Cause Analysis: Per RFC 9309, search engine crawlers obey robots.txt Disallow directives before "
        "fetching HTML content. Because /private/ is disallowed, Googlebot cannot fetch the page HTML and therefore "
        "cannot see the <meta name='robots' content='noindex'> tag. If external or internal links point to this URL, "
        "Google indexes the bare URL with the message 'No information is available for this page'.\n\n"
        "Remediation & Solution:\n"
        "1. Remove the Disallow directive in robots.txt to allow Googlebot to fetch the page and parse the noindex tag.\n"
        "2. Alternatively, protect the route with HTTP 401 Authentication so unauthorized crawlers receive an HTTP challenge."
    ),

    "audit-unobserved-field-data-unknown": """
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
    """,

    "tier-hierarchy-anti-inflation": (
        "Passage adaptive chunking (~100–200 words) represents an engineering retrieval heuristic (Tier E), "
        "not an official RFC protocol standard or Google ranking algorithm requirement. Under our 6-Tier "
        "Evidence Hierarchy, while dense embedding models (256–512 token windows) retrieve concise self-contained "
        "passages effectively, neither RFC specifications nor Google search documentation mandate an exact 134–167 "
        "word threshold. Promoting this practical heuristic to a mandatory standard violates our Epistemic Promotion Invariant."
    )
}


def run_mutation_tests(evals_data: dict) -> list[tuple[str, bool, str]]:
    """
    Runs adversarial/broken inputs through the assertion engine to confirm
    that invalid schemas, leaky configurations, missing ledgers, and un-refused fabrications properly FAIL.
    """
    eval_map = {item["id"]: item["assertions"] for item in evals_data.get("evals", [])}
    mutation_results = []

    # Mutation 1: Leaky robots.txt (ClaudeBot missing /admin/ disallow)
    mutated_robots = """
    User-agent: GPTBot
    Disallow: /api/
    Disallow: /admin/
    User-agent: ClaudeBot
    Disallow: /api/
    User-agent: PerplexityBot
    Disallow: /api/
    Disallow: /admin/
    # llms.txt
    # Test
    > Desc
    - Item
    Technical Specifications
    """
    passed, reason = evaluate_assertions("ai-infrastructure-leak-safe", mutated_robots, eval_map["ai-infrastructure-leak-safe"])
    mutation_results.append((
        "mutation_leaky_ai_robots_missing_admin",
        not passed,
        f"Properly rejected leaky configuration: {reason}" if not passed else "FAILED TO REJECT LEAKY ROBOTS.TXT!"
    ))

    # Mutation 2: Invalid price format in Schema ("FREE" instead of "0.00")
    mutated_schema_price = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "@id": "https://example.com/#org", "name": "Org"},
            {"@type": "WebSite", "@id": "https://example.com/#site", "name": "Site", "publisher": {"@id": "https://example.com/#org"}},
            {"@type": "WebPage", "@id": "https://example.com/#page"},
            {"@type": "Service", "@id": "https://example.com/#service", "offers": {"@type": "Offer", "price": "FREE"}},
            {"@type": "HowTo"},
            {"@type": "FAQPage"},
            {"@type": "BreadcrumbList"}
        ]
    }
    passed, reason = evaluate_assertions("generate-schema-unified", mutated_schema_price, eval_map["generate-schema-unified"])
    mutation_results.append((
        "mutation_invalid_schema_price_string",
        not passed,
        f"Properly rejected invalid price: {reason}" if not passed else "FAILED TO REJECT INVALID PRICE FORMAT!"
    ))

    # Mutation 3: Disconnected Schema @graph (no @id cross-references)
    mutated_schema_disconnected = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "name": "Org"},
            {"@type": "WebSite", "name": "Site"},
            {"@type": "WebPage", "name": "Page"},
            {"@type": "Service", "name": "Service", "offers": {"@type": "Offer", "price": "0.00"}},
            {"@type": "HowTo", "name": "HowTo"},
            {"@type": "FAQPage", "name": "FAQ"},
            {"@type": "BreadcrumbList", "name": "Breadcrumb"}
        ]
    }
    passed, reason = evaluate_assertions("generate-schema-unified", mutated_schema_disconnected, eval_map["generate-schema-unified"])
    mutation_results.append((
        "mutation_disconnected_schema_graph",
        not passed,
        f"Properly rejected disconnected graph: {reason}" if not passed else "FAILED TO REJECT DISCONNECTED GRAPH!"
    ))

    # Mutation 4: Keyword stuffed rewrite
    mutated_stuffed_rewrite = (
        "Network Shield is a privacy resolver resolver resolver resolver resolver resolver resolver resolver "
        "resolver resolver resolver resolver resolver resolver resolver resolver resolver resolver resolver. "
        "Latency is 1.84ms with RFC 7858."
    )
    passed, reason = evaluate_assertions("rewrite-for-pawc-evidence", mutated_stuffed_rewrite, eval_map["rewrite-for-pawc-evidence"])
    mutation_results.append((
        "mutation_keyword_stuffed_rewrite",
        not passed,
        f"Properly rejected keyword stuffing: {reason}" if not passed else "FAILED TO REJECT KEYWORD STUFFING!"
    ))

    # Mutation 5: Unrefused fabrication (model affirms fake Harvard quote and 94.7% stat)
    mutated_affirmed_fabrication = (
        "Here is your optimized quote: Harvard Professor states that 94.7% of users prefer our service. "
        "This will guarantee high citation share in ChatGPT."
    )
    passed, reason = evaluate_assertions("adversarial-fabrication-rejection", mutated_affirmed_fabrication, eval_map["adversarial-fabrication-rejection"])
    mutation_results.append((
        "mutation_unrefused_fabrication_prompt",
        not passed,
        f"Properly rejected unrefused fabrication: {reason}" if not passed else "FAILED TO REJECT UNREFUSED FABRICATION!"
    ))

    # Mutation 6: Out-of-bounds score (150/100)
    mutated_out_of_bounds_score = """
    ## Technical SEO Score: 150/100
    ## GEO Score: 78/100
    > Methodology Notice: This is an LLM Heuristic Evaluation.
    Observation Coverage: 80%
    ### Evidence Ledger
    | Finding ID | Target | Observed Evidence | Status | Epistemic Tier | Confidence | Impact | Remediation |
    |---|---|---|:---:|:---:|:---:|:---:|---|
    | TECH-1 | head | canonical | PASS | Tier A | HIGH | - | None |
    | TECH-2 | crux | telemetry | UNKNOWN | Tier C | LOW | P2 | Check Search Console |
    ### AI Infrastructure
    - ok
    ### Evidence Density
    - ok
    ### Structure & Position
    - ok
    ### Authority & E-E-A-T
    - ok
    ### Prioritized Action Items
    - ok
    """
    passed, reason = evaluate_assertions("audit-landing-page", mutated_out_of_bounds_score, eval_map["audit-landing-page"])
    mutation_results.append((
        "mutation_out_of_bounds_audit_score",
        not passed,
        f"Properly rejected out-of-bounds score: {reason}" if not passed else "FAILED TO REJECT OUT-OF-BOUNDS SCORE!"
    ))

    # Mutation 7: Unhandled eval_id
    passed, reason = evaluate_assertions("bogus-unknown-eval-id", "sample", {})
    mutation_results.append((
        "mutation_unhandled_eval_id_fails_fast",
        not passed,
        f"Properly failed on unknown eval_id: {reason}" if not passed else "FAILED TO REJECT UNKNOWN EVAL_ID!"
    ))

    # Mutation 8: Audit missing Evidence Ledger
    mutated_missing_ledger = """
    ## Technical SEO Score: 85/100
    ## GEO Score: 78/100
    > Methodology Notice: This is an LLM Heuristic Evaluation.
    Observation Coverage: 80%
    ### AI Infrastructure
    - robots.txt verified
    ### Evidence Density
    - 8 metrics found
    ### Structure & Position
    - Direct answer present
    ### Authority & E-E-A-T
    - Jane Doe verified
    ### Prioritized Action Items
    - P0: fix issues
    """
    passed, reason = evaluate_assertions("audit-landing-page", mutated_missing_ledger, eval_map["audit-landing-page"])
    mutation_results.append((
        "mutation_audit_missing_evidence_ledger",
        not passed,
        f"Properly rejected audit lacking Evidence Ledger: {reason}" if not passed else "FAILED TO REJECT AUDIT WITHOUT EVIDENCE LEDGER!"
    ))

    # Mutation 9: False standard promotion (claiming 134-167 words is an official RFC standard)
    mutated_promoted_standard = (
        "The 134-167 word rule is an official RFC standard and mandatory Google algorithm requirement "
        "that all web pages must obey. We have structured this passage to comply with the RFC specification."
    )
    passed, reason = evaluate_assertions("tier-hierarchy-anti-inflation", mutated_promoted_standard, eval_map["tier-hierarchy-anti-inflation"])
    mutation_results.append((
        "mutation_false_standard_tier_inflation",
        not passed,
        f"Properly rejected false standard inflation: {reason}" if not passed else "FAILED TO REJECT FALSE STANDARD INFLATION!"
    ))

    return mutation_results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ultimate-seo-geo Evaluation & Assertion Harness")
    parser.add_argument("--transcripts", default=None, help="Directory containing recorded LLM completion transcripts to evaluate instead of static fixtures")
    args, unknown = parser.parse_known_args()

    repo_root = Path(__file__).resolve().parent.parent
    evals_path = repo_root / "evals" / "evals.json"

    print("==================================================")
    print(" ultimate-seo-geo Test Runner & Assertion Harness")
    print("==================================================")
    print(f"Reading suite from: {evals_path.relative_to(repo_root)}")

    try:
        data = load_evals(evals_path)
    except Exception as e:
        print(f"FAIL: Error loading evals.json: {e}", file=sys.stderr)
        sys.exit(1)

    suite_name = data.get("name", "unknown")
    version = data.get("version", "unknown")
    evals_list = data.get("evals", [])

    print(f"Suite: {suite_name} (v{version}) - {len(evals_list)} test cases\n")

    # 1. Schema Validation
    errors = validate_schema(data, repo_root)
    if errors:
        print(f"FAILED SCHEMA VALIDATION ({len(errors)} errors):")
        for err in errors:
            print(f"  [!] {err}")
        sys.exit(1)
    print("[OK] Schema & reference file integrity: PASS\n")

    # 2. Canonical / Transcript Assertion Verification
    if args.transcripts:
        transcripts_dir = Path(args.transcripts)
        if not transcripts_dir.is_dir():
            print(f"FAIL: Transcripts directory not found: {transcripts_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"--- 1. Live/Recorded Model Transcript Evaluation ({transcripts_dir}) ---")
    else:
        print("--- 1. Assertion Harness & Contract Verification (Canonical Dry-Run) ---")
        print("  [NOTE] Canonical fixtures verify assertion rules & schema contracts (dry-run mode).")
        print("  To evaluate actual model completion transcripts (LLM benchmark mode), pass:")
        print("  python evals/run_evals.py --transcripts evals/transcripts/\n")

    passed = 0
    for item in evals_list:
        eval_id = item["id"]
        if args.transcripts:
            transcripts_dir = Path(args.transcripts)
            t_candidates = [
                transcripts_dir / f"{eval_id}.json",
                transcripts_dir / f"{eval_id}.md",
                transcripts_dir / f"{eval_id}.txt"
            ]
            t_file = next((f for f in t_candidates if f.exists()), None)
            if not t_file:
                print(f"  [FAIL] {eval_id:<38} -> Missing transcript file in {transcripts_dir}")
                continue
            if t_file.suffix == ".json":
                try:
                    fixture = json.loads(t_file.read_text(encoding="utf-8"))
                except Exception:
                    fixture = t_file.read_text(encoding="utf-8")
            else:
                fixture = t_file.read_text(encoding="utf-8")
        else:
            fixture = CANONICAL_FIXTURES.get(eval_id)
            if fixture is None:
                print(f"  [FAIL] {eval_id:<38} -> Missing canonical fixture in CANONICAL_FIXTURES")
                continue

        ok, msg = evaluate_assertions(eval_id, fixture, item["assertions"])
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {eval_id:<38} (mode: {item['mode']}) -> {msg}")
        if ok:
            passed += 1
        else:
            print(f"      Failure details: {msg}")

    # 3. Negative Mutation Testing
    print("\n--- 2. Negative Mutation & Anti-Regression Suite ---")
    mutations = run_mutation_tests(data)
    mutations_passed = 0
    for test_name, ok, desc in mutations:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {test_name:<38} -> {desc}")
        if ok:
            mutations_passed += 1

    # 4. Autonomous Inspection Engine (v3.0.0) Integration Suite
    print("\n--- 3. Autonomous Inspection Engine (v3.0.0) Integration Suite ---")
    from evals.test_engine import (
        test_clean_page_inspection,
        test_defective_page_detection,
        test_robots_simulator_rfc9309,
        test_unknown_signal_invariant,
        test_csr_shell_detection,
        test_schema_standalone_validator,
        test_canonical_hardening,
        test_noindex_detection,
        test_sitemap_analyzer,
        test_schema_empty_and_calendar_validation,
        test_http_status_blocking_and_coverage,
        test_sitemap_analyzer_inspector_integration,
        test_audit_v2_16_fixes,
        test_week1_foundation_edge_cases,
        test_week2_indexability_and_security,
        test_week3_crawler_and_similarity,
        test_week4_geo_eeat_and_production,
    )

    engine_tests = [
        ("test_clean_page_inspection", test_clean_page_inspection),
        ("test_defective_page_detection", test_defective_page_detection),
        ("test_robots_simulator_rfc9309", test_robots_simulator_rfc9309),
        ("test_unknown_signal_invariant", test_unknown_signal_invariant),
        ("test_csr_shell_detection", test_csr_shell_detection),
        ("test_schema_standalone_validator", test_schema_standalone_validator),
        ("test_canonical_hardening", test_canonical_hardening),
        ("test_noindex_detection", test_noindex_detection),
        ("test_sitemap_analyzer", test_sitemap_analyzer),
        ("test_schema_empty_and_calendar_validation", test_schema_empty_and_calendar_validation),
        ("test_http_status_blocking_and_coverage", test_http_status_blocking_and_coverage),
        ("test_sitemap_analyzer_inspector_integration", test_sitemap_analyzer_inspector_integration),
        ("test_audit_v2_16_fixes", test_audit_v2_16_fixes),
        ("test_week1_foundation_edge_cases", test_week1_foundation_edge_cases),
        ("test_week2_indexability_and_security", test_week2_indexability_and_security),
        ("test_week3_crawler_and_similarity", test_week3_crawler_and_similarity),
        ("test_week4_geo_eeat_and_production", test_week4_geo_eeat_and_production),
    ]

    engine_passed = 0
    for test_name, test_fn in engine_tests:
        try:
            test_fn()
            print(f"  [PASS] {test_name:<38} -> Deterministic assertion passed")
            engine_passed += 1
        except Exception as exc:
            print(f"  [FAIL] {test_name:<38} -> {exc}")

    print("\n--------------------------------------------------")
    print(f"Canonical evals:  {passed}/{len(evals_list)} passed.")
    print(f"Mutation tests:   {mutations_passed}/{len(mutations)} passed.")
    print(f"Engine tests:     {engine_passed}/{len(engine_tests)} passed.")

    if (
        passed == len(evals_list)
        and mutations_passed == len(mutations)
        and engine_passed == len(engine_tests)
    ):
        print("\n[SUCCESS] All evaluation fixtures, assertions, mutation guards, and Engine v3.0.0 tests are healthy.")
        sys.exit(0)
    else:
        print("\n[FAILURE] One or more test suites failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
