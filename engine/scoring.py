"""
Multi-Dimensional Evidence Scoring Engine.

Calculates:
1. Observable Technical Score (0..100) strictly from measured signals
2. GEO Readiness Index (0..100) measuring AI extraction and graph viability
3. Observation Coverage (%) reflecting empirical measurement completeness
4. Enforces 'Unknown != Failure' invariant (unmeasured signals never penalize scores)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List
from .ledger import (
    EvidenceLedger,
    STATUS_CRITICAL,
    STATUS_WARNING,
    STATUS_PASS,
    STATUS_INFO,
    STATUS_UNKNOWN,
    STATUS_NOT_APPLICABLE,
    STATUS_NOT_MEASURED,
    CONFIDENCE_VERIFIED,
)
from .rules import get_rule_registry


@dataclass
class SecurityHygieneScore:
    score: int
    tier: str
    https_score: int
    hsts_score: int
    mixed_content_score: int
    headers_score: int
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GeoDimensions:
    answerability: int  # max 20
    evidence_density: int  # max 20
    entity_clarity: int  # max 15
    passage_extractability: int  # max 15
    source_attribution: int  # max 10
    schema_graph: int  # max 10
    freshness: int  # max 5
    ai_crawler_access: int  # max 5
    measured_count: int = 8
    total_dimensions: int = 8
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW
    unknown_dimensions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answerability": self.answerability,
            "evidence_density": self.evidence_density,
            "entity_clarity": self.entity_clarity,
            "passage_extractability": self.passage_extractability,
            "source_attribution": self.source_attribution,
            "schema_graph": self.schema_graph,
            "freshness": self.freshness,
            "ai_crawler_access": self.ai_crawler_access,
            "measured_count": self.measured_count,
            "total_dimensions": self.total_dimensions,
            "confidence": self.confidence,
            "unknown_dimensions": self.unknown_dimensions
        }


@dataclass
class ScoreBreakdown:
    observable_technical_score: int
    geo_readiness_index: int
    observation_coverage_pct: float
    technical_health_tier: str
    geo_maturity_tier: str
    critical_count: int
    warning_count: int
    pass_count: int
    not_measured_count: int
    deductions: List[Dict[str, Any]]
    criteria_total: int = 0
    criteria_observed: int = 0
    criteria_passed: int = 0
    criteria_failed: int = 0
    criteria_unknown: int = 0
    criteria_not_applicable: int = 0
    category_coverage: Dict[str, Any] = field(default_factory=dict)
    security_score: int = 100
    security_tier: str = "EXCELLENT"
    security_hygiene: Optional[SecurityHygieneScore] = None
    indexability_matrix: Optional[Dict[str, Any]] = None
    geo_dimensions: Optional[GeoDimensions] = None


def calculate_scores(ledger: EvidenceLedger) -> ScoreBreakdown:
    """
    Computes scores strictly according to empirical evidence rules.
    Driven dynamically by rules loaded from rules/*.json.
    """
    registry = get_rule_registry()
    coverage_pct = ledger.metadata.get("observation_coverage_percent", 100.0)

    # 1. Technical Score
    tech_score = 100
    deductions = []
    rule_penalties: Dict[str, int] = {}
    crit_count = 0
    warn_count = 0
    pass_count = 0
    unmeasured_count = 0

    for ev in ledger.evidence:
        if ev.status == STATUS_PASS:
            pass_count += 1
            continue
        elif ev.status in (STATUS_UNKNOWN, STATUS_NOT_MEASURED, "NOT_MEASURED"):
            unmeasured_count += 1
            # Invariant: Unmeasured/Unknown never deducts points!
            continue
        elif ev.status in (STATUS_NOT_APPLICABLE, STATUS_INFO):
            # Not applicable or informational recommendations incur 0 penalty
            continue

        if ev.category in ("technical", "schema", "performance"):
            rule = registry.get(ev.rule_id)

            if ev.status == STATUS_CRITICAL:
                crit_count += 1
                base_deduction = rule.score_weight if rule else (25 if ev.confidence == CONFIDENCE_VERIFIED else 15)
                max_rule_cap = rule.max_penalty_cap if rule else 25
            elif ev.status == STATUS_WARNING:
                warn_count += 1
                base_deduction = rule.score_weight if rule else (5 if ev.confidence != CONFIDENCE_VERIFIED else 10)
                max_rule_cap = rule.max_penalty_cap if rule else 15
            else:
                continue

            current_penalty = rule_penalties.get(ev.rule_id, 0)
            actual_deduction = min(base_deduction, max(0, max_rule_cap - current_penalty))
            if actual_deduction > 0:
                tech_score -= actual_deduction
                rule_penalties[ev.rule_id] = current_penalty + actual_deduction
                deductions.append({
                    "rule_id": ev.rule_id,
                    "title": ev.title,
                    "penalty": -actual_deduction,
                    "reason": ev.message,
                    "confidence": ev.confidence
                })

    tech_score = max(0, min(100, tech_score))

    # 2. GEO Readiness Index (8-Component Weighted Model per Princeton KDD 2024 / GEO Framework)
    content_signal = ledger.signals.get("content_total_words")
    status_signal = ledger.signals.get("http_status_code")
    has_error = bool(status_signal and status_signal.value and status_signal.value >= 400)
    has_no_content = bool(content_signal is not None and content_signal.value == 0)

    if has_error or has_no_content:
        geo_score = 0
        geo_dims = GeoDimensions(
            answerability=0,
            evidence_density=0,
            entity_clarity=0,
            passage_extractability=0,
            source_attribution=0,
            schema_graph=0,
            freshness=0,
            ai_crawler_access=0,
            confidence="HIGH"
        )
    else:
        unknown_dims: List[str] = []

        # Component 1: Answerability (Weight: 20)
        ev_ans = next((e for e in ledger.evidence if e.rule_id == "GEO-ANSWER-FRONTLOAD-001"), None)
        if ev_ans:
            if ev_ans.status == STATUS_PASS:
                dim_ans = 20
            elif ev_ans.status == STATUS_WARNING:
                dim_ans = 10
            elif ev_ans.status == STATUS_CRITICAL:
                dim_ans = 0
            else:
                dim_ans = 5
        else:
            dim_ans = 0
            unknown_dims.append("answerability")

        # Component 2: Evidence Density (Weight: 20)
        ev_sig = ledger.signals.get("content_evidence_density_score")
        ev_rule = next((e for e in ledger.evidence if e.rule_id == "GEO-EVIDENCE-METRICS-004"), None)
        if ev_sig and ev_sig.value is not None:
            dim_ev = min(20, max(0, round(20 * (ev_sig.value / 100))))
        elif ev_rule:
            dim_ev = 20 if ev_rule.status == STATUS_PASS else (8 if ev_rule.status == STATUS_WARNING else 0)
        else:
            dim_ev = 0
            unknown_dims.append("evidence_density")

        # Component 3: Entity Clarity (Weight: 15)
        ev_coref = next((e for e in ledger.evidence if e.rule_id == "GEO-COREFERENCE-INDEPENDENCE-003"), None)
        if ev_coref:
            dim_ent = 15 if ev_coref.status == STATUS_PASS else (8 if ev_coref.status == STATUS_WARNING else 0)
        else:
            dim_ent = 0
            unknown_dims.append("entity_clarity")

        # Component 4: Passage Extractability (Weight: 15)
        chunk_evs = [e for e in ledger.evidence if e.rule_id == "GEO-ADAPTIVE-CHUNKING-002"]
        if any(e.status == STATUS_CRITICAL for e in chunk_evs):
            dim_chunk = 0
        elif any(e.status == STATUS_WARNING for e in chunk_evs):
            dim_chunk = 5
        elif any(e.status == STATUS_PASS for e in chunk_evs):
            dim_chunk = 15 if not any(e.status == STATUS_INFO for e in chunk_evs) else 10
        else:
            dim_chunk = 0
            unknown_dims.append("passage_extractability")

        # Component 5: Source Attribution (Weight: 10)
        # Bugfix: evaluate citations via typed signal and PASS status, never grep error messages
        cit_rule = next((e for e in ledger.evidence if e.rule_id in ("GEO-EVIDENCE-METRICS-004", "GEO-SOURCE-ATTRIBUTION-005")), None)
        cit_signal = ledger.signals.get("content_citations_count")
        ev_sig_val = ledger.signals.get("content_evidence_density_score")
        has_citations = (
            (cit_rule and cit_rule.status == STATUS_PASS)
            or (cit_signal and cit_signal.value and cit_signal.value > 0)
            or (ev_sig_val and ev_sig_val.value and ev_sig_val.value >= 30)
        )
        if has_citations:
            dim_src = 10
        elif cit_rule and cit_rule.status == STATUS_WARNING:
            dim_src = 4
        else:
            dim_src = 0
            unknown_dims.append("source_attribution")

        # Component 6: Schema Graph (Weight: 10)
        ev_graph = next((e for e in ledger.evidence if e.rule_id == "SCHEMA-GRAPH-INTERCONNECT-002"), None)
        schema_count = ledger.signals.get("schema_entity_count")
        if ev_graph and ev_graph.status == STATUS_PASS:
            dim_schema = 10
        elif ev_graph and ev_graph.status == STATUS_WARNING:
            dim_schema = 5
        elif schema_count and schema_count.value and schema_count.value > 0:
            dim_schema = 5
        else:
            dim_schema = 0

        # Component 7: Freshness (Weight: 5)
        fresh_sig = ledger.signals.get("freshness_score")
        if fresh_sig and fresh_sig.is_measured:
            f_val = fresh_sig.value or 50
            dim_fresh = 5 if f_val >= 80 else (3 if f_val >= 50 else 1)
        else:
            dim_fresh = 0
            unknown_dims.append("freshness")

        # Component 8: AI Crawler Access (Weight: 5)
        rob_sig = ledger.signals.get("ai_crawler_summary")
        dim_crawl = 5  # RFC 9309 neutral default allow
        if rob_sig and isinstance(rob_sig.value, dict) and rob_sig.value:
            blocked = sum(1 for b, info in rob_sig.value.items() if not info.get("root_allowed", True))
            if blocked > 5:
                dim_crawl = 0
            elif blocked > 0:
                dim_crawl = 2
            else:
                dim_crawl = 5

        # Content Depth Guard: True content stubs (<25 words) cannot claim answerability or coreference independence
        if content_signal and content_signal.value is not None and content_signal.value < 25:
            dim_ans = 0
            dim_ent = 0
            dim_chunk = min(dim_chunk, 5)

        geo_score = min(100, max(0, dim_ans + dim_ev + dim_ent + dim_chunk + dim_src + dim_schema + dim_fresh + dim_crawl))

        measured_count = 8 - len(unknown_dims)
        conf = "HIGH" if measured_count >= 7 else ("MEDIUM" if measured_count >= 5 else "LOW")

        geo_dims = GeoDimensions(
            answerability=dim_ans,
            evidence_density=dim_ev,
            entity_clarity=dim_ent,
            passage_extractability=dim_chunk,
            source_attribution=dim_src,
            schema_graph=dim_schema,
            freshness=dim_fresh,
            ai_crawler_access=dim_crawl,
            measured_count=measured_count,
            total_dimensions=8,
            confidence=conf,
            unknown_dimensions=unknown_dims
        )

    # Determine Tiers
    if tech_score >= 90:
        tech_tier = "EXCELLENT"
    elif tech_score >= 75:
        tech_tier = "GOOD"
    elif tech_score >= 50:
        tech_tier = "NEEDS_ATTENTION"
    else:
        tech_tier = "CRITICAL"

    if geo_score >= 85:
        geo_tier = "STAGE_4_GEO_AUTHORITY"
    elif geo_score >= 70:
        geo_tier = "STAGE_3_STRUCTURED_ENTITY"
    elif geo_score >= 45:
        geo_tier = "STAGE_2_INDEXED_CONTENT"
    else:
        geo_tier = "STAGE_1_RAW_WEB"

    # 3. Security Hygiene Score (Separate 0..100 dimension, not penalized in technical score)
    https_sig = ledger.signals.get("target_is_https")
    hsts_sig = ledger.signals.get("http_hsts_present")
    insecure_res_sig = ledger.signals.get("html_insecure_resources_count")
    sec_hdrs_sig = ledger.signals.get("http_security_headers_count")

    is_https = bool(https_sig.value) if https_sig and https_sig.is_measured else True
    has_hsts = bool(hsts_sig.value) if hsts_sig and hsts_sig.is_measured else False
    insecure_count = insecure_res_sig.value if insecure_res_sig and insecure_res_sig.is_measured else 0
    no_mixed = (insecure_count == 0)
    sec_hdrs_count = sec_hdrs_sig.value if sec_hdrs_sig and sec_hdrs_sig.is_measured else 0

    https_pts = 25 if is_https else 0
    hsts_pts = 25 if has_hsts else 0
    mixed_pts = 25 if no_mixed else 0
    hdrs_pts = min(25, round(25 * (min(4, sec_hdrs_count) / 4)))

    sec_score = https_pts + hsts_pts + mixed_pts + hdrs_pts
    if sec_score >= 90:
        sec_tier = "EXCELLENT"
    elif sec_score >= 70:
        sec_tier = "GOOD"
    elif sec_score >= 50:
        sec_tier = "MODERATE_RISK"
    else:
        sec_tier = "VULNERABLE"

    sec_hygiene = SecurityHygieneScore(
        score=sec_score,
        tier=sec_tier,
        https_score=https_pts,
        hsts_score=hsts_pts,
        mixed_content_score=mixed_pts,
        headers_score=hdrs_pts,
        details={
            "is_https": is_https,
            "has_hsts": has_hsts,
            "insecure_resources_count": insecure_count,
            "security_headers_count": sec_hdrs_count
        }
    )

    return ScoreBreakdown(
        observable_technical_score=tech_score,
        geo_readiness_index=geo_score,
        observation_coverage_pct=coverage_pct,
        technical_health_tier=tech_tier,
        geo_maturity_tier=geo_tier,
        critical_count=crit_count,
        warning_count=warn_count,
        pass_count=pass_count,
        not_measured_count=unmeasured_count,
        deductions=deductions,
        criteria_total=ledger.metadata.get("criteria_total", 0),
        criteria_observed=ledger.metadata.get("criteria_observed", 0),
        criteria_passed=ledger.metadata.get("criteria_passed", 0),
        criteria_failed=ledger.metadata.get("criteria_failed", 0),
        criteria_unknown=ledger.metadata.get("criteria_unknown", 0),
        criteria_not_applicable=ledger.metadata.get("criteria_not_applicable", 0),
        category_coverage=ledger.metadata.get("category_coverage", {}),
        security_score=sec_score,
        security_tier=sec_tier,
        security_hygiene=sec_hygiene,
        indexability_matrix=ledger.metadata.get("indexability_matrix"),
        geo_dimensions=geo_dims
    )
