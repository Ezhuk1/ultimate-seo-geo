"""
Deterministic JSON-LD & Schema.org Graph AST Analyzer.

Analyzes:
- JSON-LD syntax errors & unescaped characters (SCHEMA-SYNTAX-001)
- Multi-script fragmentation vs unified @graph architecture
- Entity cross-referencing via @id and orphaned entities (SCHEMA-GRAPH-INTERCONNECT-002)
- Offer price formats per Google Merchant specification (SCHEMA-PRICE-FORMAT-003)
- Author E-E-A-T sameAs profile verification (SCHEMA-AUTHOR-SAMEAS-004)
- Core required property completeness for major Schema types
"""

from __future__ import annotations
import json
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple


PRICE_REGEX = re.compile(r"^\d+(\.\d{1,2})?$")
RECOGNIZED_AUTHORITY_DOMAINS = [
    "wikidata.org", "wikipedia.org", "linkedin.com", "github.com",
    "orcid.org", "twitter.com", "x.com", "scholar.google.com"
]


@dataclass
class SchemaFinding:
    rule_id: str
    severity: str  # CRITICAL, WARNING, INFO
    entity_type: Optional[str]
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SchemaAnalysisResult:
    total_scripts: int = 0
    valid_scripts: int = 0
    syntax_errors: List[str] = field(default_factory=list)
    has_unified_graph: bool = False
    entities: List[Dict[str, Any]] = field(default_factory=list)
    entity_types: List[str] = field(default_factory=list)
    entity_ids: Set[str] = field(default_factory=set)
    referenced_ids: Set[str] = field(default_factory=set)
    orphaned_entities: List[str] = field(default_factory=list)
    duplicate_ids: List[str] = field(default_factory=list)
    syntax_valid: str = "YES"
    schema_org_structure: str = "VALID"
    google_rich_result_eligibility: str = "UNKNOWN"
    visible_content_consistency: str = "UNKNOWN"
    findings: List[SchemaFinding] = field(default_factory=list)


def _extract_ids_and_references(obj: Any, declared_ids: Set[str], referenced_ids: Set[str], is_root: bool = False):
    """Recursively traverses JSON-LD object to collect declared @ids and references."""
    if isinstance(obj, dict):
        obj_id = obj.get("@id")
        if obj_id and isinstance(obj_id, str):
            if is_root or "@type" in obj:
                declared_ids.add(obj_id)
            else:
                referenced_ids.add(obj_id)

        for key, value in obj.items():
            if key == "@id" and not is_root and "@type" not in obj:
                continue
            elif key in ("author", "publisher", "provider", "mainEntity", "isPartOf", "offers", "brand", "item"):
                if isinstance(value, dict) and "@id" in value:
                    ref = value["@id"]
                    if isinstance(ref, str):
                        referenced_ids.add(ref)
                elif isinstance(value, str) and (value.startswith("http") or value.startswith("#")):
                    referenced_ids.add(value)
            _extract_ids_and_references(value, declared_ids, referenced_ids, is_root=False)
    elif isinstance(obj, list):
        for item in obj:
            _extract_ids_and_references(item, declared_ids, referenced_ids, is_root=False)


def _find_entities_by_type(entities: List[Dict[str, Any]], target_type: str) -> List[Dict[str, Any]]:
    results = []
    for ent in entities:
        t = ent.get("@type")
        if t == target_type or (isinstance(t, list) and target_type in t):
            results.append(ent)
    return results


