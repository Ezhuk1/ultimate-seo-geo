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
STATUS_NOT_MEASURED = "NOT_MEASURED"


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
        evidence_snippet: Optional[str] = None
    ):
        self.evidence.append(EvidenceItem(
            rule_id=rule_id,
            category=category,
            title=title,
            status=status,
            confidence=confidence,
            observed=observed,
            expected=expected,
            message=message,
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
        impact_estimate: str
    ):
        finding_id = f"FND-{len(self.findings) + 1:03d}"
        self.findings.append(FindingItem(
            finding_id=finding_id,
            category=category,
            severity=severity,
            title=title,
            rule_id=rule_id,
            confidence=confidence,
            action_priority=action_priority,
            remediation_steps=remediation_steps,
            impact_estimate=impact_estimate
        ))

    def build(self, expected_baseline: Optional[int] = None) -> EvidenceLedger:
        # Calculate observation coverage against actual observed or expected baseline
        baseline = expected_baseline if expected_baseline is not None else len(self.signals)
        total_signals = max(len(self.signals), baseline)
        measured_signals = sum(1 for s in self.signals.values() if s.is_measured)
        coverage_pct = round((measured_signals / total_signals * 100), 1) if total_signals > 0 else 100.0

        metadata = {
            "engine_version": "2.0.0",
            "protocol": "Evidence-Ledger-v2",
            "target": self.target_url,
            "provenance_sha256": self.raw.provenance_hash,
            "generated_at": self.raw.timestamp_utc,
            "observation_coverage_percent": coverage_pct,
            "signals_total": total_signals,
            "signals_measured": measured_signals,
            "signals_unmeasured": total_signals - measured_signals,
        }

        ledger = EvidenceLedger(
            metadata=metadata,
            raw=self.raw,
            signals=self.signals,
            evidence=self.evidence,
            findings=self.findings,
            metrics={"coverage_pct": coverage_pct}
        )
        return ledger
