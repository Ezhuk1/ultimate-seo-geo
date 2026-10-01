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
    re.compile(r"\b(?:is\s+(?:a|an|the|defined\s+as|known\s+as|classified\s+as)|are\s+(?:the|a|structured|defined)|refers\s+to|means|consists\s+of|гэта|это|является|з['’]?яўляецца|уяўляе\s+сабой|представляет\s+собой)\b", re.IGNORECASE),
    re.compile(r"^[A-Za-zА-Яа-яЁёІіЎўЇїЄє][^—–\-:]+[—–\-:]\s+[A-Za-zА-Яа-яЁёІіЎўЇїЄє]", re.MULTILINE),
]

FLUFF_INTRO_PATTERNS = [
    re.compile(r"\b(in today'?s fast-paced world|have you ever wondered|as we all know|it goes without saying|imagine a world where)\b", re.IGNORECASE),
    re.compile(r"\b(in this article|in this post|we will explore|let's dive into|let's take a look)\b", re.IGNORECASE),
    re.compile(r"\b(в современном мире|в этой статье|в этой публикации|как известно|ни для кого не секрет|давайте разберемся|сегодня мы поговорим|никому не секрет)\b", re.IGNORECASE),
]

PERCENTAGE_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s?%")
NUMERIC_STAT_PATTERN = re.compile(r"\b\d{1,3}(,\d{3})+(\.\d+)?\b|\b\d{1,3}( \d{3})+\b|\b\d+(\.\d+)?\s*(million|billion|trillion|x|times)\b", re.IGNORECASE)

CITATION_CUES = [
    "according to", "study by", "research by", "report from", "published in",
    "data from", "source:", "survey conducted", "arxiv", "et al", "doi:", "rfc",
    "согласно", "исследование", "по данным", "источник:", "отчет",
    "паводле", "па дадзеных", "дадзеныя", "стандарт", "ietf"
]

PRONOUN_LEAD_PATTERN = re.compile(r"^(it|this|that|these|those|they|he|she|это|он|она|оно|они|данный|эта|тот|эти|тех)\b", re.IGNORECASE)

UNSUPPORTED_SUPERLATIVES = [
    "best in class", "industry-leading", "world's best", "unmatched quality",
    "revolutionary", "game-changing", "market leader", "ultimate solution",
    "cutting-edge", "unrivaled", "лучший в мире", "непревзойденный", "революционный"
]

INTENT_KEYWORDS = {
    "TRANSACTIONAL": ["buy", "order", "purchase", "pricing", "price", "subscribe", "checkout", "discount", "купить", "заказать", "цена", "стоимость", "тариф"],
    "COMMERCIAL": ["best", "top", "review", "vs", "comparison", "alternatives", "features", "лучший", "топ", "обзор", "сравнение", "рейтинг"],
    "NAVIGATIONAL": ["login", "sign in", "sign up", "contact us", "about us", "portal", "войти", "контакты", "о нас", "личный кабинет"],
    "INFORMATIONAL": ["how to", "guide", "what is", "tutorial", "why", "explain", "overview", "definition", "как", "что такое", "руководство", "инструкция"]
}


import math

QUESTION_HEADING_PATTERN = re.compile(
    r"^(\s*(what|how|why|who|when|where|which|can|is|are|does|do|как|что|почему|зачем|где|кто|когда|какой|каковы|як|чаму|ці)\b|.*\?\s*$)",
    re.IGNORECASE
)


