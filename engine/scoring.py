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

    # 2. GEO Readiness Index
    content_signal = ledger.signals.get("content_total_words")
    status_signal = ledger.signals.get("http_status_code")
    has_error = bool(status_signal and status_signal.value and status_signal.value >= 400)
    has_no_content = bool(content_signal is not None and content_signal.value == 0)

    if has_error or has_no_content:
        geo_score = 0
    else:
        geo_score = 0
        geo_rule_ids = [
            "GEO-ANSWER-FRONTLOAD-001",
            "GEO-ADAPTIVE-CHUNKING-002",
            "GEO-COREFERENCE-INDEPENDENCE-003",
            "SCHEMA-GRAPH-INTERCONNECT-002"
        ]
        for r_id in geo_rule_ids:
            rule = registry.get(r_id)
            points_map = rule.geo_points if rule and rule.geo_points else {"pass": 25, "warning": 10, "neutral": 15}
            ev = next((e for e in ledger.evidence if e.rule_id == r_id), None)
            if ev:
                if ev.status == STATUS_PASS:
                    geo_score += points_map.get("pass", 25)
                elif ev.status == STATUS_WARNING:
                    geo_score += points_map.get("warning", 10)
            else:
                if r_id == "SCHEMA-GRAPH-INTERCONNECT-002":
                    schema_ent = ledger.signals.get("schema_entity_count")
                    if schema_ent and schema_ent.value > 0:
                        geo_score += points_map.get("neutral", 15)
                else:
                    geo_score += points_map.get("neutral", 15)

    geo_score = max(0, min(100, geo_score))

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
        indexability_matrix=ledger.metadata.get("indexability_matrix")
    )
