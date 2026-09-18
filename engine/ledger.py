"""
Evidence Ledger Protocol Implementation.

Coordinates the 4-layer audit pipeline:
RAW -> SIGNAL -> EVIDENCE -> FINDING

Enforces:
- Zero Fabrication & Provenance Tracking (SHA-256)
- 3 Confidence Levels (VERIFIED_FACT, HEURISTIC_ESTIMATE, UNVERIFIABLE_HYPOTHESIS)
- "Unknown != Failure" invariant
- Observation Coverage metric
"""

from __future__ import annotations
import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


CONFIDENCE_VERIFIED = "VERIFIED_FACT"
CONFIDENCE_HEURISTIC = "HEURISTIC_ESTIMATE"
CONFIDENCE_UNVERIFIABLE = "UNVERIFIABLE_HYPOTHESIS"

STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_CRITICAL = "CRITICAL"
STATUS_INFO = "INFO"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_NOT_MEASURED = "UNKNOWN"


@dataclass
class RawLayer:
    target_url: str
    provenance_hash: str
    timestamp_utc: str
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    content_type: Optional[str] = None
    raw_headers: Dict[str, str] = field(default_factory=dict)
    raw_html_sample: str = ""
    raw_robots_txt: Optional[str] = None


@dataclass
class SignalItem:
    signal_id: str
    name: str
    value: Any
    is_measured: bool = True
    unit: Optional[str] = None
    measurement_source: str = "deterministic_analyzer"


@dataclass
class EvidenceItem:
    rule_id: str
    category: str  # technical, schema, geo, performance
    title: str
    status: str    # PASS, WARNING, CRITICAL, INFO, NOT_MEASURED
    confidence: str # VERIFIED_FACT, HEURISTIC_ESTIMATE, UNVERIFIABLE_HYPOTHESIS
    observed: Any
    expected: Any
    message: str
    tier: str = ""
    evidence_snippet: Optional[str] = None


@dataclass
class FindingItem:
    finding_id: str
    category: str
    severity: str
    title: str
    rule_id: str
    confidence: str
    action_priority: str # P0_BLOCKER, P1_HIGH, P2_MEDIUM, P3_LOW, P4_MONITOR
    tier: str = ""
    remediation_steps: List[str] = field(default_factory=list)
    impact_estimate: str = ""


@dataclass
class EvidenceLedger:
    metadata: Dict[str, Any]
    raw: RawLayer
    signals: Dict[str, SignalItem] = field(default_factory=dict)
    evidence: List[EvidenceItem] = field(default_factory=list)
    findings: List[FindingItem] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


EXPECTED_BASELINE_SIGNALS = 16