@dataclass
class PawcAnalysisResult:
    score: int = 0
    opening_evidence_weight: float = 0.0
    heading_answer_weight: float = 0.0
    sentences_count: int = 0
    decay_alpha: float = 1.0
    top_sentences: List[Dict[str, Any]] = field(default_factory=list)


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
    search_intent: str = "INFORMATIONAL"
    evidence_density_score: int = 0
    unsupported_superlatives: List[str] = field(default_factory=list)
    fluff_count: int = 0
    is_thin_content: bool = False
    pawc: PawcAnalysisResult = field(default_factory=PawcAnalysisResult)
    question_headings_count: int = 0
    question_answers_count: int = 0
    findings: List[ContentFinding] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def compute_pawc(
    visible_text: str,
    headings: Optional[List[Dict[str, Any]]] = None,
    alpha: float = 1.0
) -> PawcAnalysisResult:
    """
    Computes Position-Adjusted Word Count / Weighting (PAWC) per Princeton KDD 2024.
    Weights factual definitions, empirical statistics, and authoritative citations
    exponentially higher when placed in early positions (W = F * exp(-alpha * (pos / N))).
    """
    res = PawcAnalysisResult()
    raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", visible_text) if len(s.strip().split()) >= 3]
    N = len(raw_sentences)
    res.sentences_count = N
    if N == 0:
        return res

    heading_texts = {h.get("text", "").strip().lower() for h in (headings or []) if h.get("text")}

    total_weighted_points = 0.0
    ideal_max_points = 0.0
    opening_pts = 0.0
    heading_pts = 0.0

    for i, sent in enumerate(raw_sentences):
        pos_ratio = i / float(N)
        decay = math.exp(-alpha * pos_ratio)

        features = 0.0
        sent_lower = sent.lower()

        # 1. Definition syntax
        if any(p.search(sent) for p in DEFINITION_PATTERNS):
            features += 2.5
        # 2. Empirical statistics
        if PERCENTAGE_PATTERN.search(sent) or NUMERIC_STAT_PATTERN.search(sent):
            features += 2.0
        # 3. Citation cues
        if any(cue in sent_lower for cue in CITATION_CUES):
            features += 2.5
        # 4. Heading proximity
        is_hdg_adjacent = (i == 0) or any(sent_lower.startswith(ht[:20]) for ht in heading_texts if len(ht) >= 5)
        if is_hdg_adjacent:
            features += 1.5

        if features > 0:
            weighted = features * decay
            total_weighted_points += weighted
            if i < 3:
                opening_pts += weighted
            if is_hdg_adjacent:
                heading_pts += weighted
            if len(res.top_sentences) < 5:
                res.top_sentences.append({
                    "sentence": sent[:100] + ("..." if len(sent) > 100 else ""),
                    "position": i,
                    "decay": round(decay, 3),
                    "score": round(weighted, 2)
                })

        ideal_max_points += 3.0 * math.exp(-alpha * (min(i, 4) / float(N)))

    res.opening_evidence_weight = round(opening_pts, 2)
    res.heading_answer_weight = round(heading_pts, 2)

    raw_norm = (total_weighted_points / max(1.0, ideal_max_points)) * 100.0
    if opening_pts > 2.0:
        raw_norm += 15.0
    res.score = min(100, max(0, int(round(raw_norm))))
    return res


