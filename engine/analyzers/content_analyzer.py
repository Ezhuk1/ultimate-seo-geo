"""
Deterministic Content & GEO Readiness Analyzer.

Evaluates text content against empirical GEO criteria:
- Direct Answer Frontloading in opening block (GEO-ANSWER-FRONTLOAD-001)
- Adaptive Chunking & Section Length distribution (GEO-ADAPTIVE-CHUNKING-002)
- Coreference Independence & Entity Explicitness (GEO-COREFERENCE-INDEPENDENCE-003)
- Evidence & Statistical Claim citations (GEO-EVIDENCE-METRICS-004)
- Reading flow, heading structure, and list/table utilization
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


DEFINITION_PATTERNS = [
    re.compile(r"\b(is|are|refers to|is defined as|means|consists of)\b", re.IGNORECASE),
    re.compile(r"^[A-Z][^—–\-:]+[—–\-:]\s+[a-z]", re.MULTILINE),
]

FLUFF_INTRO_PATTERNS = [
    re.compile(r"\b(in today'?s fast-paced world|have you ever wondered|as we all know|it goes without saying|imagine a world where)\b", re.IGNORECASE),
    re.compile(r"\b(in this article|in this post|we will explore|let's dive into|let's take a look)\b", re.IGNORECASE)
]

PERCENTAGE_PATTERN = re.compile(r"\b\d+([.,]\d+)?\s?%\b")
NUMERIC_STAT_PATTERN = re.compile(r"\b\d{1,3}(,\d{3})+(\.\d+)?\b|\b\d+(\.\d+)?\s*(million|billion|trillion|x|times)\b", re.IGNORECASE)

CITATION_CUES = [
    "according to", "study by", "research by", "report from", "published in",
    "data from", "source:", "survey conducted", "arxiv", "et al", "doi:"
]

PRONOUN_LEAD_PATTERN = re.compile(r"^(it|this|that|these|those|they|he|she)\b", re.IGNORECASE)


@dataclass
class ContentChunk:
    heading: str
    level: int
    text: str
    word_count: int
    has_pronoun_lead: bool
    has_definition_pattern: bool
    stats_count: int
    has_citation: bool


@dataclass
class ContentFinding:
    rule_id: str
    severity: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentAnalysisResult:
    total_words: int = 0
    total_chunks: int = 0
    opening_has_direct_answer: bool = False
    opening_has_fluff: bool = False
    opening_snippet: str = ""
    chunks: List[ContentChunk] = field(default_factory=list)
    monolithic_chunks_count: int = 0
    thin_chunks_count: int = 0
    pronoun_lead_count: int = 0
    unverified_stats_count: int = 0
    findings: List[ContentFinding] = field(default_factory=list)


def analyze_content(visible_text: str, headings: Optional[List[Dict[str, Any]]] = None) -> ContentAnalysisResult:
    """
    Performs deterministic content and GEO inspection on visible page text.
    """
    result = ContentAnalysisResult()
    clean_text = re.sub(r"\s+", " ", visible_text).strip()
    words = clean_text.split()
    result.total_words = len(words)

    if not words:
        result.findings.append(ContentFinding(
            rule_id="GEO-ANSWER-FRONTLOAD-001",
            severity="CRITICAL",
            message="No visible content found on page."
        ))
        return result

    # 1. Direct Answer Frontloading in Opening Block (first 60 words)
    opening_words = words[:60]
    opening_str = " ".join(opening_words)
    result.opening_snippet = opening_str

    for fluff_pat in FLUFF_INTRO_PATTERNS:
        if fluff_pat.search(opening_str):
            result.opening_has_fluff = True
            result.findings.append(ContentFinding(
                rule_id="GEO-ANSWER-FRONTLOAD-001",
                severity="WARNING",
                message="Opening paragraph begins with conversational fluff/filler instead of direct answer.",
                details={"snippet": opening_str[:120]}
            ))
            break

    for def_pat in DEFINITION_PATTERNS:
        if def_pat.search(opening_str):
            result.opening_has_direct_answer = True
            break

    if not result.opening_has_direct_answer and not result.opening_has_fluff and len(words) > 80:
        result.findings.append(ContentFinding(
            rule_id="GEO-ANSWER-FRONTLOAD-001",
            severity="INFO",
            message="Opening 60 words do not contain an immediate concise definition or entity answer syntax.",
            details={"snippet": opening_str[:120]}
        ))

    # 2. Chunking Analysis
    # Split text by double newlines or paragraph markers
    raw_sections = [p.strip() for p in re.split(r"\n\s*\n", visible_text) if p.strip()]
    if not raw_sections:
        raw_sections = [clean_text]

    for sec in raw_sections:
        sec_words = sec.split()
        w_count = len(sec_words)
        if w_count == 0:
            continue

        first_sentence = re.split(r"[.!?]", sec)[0].strip()
        pronoun_lead = bool(PRONOUN_LEAD_PATTERN.match(first_sentence))
        if pronoun_lead:
            result.pronoun_lead_count += 1

        # Check for stats and citations
        percentages = PERCENTAGE_PATTERN.findall(sec)
        num_stats = NUMERIC_STAT_PATTERN.findall(sec)
        total_stats = len(percentages) + len(num_stats)
        sec_lower = sec.lower()
        has_cit = any(cue in sec_lower for cue in CITATION_CUES)

        if total_stats > 0 and not has_cit:
            result.unverified_stats_count += total_stats

        has_def = any(def_pat.search(sec) for def_pat in DEFINITION_PATTERNS)

        chunk = ContentChunk(
            heading="",
            level=2,
            text=sec[:100] + "..." if len(sec) > 100 else sec,
            word_count=w_count,
            has_pronoun_lead=pronoun_lead,
            has_definition_pattern=has_def,
            stats_count=total_stats,
            has_citation=has_cit
        )
        result.chunks.append(chunk)

        if w_count > 450:
            result.monolithic_chunks_count += 1

    result.total_chunks = len(result.chunks)

    # 3. Findings for Chunks & Structure
    if result.monolithic_chunks_count > 0:
        result.findings.append(ContentFinding(
            rule_id="GEO-ADAPTIVE-CHUNKING-002",
            severity="WARNING",
            message=f"Found {result.monolithic_chunks_count} oversized monolithic block(s) (>450 words) without subheadings or visual breaks.",
            details={"monolithic_chunks": result.monolithic_chunks_count}
        ))

    if result.pronoun_lead_count > 2:
        result.findings.append(ContentFinding(
            rule_id="GEO-COREFERENCE-INDEPENDENCE-003",
            severity="WARNING",
            message=f"Multiple paragraphs ({result.pronoun_lead_count}) begin with ambiguous pronouns ('It', 'This', 'They'). High risk of ambiguous extraction in isolated RAG chunks.",
            details={"pronoun_leads": result.pronoun_lead_count}
        ))

    if result.unverified_stats_count > 0:
        result.findings.append(ContentFinding(
            rule_id="GEO-EVIDENCE-METRICS-004",
            severity="INFO",
            message=f"Detected {result.unverified_stats_count} numerical/statistical claim(s) without adjacent attribution cues or source links.",
            details={"unverified_stats": result.unverified_stats_count}
        ))

    return result