def analyze_json_ld(raw_json_blocks: List[str]) -> SchemaAnalysisResult:
    """
    Parses and evaluates JSON-LD script blocks.
    """
    result = SchemaAnalysisResult(total_scripts=len(raw_json_blocks))
    parsed_roots = []

    # 1. Parse JSON and validate syntax
    for idx, raw_text in enumerate(raw_json_blocks):
        clean_text = raw_text.strip()
        if not clean_text:
            continue
        try:
            data = json.loads(clean_text)
            result.valid_scripts += 1
            parsed_roots.append(data)
        except json.JSONDecodeError as exc:
            err_msg = f"Script block #{idx+1} JSON syntax error: {exc.msg} at line {exc.lineno}:{exc.colno}"
            result.syntax_errors.append(err_msg)
            result.findings.append(SchemaFinding(
                rule_id="SCHEMA-SYNTAX-001",
                severity="CRITICAL",
                entity_type=None,
                message=err_msg,
                details={"raw_snippet": clean_text[:200]}
            ))

    if result.total_scripts > 1:
        result.findings.append(SchemaFinding(
            rule_id="SCHEMA-GRAPH-INTERCONNECT-002",
            severity="INFO",
            entity_type=None,
            message=f"Multiple separate <script type='application/ld+json'> tags ({result.total_scripts}) detected. Recommended: unify into single @graph.",
            details={"script_count": result.total_scripts}
        ))

    # 2. Extract Entities from parsed roots
    for root in parsed_roots:
        if isinstance(root, dict):
            if "@graph" in root and isinstance(root["@graph"], list):
                result.has_unified_graph = True
                for item in root["@graph"]:
                    if isinstance(item, dict):
                        result.entities.append(item)
            else:
                result.entities.append(root)
        elif isinstance(root, list):
            for item in root:
                if isinstance(item, dict):
                    result.entities.append(item)

    # Check entity types
    for entity in result.entities:
        t = entity.get("@type")
        if not t:
            result.findings.append(SchemaFinding(
                rule_id="SCHEMA-TYPE-MISSING-007",
                severity="CRITICAL",
                entity_type=None,
                message="Schema entity is missing required '@type' attribute.",
                details={"entity_keys": list(entity.keys())}
            ))
        elif isinstance(t, str):
            result.entity_types.append(t)
        elif isinstance(t, list):
            result.entity_types.extend(t)

        ent_id = entity.get("@id")
        if ent_id and isinstance(ent_id, str):
            if ent_id in result.entity_ids:
                result.duplicate_ids.append(ent_id)
                result.findings.append(SchemaFinding(
                    rule_id="SCHEMA-DUPLICATE-ID-008",
                    severity="CRITICAL",
                    entity_type=entity.get("@type"),
                    message=f"Duplicate entity '@id' '{ent_id}' defined multiple times in the schema graph.",
                    details={"duplicate_id": ent_id}
                ))
            else:
                result.entity_ids.add(ent_id)

    # 3. Analyze Graph Interconnections
    entity_outgoing_refs: Dict[str, Set[str]] = {}
    for entity in result.entities:
        ent_id = entity.get("@id")
        out_refs: Set[str] = set()
        _extract_ids_and_references(entity, set(), out_refs, is_root=True)
        # Discard self-reference
        if ent_id in out_refs:
            out_refs.remove(ent_id)
        if ent_id:
            entity_outgoing_refs[ent_id] = out_refs
        result.referenced_ids.update(out_refs)

    # An entity is orphaned/disconnected if it has NO incoming references AND NO outgoing references to known entities
    if len(result.entities) > 1:
        known_ids = result.entity_ids
        for entity in result.entities:
            ent_type = entity.get("@type", "Unknown")
            ent_id = entity.get("@id")
            if not ent_id:
                result.orphaned_entities.append(f"{ent_type} (no @id)")
                continue

            has_incoming = ent_id in result.referenced_ids
            has_outgoing_to_known = bool(entity_outgoing_refs.get(ent_id, set()) & known_ids)

            if not has_incoming and not has_outgoing_to_known:
                result.orphaned_entities.append(f"{ent_type} ({ent_id})")

        if result.orphaned_entities:
            result.findings.append(SchemaFinding(
                rule_id="SCHEMA-GRAPH-INTERCONNECT-002",
                severity="WARNING",
                entity_type=None,
                message=f"Disconnected/orphaned entities found without graph references: {', '.join(result.orphaned_entities)}",
                details={"orphaned": result.orphaned_entities}
            ))

    # 4. Check Offer Prices (SCHEMA-PRICE-FORMAT-003)
    offers = _find_entities_by_type(result.entities, "Offer")
    # Also check offers embedded in products
    products = _find_entities_by_type(result.entities, "Product")
    for prod in products:
        prod_offers = prod.get("offers")
        if isinstance(prod_offers, dict):
            offers.append(prod_offers)
        elif isinstance(prod_offers, list):
            offers.extend([o for o in prod_offers if isinstance(o, dict)])

    for offer in offers:
        price = offer.get("price")
        if price is not None:
            price_str = str(price).strip()
            # If formatted like "$99" or "99,00" or invalid decimal
            if not PRICE_REGEX.match(price_str):
                result.findings.append(SchemaFinding(
                    rule_id="SCHEMA-PRICE-FORMAT-003",
                    severity="CRITICAL",
                    entity_type="Offer",
                    message=rf"Invalid price format '{price}'. Must strictly match '^\d+(\.\d{{1,2}})?$' without currency symbols or commas.",
                    details={"invalid_price": price}
                ))

    # 5. Check Author sameAs authority profiles (SCHEMA-AUTHOR-SAMEAS-004)
    raw_authors: List[Dict[str, Any]] = []
    for entity in result.entities:
        auth = entity.get("author")
        if isinstance(auth, dict):
            if not ("@id" in auth and len(auth) == 1):
                raw_authors.append(auth)
        elif isinstance(auth, list):
            raw_authors.extend([a for a in auth if isinstance(a, dict) and not ("@id" in a and len(a) == 1)])
        if entity.get("@type") in ("Person", "Organization"):
            raw_authors.append(entity)

    # Deduplicate authors to avoid repetitive findings for the same entity
    seen_authors = set()
    authors: List[Dict[str, Any]] = []
    for author in raw_authors:
        auth_key = author.get("@id") or f"{author.get('@type', '')}:{author.get('name', '')}"
        if auth_key not in seen_authors:
            seen_authors.add(auth_key)
            authors.append(author)

    for author in authors:
        same_as = author.get("sameAs")
        name = author.get("name", "Unknown author")
        profiles: List[str] = []
        if isinstance(same_as, str):
            profiles = [same_as]
        elif isinstance(same_as, list):
            profiles = [str(p) for p in same_as]

        has_trusted_profile = any(
            any(domain in prof.lower() for domain in RECOGNIZED_AUTHORITY_DOMAINS)
            for prof in profiles
        )

        if not profiles:
            result.findings.append(SchemaFinding(
                rule_id="SCHEMA-AUTHOR-SAMEAS-004",
                severity="WARNING",
                entity_type="Author",
                message=f"Author '{name}' is missing 'sameAs' profile links (Wikidata, LinkedIn, ORCID, GitHub).",
                details={"author_name": name}
            ))
        elif not has_trusted_profile:
            result.findings.append(SchemaFinding(
                rule_id="SCHEMA-AUTHOR-SAMEAS-004",
                severity="INFO",
                entity_type="Author",
                message=f"Author '{name}' sameAs links lack recognized authority entities (Wikidata, LinkedIn, ORCID).",
                details={"author_name": name, "profiles": profiles}
            ))

    # 6. Check Broken @id References (SCHEMA-BROKEN-REF-005)
    # References pointing to an @id not declared anywhere in this graph
    broken_refs = [
        ref for ref in result.referenced_ids
        if ref not in result.entity_ids and (ref.startswith("#") or any(ref.startswith(eid.split("#")[0]) for eid in result.entity_ids if "#" in eid))
    ]
    for b_ref in broken_refs:
        result.findings.append(SchemaFinding(
            rule_id="SCHEMA-BROKEN-REF-005",
            severity="CRITICAL",
            entity_type=None,
            message=f"Broken entity reference: '@id' '{b_ref}' referenced in property does not exist in the @graph.",
            details={"broken_id": b_ref}
        ))

    # 7. Check ISO 8601 Date Formats & Calendar Validity (SCHEMA-DATE-FORMAT-006)
    iso_date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$")
    for entity in result.entities:
        for date_key in ("datePublished", "dateModified"):
            val = entity.get(date_key)
            if val is not None:
                val_str = str(val).strip()
                is_valid_date = False
                if iso_date_pattern.match(val_str):
                    try:
                        date_part = val_str[:10]
                        datetime.strptime(date_part, "%Y-%m-%d")
                        if "T" in val_str:
                            iso_clean = val_str.replace("Z", "+00:00")
                            datetime.fromisoformat(iso_clean)
                        is_valid_date = True
                    except (ValueError, TypeError):
                        is_valid_date = False

                if not is_valid_date:
                    result.findings.append(SchemaFinding(
                        rule_id="SCHEMA-DATE-FORMAT-006",
                        severity="CRITICAL",
                        entity_type=entity.get("@type"),
                        message=f"Invalid {date_key} format or non-existent calendar date '{val}'. Schema.org strictly requires valid ISO 8601 calendar date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ).",
                        details={"key": date_key, "invalid_value": val}
                    ))

    # 8. Check Required Properties for High-Value Schema Types
    required_type_properties = {
        "Article": ["headline", "author"],
        "BlogPosting": ["headline", "author"],
        "NewsArticle": ["headline", "author"],
        "Product": ["name", "offers"],
        "Organization": ["name"],
        "LocalBusiness": ["name"],
        "BreadcrumbList": ["itemListElement"],
        "FAQPage": ["mainEntity"]
    }
    for entity in result.entities:
        t = entity.get("@type")
        types = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
        for type_name in types:
            req_props = required_type_properties.get(type_name, [])
            for prop in req_props:
                if prop not in entity or entity[prop] is None or entity[prop] == "":
                    result.findings.append(SchemaFinding(
                        rule_id="SCHEMA-REQUIRED-PROP-009",
                        severity="WARNING",
                        entity_type=type_name,
                        message=f"{type_name} entity is missing recommended property '{prop}'.",
                        details={"type": type_name, "missing_property": prop}
                    ))

    # 9. Check AggregateRating Integrity
    ratings = _find_entities_by_type(result.entities, "AggregateRating")
    for entity in result.entities:
        ar = entity.get("aggregateRating")
        if isinstance(ar, dict):
            ratings.append(ar)

    for r in ratings:
        r_val = r.get("ratingValue")
        b_val = r.get("bestRating", 5)
        try:
            if r_val is not None:
                num_r = float(r_val)
                num_b = float(b_val) if b_val is not None else 5.0
                if num_r > num_b:
                    result.findings.append(SchemaFinding(
                        rule_id="SCHEMA-RATING-VALIDITY-010",
                        severity="CRITICAL",
                        entity_type="AggregateRating",
                        message=f"ratingValue ({num_r}) cannot exceed bestRating ({num_b}).",
                        details={"ratingValue": num_r, "bestRating": num_b}
                    ))
        except (ValueError, TypeError):
            pass

        r_cnt = r.get("ratingCount") or r.get("reviewCount")
        if r_cnt is not None:
            try:
                if int(r_cnt) <= 0:
                    result.findings.append(SchemaFinding(
                        rule_id="SCHEMA-RATING-VALIDITY-010",
                        severity="WARNING",
                        entity_type="AggregateRating",
                        message=f"ratingCount/reviewCount must be greater than 0 (got {r_cnt})."
                    ))
            except (ValueError, TypeError):
                pass

    # 10. Compute 4-Tier Verdict
    result.syntax_valid = "NO" if result.syntax_errors else "YES"
    has_crit = any(f.severity == "CRITICAL" for f in result.findings)
    has_warn = any(f.severity == "WARNING" for f in result.findings)

    if result.syntax_valid == "NO" or has_crit:
        result.schema_org_structure = "INVALID"
    elif has_warn:
        result.schema_org_structure = "PARTIAL"
    else:
        result.schema_org_structure = "VALID"

    if result.schema_org_structure == "VALID":
        result.google_rich_result_eligibility = "ELIGIBLE"
    elif result.schema_org_structure == "PARTIAL":
        result.google_rich_result_eligibility = "WARNING"
    else:
        result.google_rich_result_eligibility = "UNKNOWN"

    return result