def analyze_content(
    visible_text: str,
    headings: Optional[List[Dict[str, Any]]] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    extractable_elements: Optional[Dict[str, Any]] = None,
    content_ratio: Optional[Dict[str, Any]] = None,
    schema_entities: Optional[List[Dict[str, Any]]] = None,
    links: Optional[List[Dict[str, Any]]] = None
) -> ContentAnalysisResult:
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

    # Compute PAWC Positional Weighting
    result.pawc = compute_pawc(visible_text, headings)

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

    if len(words) >= 25:
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

        sentences = [s.strip() for s in re.split(r"[.!?]", sec) if s.strip()]
        pronoun_lead = any(bool(PRONOUN_LEAD_PATTERN.match(s)) for s in sentences[:2])
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

    # 4. Search Intent Detection
    lower_text = clean_text.lower()
    text_for_intent = (clean_text + " " + (title or "") + " " + (description or "")).lower()
    intent_scores = {k: 0 for k in INTENT_KEYWORDS}
    for intent, kw_list in INTENT_KEYWORDS.items():
        for kw in kw_list:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_for_intent):
                intent_scores[intent] += 1
    best_intent = max(intent_scores.items(), key=lambda x: x[1])
    result.search_intent = best_intent[0] if best_intent[1] > 0 else "INFORMATIONAL"

    # 5. Evidence Density Score
    citations_found = sum(1 for cue in CITATION_CUES if cue in lower_text)
    stats_found = len(PERCENTAGE_PATTERN.findall(clean_text)) + len(NUMERIC_STAT_PATTERN.findall(clean_text))
    raw_ev_pts = (citations_found * 20) + (min(stats_found, 5) * 12)
    result.evidence_density_score = min(100, raw_ev_pts)

    # 6. Fluff & Unsupported Superlatives
    common_fluff = ["game-changing", "revolutionary", "world-class", "seamless", "next-generation", "best-of-breed", "synergy", "cutting-edge"]
    fluff_found = sum(1 for fw in common_fluff if fw in lower_text)

    for sup in UNSUPPORTED_SUPERLATIVES:
        if re.search(r'\b' + re.escape(sup) + r'\b', lower_text):
            result.unsupported_superlatives.append(sup)

    result.fluff_count = fluff_found + len(result.unsupported_superlatives)

    if result.unsupported_superlatives:
        result.findings.append(ContentFinding(
            rule_id="GEO-EVIDENCE-METRICS-004",
            severity="INFO",
            message=f"Detected unsupported subjective superlative claim(s): {', '.join(result.unsupported_superlatives[:3])}. Support assertions with empirical metrics.",
            details={"superlatives": result.unsupported_superlatives}
        ))

    # 7. Thin Content Check
    if result.total_words < 150:
        result.is_thin_content = True
        result.findings.append(ContentFinding(
            rule_id="GEO-ADAPTIVE-CHUNKING-002",
            severity="WARNING" if result.total_words < 25 else "INFO",
            message=f"Page has thin content ({result.total_words} words). Search engines and AI retrieval bots may consider it low utility.",
            details={"word_count": result.total_words}
        ))

    # 8. Question Headings & Direct Answer Architecture (CONTENT-QUESTION-HEADINGS-002)
    if headings:
        q_headings = [h for h in headings if QUESTION_HEADING_PATTERN.search(h.get("text", ""))]
        result.question_headings_count = len(q_headings)
        if q_headings:
            answered_count = 0
            for qh in q_headings:
                qh_text = qh.get("text", "").lower()
                for chk in result.chunks:
                    if chk.heading.lower() == qh_text or chk.text.lower().startswith(qh_text[:20]):
                        if chk.word_count <= 80 and (chk.has_definition_pattern or not chk.has_pronoun_lead):
                            answered_count += 1
                            break
            result.question_answers_count = max(1, answered_count) if result.opening_has_direct_answer else answered_count

    # 9. Structured Extractable Elements (CONTENT-EXTRACTABLE-003)
    if extractable_elements:
        tables = extractable_elements.get("tables_count", 0)
        lists = extractable_elements.get("lists_count", 0)
        tldr = extractable_elements.get("tldr_blocks_count", 0)
        dl = extractable_elements.get("definition_lists_count", 0)
        has_extractable = (tables > 0 or lists > 0 or tldr > 0 or dl > 0)
        if not has_extractable and result.total_words >= 300:
            result.findings.append(ContentFinding(
                rule_id="CONTENT-EXTRACTABLE-003",
                severity="INFO",
                message="Page contains >=300 words but lacks structured comparison tables, bulleted lists, or TL;DR summary blocks.",
                details={"tables": tables, "lists": lists, "tldr": tldr}
            ))

    # 10. Content-to-Boilerplate Ratio (CONTENT-TEXT-RATIO-004)
    if content_ratio:
        tot_w = content_ratio.get("total_words", 0)
        ratio = content_ratio.get("ratio", 1.0)
        if tot_w >= 300 and ratio < 0.20:
            result.findings.append(ContentFinding(
                rule_id="CONTENT-TEXT-RATIO-004",
                severity="WARNING",
                message=f"Substantive main content ratio ({int(ratio*100)}%) is below recommended 20% threshold. Page template is dominated by boilerplate header/nav/footer.",
                details={"ratio": ratio, "total_words": tot_w}
            ))

    # 11. Schema Date Visible Parity (CONTENT-DATE-VISIBLE-005)
    if schema_entities:
        for ent in schema_entities:
            if isinstance(ent, dict):
                d_pub = ent.get("datePublished")
                d_mod = ent.get("dateModified")
                for d_val in (d_pub, d_mod):
                    if d_val and isinstance(d_val, str) and len(d_val) >= 4:
                        year = d_val[:4]
                        if year.isdigit() and int(year) >= 2000 and year not in clean_text:
                            result.findings.append(ContentFinding(
                                rule_id="CONTENT-DATE-VISIBLE-005",
                                severity="WARNING",
                                message=f"Schema declares publication/modification date '{d_val}', but year '{year}' is not visibly rendered in document body.",
                                details={"schema_date": d_val}
                            ))
                            break

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Round-4 GEO additions: section-level inverted pyramid + information gain.
# Both are Tier E heuristics (RU/EN) and never gate scores on their own.
# ─────────────────────────────────────────────────────────────────────────────