class LedgerBuilder:
    """Builder for assembling deterministic inspection ledgers."""

    def __init__(self, target_url: str):
        self.target_url = target_url
        self.raw = RawLayer(
            target_url=target_url,
            provenance_hash="",
            timestamp_utc=datetime.now(timezone.utc).isoformat()
        )
        self.signals: Dict[str, SignalItem] = {}
        self.evidence: List[EvidenceItem] = []
        self.findings: List[FindingItem] = []
        self.metadata: Dict[str, Any] = {}

    def set_raw(self, status_code: int, headers: Dict[str, str], body_text: str, response_time_ms: float, robots_txt: Optional[str] = None):
        h = hashlib.sha256(body_text.encode("utf-8", errors="replace")).hexdigest()
        self.raw.provenance_hash = h
        self.raw.status_code = status_code
        self.raw.response_time_ms = response_time_ms
        self.raw.content_type = headers.get("content-type", "")
        self.raw.raw_headers = headers
        self.raw.raw_html_sample = body_text[:500]
        self.raw.raw_robots_txt = robots_txt

    def add_signal(self, signal_id: str, name: str, value: Any, is_measured: bool = True, unit: Optional[str] = None, source: str = "deterministic_analyzer"):
        self.signals[signal_id] = SignalItem(
            signal_id=signal_id,
            name=name,
            value=value,
            is_measured=is_measured,
            unit=unit,
            measurement_source=source
        )

    def add_evidence(
        self,
        rule_id: str,
        category: str,
        title: str,
        status: str,
        confidence: str,
        observed: Any,
        expected: Any,
        message: str,
        evidence_snippet: Optional[str] = None,
        tier: Optional[str] = None
    ):
        if not tier:
            try:
                from .rules import get_rule_registry
                r_def = get_rule_registry().get(rule_id)
                if r_def and r_def.tier:
                    tier = r_def.tier
            except Exception:
                pass
        self.evidence.append(EvidenceItem(
            rule_id=rule_id,
            category=category,
            title=title,
            status=status,
            confidence=confidence,
            observed=observed,
            expected=expected,
            message=message,
            tier=tier or "",
            evidence_snippet=evidence_snippet
        ))

    def add_finding(
        self,
        rule_id: str,
        category: str,
        severity: str,
        title: str,
        confidence: str,
        action_priority: str,
        remediation_steps: List[str],
        impact_estimate: str,
        tier: Optional[str] = None
    ):
        if not tier:
            try:
                from .rules import get_rule_registry
                r_def = get_rule_registry().get(rule_id)
                if r_def and r_def.tier:
                    tier = r_def.tier
            except Exception:
                pass
        finding_id = f"FND-{len(self.findings) + 1:03d}"
        self.findings.append(FindingItem(
            finding_id=finding_id,
            category=category,
            severity=severity,
            title=title,
            rule_id=rule_id,
            confidence=confidence,
            action_priority=action_priority,
            tier=tier or "",
            remediation_steps=remediation_steps,
            impact_estimate=impact_estimate
        ))

    def build(self, expected_baseline: Optional[int] = None) -> EvidenceLedger:
        # Calculate signal coverage for backwards-compatibility
        baseline_signals = expected_baseline if expected_baseline is not None else len(self.signals)
        total_signals = max(len(self.signals), baseline_signals)
        measured_signals = sum(1 for s in self.signals.values() if s.is_measured)
        signals_coverage_pct = round((measured_signals / total_signals * 100), 1) if total_signals > 0 else 100.0

        # Calculate criteria-based coverage from evidence
        criteria_passed = 0
        criteria_failed = 0
        criteria_observed = 0
        criteria_unknown = 0
        criteria_not_applicable = 0
        cat_stats: Dict[str, Dict[str, int]] = {}

        for ev in self.evidence:
            cat = ev.category or "technical"
            if cat not in cat_stats:
                cat_stats[cat] = {"total": 0, "observed": 0, "passed": 0, "failed": 0, "unknown": 0, "not_applicable": 0}

            if ev.status == STATUS_PASS:
                criteria_passed += 1
                criteria_observed += 1
                cat_stats[cat]["passed"] += 1
                cat_stats[cat]["observed"] += 1
            elif ev.status in (STATUS_WARNING, STATUS_CRITICAL):
                criteria_failed += 1
                criteria_observed += 1
                cat_stats[cat]["failed"] += 1
                cat_stats[cat]["observed"] += 1
            elif ev.status == STATUS_INFO:
                criteria_observed += 1
                cat_stats[cat]["observed"] += 1
            elif ev.status in (STATUS_UNKNOWN, "NOT_MEASURED"):
                criteria_unknown += 1
                cat_stats[cat]["unknown"] += 1
            elif ev.status == STATUS_NOT_APPLICABLE:
                criteria_not_applicable += 1
                cat_stats[cat]["not_applicable"] += 1

        applicable_criteria = criteria_observed + criteria_unknown
        baseline_criteria = expected_baseline if expected_baseline is not None else 0
        criteria_total = max(applicable_criteria, baseline_criteria)
        if criteria_total > applicable_criteria:
            criteria_unknown += (criteria_total - applicable_criteria)

        coverage_pct = round((criteria_observed / criteria_total * 100), 1) if criteria_total > 0 else 100.0

        category_coverage: Dict[str, Dict[str, Any]] = {}
        for cat, s in cat_stats.items():
            cat_applicable = s["observed"] + s["unknown"]
            cat_pct = round((s["observed"] / cat_applicable * 100), 1) if cat_applicable > 0 else 100.0
            category_coverage[cat] = {
                "total": cat_applicable,
                "observed": s["observed"],
                "passed": s["passed"],
                "failed": s["failed"],
                "unknown": s["unknown"],
                "not_applicable": s["not_applicable"],
                "coverage_pct": cat_pct,
            }

        metadata = {
            "engine_version": "3.1.0",
            "protocol": "Evidence-Ledger-v2",
            "target": self.target_url,
            "provenance_sha256": self.raw.provenance_hash,
            "generated_at": self.raw.timestamp_utc,
            "observation_coverage_percent": coverage_pct,
            "criteria_total": criteria_total,
            "criteria_observed": criteria_observed,
            "criteria_passed": criteria_passed,
            "criteria_failed": criteria_failed,
            "criteria_unknown": criteria_unknown,
            "criteria_not_applicable": criteria_not_applicable,
            "category_coverage": category_coverage,
            "signals_total": total_signals,
            "signals_measured": measured_signals,
            "signals_unmeasured": total_signals - measured_signals,
            "signals_coverage_percent": signals_coverage_pct,
        }
        metadata.update(self.metadata)

        ledger = EvidenceLedger(
            metadata=metadata,
            raw=self.raw,
            signals=self.signals,
            evidence=self.evidence,
            findings=self.findings,
            metrics={
                "coverage_pct": coverage_pct,
                "criteria_total": criteria_total,
                "criteria_observed": criteria_observed,
                "criteria_passed": criteria_passed,
                "criteria_failed": criteria_failed,
                "criteria_unknown": criteria_unknown,
                "criteria_not_applicable": criteria_not_applicable,
                "category_coverage": category_coverage
            }
        )
        return ledger

