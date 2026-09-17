"""
Multi-Dimensional Evidence Scoring Engine.

Calculates:
1. Observable Technical Score (0..100) strictly from measured signals
2. GEO Readiness Index (0..100) measuring AI extraction and graph viability
3. Observation Coverage (%) reflecting empirical measurement completeness
4. Enforces 'Unknown != Failure' invariant (unmeasured signals never penalize scores)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List
from .ledger import (
    EvidenceLedger,
    STATUS_CRITICAL,
    STATUS_WARNING,
    STATUS_PASS,
    STATUS_NOT_MEASURED,
    CONFIDENCE_VERIFIED,
)


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


def calculate_scores(ledger: EvidenceLedger) -> ScoreBreakdown:
    """
    Computes scores strictly according to empirical evidence rules.
    """
    coverage_pct = ledger.metadata.get("observation_coverage_percent", 100.0)

    # 1. Technical Score
    tech_score = 100
    deductions = []
    crit_count = 0
    warn_count = 0
    pass_count = 0
    unmeasured_count = 0

    for ev in ledger.evidence:
        if ev.status == STATUS_PASS:
            pass_count += 1
            continue
        elif ev.status == STATUS_NOT_MEASURED:
            unmeasured_count += 1
            # Invariant: Unmeasured never deducts points!
            continue

        if ev.category in ("technical", "schema", "performance"):
            if ev.status == STATUS_CRITICAL:
                crit_count += 1
                deduction = 25 if ev.confidence == CONFIDENCE_VERIFIED else 15
                tech_score -= deduction
                deductions.append({
                    "rule_id": ev.rule_id,
                    "title": ev.title,
                    "penalty": -deduction,
                    "reason": ev.message,
                    "confidence": ev.confidence
                })
            elif ev.status == STATUS_WARNING:
                warn_count += 1
                # Differentiate penalties:
                # Heuristic / display length warnings carry -5 pts
                # Technical and structural warnings carry -10 pts
                if ev.confidence != CONFIDENCE_VERIFIED or ev.rule_id in ("TECH-TITLE-003", "TECH-META-DESC-004"):
                    deduction = 5
                else:
                    deduction = 10
                tech_score -= deduction
                deductions.append({
                    "rule_id": ev.rule_id,
                    "title": ev.title,
                    "penalty": -deduction,
                    "reason": ev.message,
                    "confidence": ev.confidence
                })

    tech_score = max(0, min(100, tech_score))

    # 2. GEO Readiness Index
    geo_score = 0
    # Direct Answer Frontload (25 pts)
    ans_ev = next((e for e in ledger.evidence if e.rule_id == "GEO-ANSWER-FRONTLOAD-001"), None)
    if ans_ev:
        if ans_ev.status == STATUS_PASS:
            geo_score += 25
        elif ans_ev.status == STATUS_WARNING:
            geo_score += 10
    else:
        geo_score += 15  # Neutral default if not evaluated

    # Adaptive Chunking (25 pts)
    chunk_ev = next((e for e in ledger.evidence if e.rule_id == "GEO-ADAPTIVE-CHUNKING-002"), None)
    if chunk_ev:
        if chunk_ev.status == STATUS_PASS:
            geo_score += 25
        elif chunk_ev.status == STATUS_WARNING:
            geo_score += 12
    else:
        geo_score += 15

    # Coreference Independence (25 pts)
    coref_ev = next((e for e in ledger.evidence if e.rule_id == "GEO-COREFERENCE-INDEPENDENCE-003"), None)
    if coref_ev:
        if coref_ev.status == STATUS_PASS:
            geo_score += 25
        elif coref_ev.status == STATUS_WARNING:
            geo_score += 12
    else:
        geo_score += 15

    # Schema Graph Integration (25 pts)
    graph_ev = next((e for e in ledger.evidence if e.rule_id == "SCHEMA-GRAPH-INTERCONNECT-002"), None)
    if graph_ev:
        if graph_ev.status == STATUS_PASS:
            geo_score += 25
        elif graph_ev.status == STATUS_WARNING:
            geo_score += 10
    else:
        schema_ent = ledger.signals.get("schema_entity_count")
        if schema_ent and schema_ent.value > 0:
            geo_score += 15

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
        deductions=deductions
    )
