"""
Deterministic E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness) Analyzer.

Evaluates:
- Author identity & author biography
- Author authority verification via sameAs links (Wikidata, ORCID, LinkedIn, Google Scholar)
- Organization publishing credentials and Contact/About accessibility
- Editorial policy, corrections, and fact-checking disclosures
- YMYL (Your Money or Your Life) risk detection and appropriate disclaimers
- First-hand experience signals (hands-on testing, original research, empirical benchmarking)
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set


TRUSTED_AUTHORITY_DOMAINS = [
    "wikidata.org", "wikipedia.org", "orcid.org", "scholar.google.com",
    "linkedin.com", "github.com", "researchgate.net", "crunchbase.com"
]

YMYL_KEYWORDS = [
    "investment", "crypto", "medical advice", "symptoms", "diagnosis",
    "treatment", "loan", "mortgage", "credit card", "banking", "legal advice",
    "tax advice", "health insurance", "pharmacy", "medication", "cure",
    "инвестиции", "кредит", "лечение", "симптомы", "диагноз", "юридическая консультация"
]

DISCLAIMER_PATTERNS = [
    re.compile(r"\b(disclaimer|terms of use|not financial advice|not medical advice|consult your physician|consult a professional|disclaimer:|отказ от ответственности|не является финансовой рекомендацией)\b", re.IGNORECASE),
    re.compile(r"\b(for informational purposes only|educational purposes only|не является индивидуальной инвестиционной рекомендацией)\b", re.IGNORECASE)
]

FIRST_HAND_EXPERIENCE_PATTERNS = [
    re.compile(r"\b(in our testing|we tested|we evaluated|in our benchmarks?|our hands-on|we measured|we deployed|our audit of|we analyzed|in our experiment|в наших тестах|мы протестировали|мы измерили|наш опыт)\b", re.IGNORECASE),
    re.compile(r"\b(after \d+ (?:months?|weeks?|days?|hours?) of (?:testing|using|deploying|running))\b", re.IGNORECASE)
]


@dataclass
class EeatFinding:
    rule_id: str
    severity: str  # CRITICAL, WARNING, INFO, PASS
    message: str
    dimension: str  # Experience, Expertise, Authoritativeness, Trust
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EeatAnalysisResult:
    has_author: bool = False
    author_name: str = ""
    has_author_bio: bool = False
    author_same_as: List[str] = field(default_factory=list)
    has_trusted_authority_profile: bool = False
    has_organization: bool = False
    organization_name: str = ""
    has_contact_page: bool = False
    has_about_page: bool = False
    has_editorial_policy: bool = False
    is_ymyl_content: bool = False
    has_ymyl_disclaimer: bool = False
    first_hand_experience_count: int = 0
    experience_snippets: List[str] = field(default_factory=list)
    eeat_score: int = 0  # 0..100
    findings: List[EeatFinding] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_author": self.has_author,
            "author_name": self.author_name,
            "has_author_bio": self.has_author_bio,
            "author_same_as": self.author_same_as,
            "has_trusted_authority_profile": self.has_trusted_authority_profile,
            "has_organization": self.has_organization,
            "organization_name": self.organization_name,
            "has_contact_page": self.has_contact_page,
            "has_about_page": self.has_about_page,
            "has_editorial_policy": self.has_editorial_policy,
            "is_ymyl_content": self.is_ymyl_content,
            "has_ymyl_disclaimer": self.has_ymyl_disclaimer,
            "first_hand_experience_count": self.first_hand_experience_count,
            "eeat_score": self.eeat_score,
            "findings_count": len(self.findings)
        }


def analyze_eeat(
    visible_text: str,
    schema_entities: Optional[List[Dict[str, Any]]] = None,
    links: Optional[List[Dict[str, Any]]] = None
) -> EeatAnalysisResult:
    """
    Performs deterministic evaluation of E-E-A-T and transparency signals.
    """
    result = EeatAnalysisResult()
    lower_text = visible_text.lower() if visible_text else ""
    schema_entities = schema_entities or []
    links = links or []

    # 1. Author Identification (from Schema or text patterns)
    authors: List[Dict[str, Any]] = []
    for ent in schema_entities:
        t = ent.get("@type")
        if t == "Person":
            authors.append(ent)
        elif isinstance(ent.get("author"), dict):
            authors.append(ent["author"])
        elif isinstance(ent.get("author"), list):
            for a in ent["author"]:
                if isinstance(a, dict):
                    authors.append(a)

    if authors:
        result.has_author = True
        first_auth = authors[0]
        result.author_name = str(first_auth.get("name", "")).strip()
        bio = first_auth.get("description") or first_auth.get("disambiguatingDescription") or ""
        result.has_author_bio = bool(len(bio.strip()) > 10)

        # Collect sameAs
        same_as = first_auth.get("sameAs", [])
        if isinstance(same_as, str):
            same_as = [same_as]
        elif isinstance(same_as, list):
            same_as = [str(s) for s in same_as]
        result.author_same_as = same_as

        for p in same_as:
            if any(dom in p.lower() for dom in TRUSTED_AUTHORITY_DOMAINS):
                result.has_trusted_authority_profile = True
                break
    else:
        # Check text cues for author byline
        byline_match = re.search(r'\b(?:written by|author|by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', visible_text or "")
        if byline_match:
            result.has_author = True
            result.author_name = byline_match.group(1).strip()

    # 2. Organization Identification
    for ent in schema_entities:
        t = ent.get("@type")
        if t in ("Organization", "Corporation", "LocalBusiness"):
            result.has_organization = True
            result.organization_name = str(ent.get("name", "")).strip()
            break
        elif isinstance(ent.get("publisher"), dict):
            result.has_organization = True
            result.organization_name = str(ent["publisher"].get("name", "")).strip()
            break

    # 3. Transparency Pages (Contact, About, Editorial Policy)
    for lk in links:
        href = str(lk.get("href", "")).lower()
        txt = str(lk.get("text", "")).lower()
        comb = f"{href} {txt}"

        if any(c in comb for c in ("/contact", "contact us", "контакты", "связаться")):
            result.has_contact_page = True
        if any(a in comb for a in ("/about", "about us", "about-us", "о нас", "о компании")):
            result.has_about_page = True
        if any(e in comb for e in ("/editorial", "editorial policy", "corrections", "fact-check", "редакционная политика")):
            result.has_editorial_policy = True

    # 4. YMYL & Disclaimers
    ymyl_hits = [kw for kw in YMYL_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', lower_text)]
    strong_ymyl = {"medical advice", "legal advice", "tax advice", "investment", "financial advice", "лечение", "симптомы"}
    if len(ymyl_hits) >= 2 or any(h in strong_ymyl for h in ymyl_hits):
        result.is_ymyl_content = True

    for disc_pat in DISCLAIMER_PATTERNS:
        if disc_pat.search(visible_text or ""):
            result.has_ymyl_disclaimer = True
            break

    # 5. First-Hand Experience Signals
    for exp_pat in FIRST_HAND_EXPERIENCE_PATTERNS:
        for match in exp_pat.finditer(visible_text or ""):
            result.first_hand_experience_count += 1
            if len(result.experience_snippets) < 3:
                snippet_start = max(0, match.start() - 20)
                snippet_end = min(len(visible_text), match.end() + 60)
                result.experience_snippets.append(visible_text[snippet_start:snippet_end].strip())

    # 6. Scoring & Findings Generation
    score = 0
    # Author & Bio (25 pts)
    if result.has_author:
        score += 15
        if result.has_author_bio or result.has_trusted_authority_profile:
            score += 10
            result.findings.append(EeatFinding(
                rule_id="EEAT-AUTHOR-001",
                severity="PASS",
                message=f"Verified author '{result.author_name}' with explicit background/authority profile.",
                dimension="Expertise"
            ))
        else:
            result.findings.append(EeatFinding(
                rule_id="EEAT-AUTHOR-001",
                severity="WARNING",
                message=f"Author '{result.author_name}' identified without detailed bio or authority sameAs profiles.",
                dimension="Expertise"
            ))
    else:
        result.findings.append(EeatFinding(
            rule_id="EEAT-AUTHOR-001",
            severity="INFO",
            message="No explicit individual author byline or author Person entity identified.",
            dimension="Expertise"
        ))

    # Organization & Transparency (25 pts)
    org_pts = 0
    if result.has_organization:
        org_pts += 10
    if result.has_about_page:
        org_pts += 5
    if result.has_contact_page:
        org_pts += 5
    if result.has_editorial_policy:
        org_pts += 5
    score += org_pts

    if not result.has_contact_page and not result.has_about_page:
        result.findings.append(EeatFinding(
            rule_id="EEAT-TRANSPARENCY-002",
            severity="WARNING",
            message="Missing visible navigation links to About Us or Contact Us pages.",
            dimension="Trust"
        ))
    else:
        result.findings.append(EeatFinding(
            rule_id="EEAT-TRANSPARENCY-002",
            severity="PASS",
            message="Publisher organization and transparency touchpoints (About/Contact) detected.",
            dimension="Trust"
        ))

    # First-Hand Experience (25 pts)
    if result.first_hand_experience_count > 0:
        score += min(25, 10 + result.first_hand_experience_count * 5)
        result.findings.append(EeatFinding(
            rule_id="EEAT-EXPERIENCE-003",
            severity="PASS",
            message=f"Detected {result.first_hand_experience_count} marker(s) of first-hand empirical experience/testing.",
            dimension="Experience",
            details={"snippets": result.experience_snippets}
        ))
    else:
        result.findings.append(EeatFinding(
            rule_id="EEAT-EXPERIENCE-003",
            severity="INFO",
            message="No explicit first-hand testing or hands-on experimental markers identified.",
            dimension="Experience"
        ))

    # YMYL & Disclaimer Compliance (25 pts)
    if result.is_ymyl_content:
        if result.has_ymyl_disclaimer:
            score += 25
            result.findings.append(EeatFinding(
                rule_id="EEAT-YMYL-004",
                severity="PASS",
                message="YMYL topic area detected with required professional advice disclaimer.",
                dimension="Trust"
            ))
        else:
            result.findings.append(EeatFinding(
                rule_id="EEAT-YMYL-004",
                severity="WARNING",
                message="Page discusses YMYL financial/medical/legal topics without explicit professional disclaimer.",
                dimension="Trust"
            ))
    else:
        # Non-YMYL content receives full trust baseline
        score += 25

    result.eeat_score = min(100, score)
    return result