WATER_PHRASES = [
    "in today's fast-paced world", "in the modern digital landscape",
    "in the ever-evolving world", "digital landscape",
    "never been more important", "more important than ever",
    "в современном мире", "в современном быстро меняющемся мире",
    "цифровом ландшафте", "как никогда ранее", "на сегодняшний день играют важную роль",
    "трудно переоценить",
]

INFO_GAIN_TRIGGER_PATTERNS = [
    re.compile(r"\b(we|our team|our lab)\b[^.?!]{0,120}?\b\d+([.,]\d+)?\s?(%|percent|ms|seconds|users|requests)", re.IGNORECASE),
    re.compile(r"\b(мы|наш\w*)\b[^.?!]{0,120}?\b\d+([.,]\d+)?\s?(%|процент\w*|млн|тыс|мс|пользовател\w+)", re.IGNORECASE),
    re.compile(r"\b(we tested|we measured|we benchmarked|case study|our experiment|in production we)\b", re.IGNORECASE),
    re.compile(r"\b(мы протестировали|мы измерили|мы внедрили|наш эксперимент|кейс|бенчмарк)\b", re.IGNORECASE),
    re.compile(r"[=≈]\s*\d+"),
    re.compile(r"\b(source code|open[- ]sourced|github\.com/[^\s]+|according to our telemetry)\b", re.IGNORECASE),
]


def analyze_section_pyramid(
    visible_text: str,
    headings: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Per H2/H3 section: does the first ~55 words carry substance (stat,
    definition or citation cue)? Inverted-pyramid heuristic for LLM chunking."""
    headings = headings or []
    section_heads = [h for h in headings if int(h.get("level", 9)) in (2, 3) and h.get("text")]
    if not section_heads:
        return {"sections_total": 0, "sections_frontloaded": 0, "ratio_pct": None,
                "weak_sections": [], "applicable": False}

    text = visible_text or ""
    sections: List[Dict[str, Any]] = []
    for i, h in enumerate(section_heads):
        start = text.find(h["text"])
        if start == -1:
            continue
        start += len(h["text"])
        end = len(text)
        for nxt in section_heads[i + 1:]:
            npos = text.find(nxt["text"], start)
            if npos != -1:
                end = min(end, npos)
        body = text[start:end].strip()
        if len(body.split()) >= 60:
            sections.append({"title": h["text"][:80], "body": body})

    frontloaded = 0
    weak: List[str] = []
    for sec in sections:
        head_words = " ".join(sec["body"].split()[:55])
        has_stat = bool(PERCENTAGE_PATTERN.search(head_words) or NUMERIC_STAT_PATTERN.search(head_words))
        has_def = any(p.search(head_words) for p in DEFINITION_PATTERNS)
        has_cite = any(cue in head_words.lower() for cue in CITATION_CUES)
        if has_stat or has_def or has_cite:
            frontloaded += 1
        else:
            weak.append(sec["title"])
    total = len(sections)
    return {"sections_total": total, "sections_frontloaded": frontloaded,
            "ratio_pct": round(frontloaded / total * 100.0, 1) if total else None,
            "weak_sections": weak[:5], "applicable": total >= 2}


def analyze_information_gain(visible_text: str) -> Dict[str, Any]:
    """Weak-signal heuristics for information gain: originality triggers
    (first-person results, benchmarks, formulas, artifacts) vs boilerplate
    'water' openers that AI crawlers discard as noise."""
    text = visible_text or ""
    triggers: List[str] = []
    for pat in INFO_GAIN_TRIGGER_PATTERNS:
        m = pat.search(text)
        if m:
            triggers.append(m.group(0)[:80])
    water = [w for w in WATER_PHRASES if w in text.lower()]
    return {"trigger_count": len(set(triggers)), "triggers": list(dict.fromkeys(triggers))[:5],
            "water_phrases": water[:5], "applicable": len(text.split()) >= 300}