def validate_schema_snippet(snippet: str | dict | list) -> tuple[bool, list[str], SchemaAnalysisResult]:
    """
    Validates a standalone Schema.org JSON-LD snippet (string, dict, or list).
    Returns (is_valid, list_of_errors, SchemaAnalysisResult).
    """
    errors = []
    if isinstance(snippet, str):
        clean_text = snippet.strip()
        # Strip code fences if present
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\s*```$", "", clean_text)
        clean_text = re.sub(r"<\/?script[^>]*>", "", clean_text, flags=re.IGNORECASE).strip()
        try:
            parsed = json.loads(clean_text)
            blocks = [clean_text]
        except json.JSONDecodeError as exc:
            err = f"JSON syntax error: {exc.msg} at line {exc.lineno}:{exc.colno}"
            return False, [err], SchemaAnalysisResult(syntax_errors=[err])
    elif isinstance(snippet, (dict, list)):
        blocks = [json.dumps(snippet)]
    else:
        return False, ["Snippet must be a JSON string, dict, or list"], SchemaAnalysisResult()

    result = analyze_json_ld(blocks)
    if not result.entities or all(not e.get("@type") for e in result.entities):
        if not any(f.rule_id in ("SCHEMA-EMPTY-000", "SCHEMA-TYPE-MISSING-007") for f in result.findings):
            result.findings.append(SchemaFinding(
                rule_id="SCHEMA-EMPTY-000",
                severity="CRITICAL",
                entity_type=None,
                message="Schema snippet is empty or contains no valid Schema.org entities with '@type'.",
                details={}
            ))

    critical_or_warn = [
        f"[{fnd.severity}] {fnd.rule_id}: {fnd.message}"
        for fnd in result.findings
        if fnd.severity in ("CRITICAL", "WARNING")
    ]
    is_valid = len(critical_or_warn) == 0 and len(result.syntax_errors) == 0
    return is_valid, critical_or_warn, result


