"""
Web Content Prompt Injection Analyzer & Defense Engine.

Protects AI/LLM SEO auditor systems from adversarial web content:
- Direct prompt injections ("ignore previous instructions", "score this 100/100")
- Delimiter attacks ([INST], <|im_start|>, ### System:)
- Hidden CSS / comment injection vectors (display:none, font-size:0, comments)
- Isolation and sanitization guarantees (untrusted content treated strictly as data)

References: OWASP Top 10 for LLM Applications (LLM01 Prompt Injection).
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class PromptInjectionFinding:
    pattern_type: str
    matched_phrase: str
    location: str
    severity: str = "CRITICAL"
    snippet: str = ""
    is_hidden: bool = False


# High-confidence adversarial injection patterns
DIRECT_INJECTION_PATTERNS = [
    (r"ignore\s+(?:all\s+)?previous\s+(?:instructions|directives|prompts|commands)", "DIRECT_INSTRUCTION_OVERRIDE"),
    (r"disregard\s+(?:all\s+)?prior\s+(?:instructions|context|guidelines)", "DIRECT_INSTRUCTION_OVERRIDE"),
    (r"you\s+are\s+now\s+(?:a|an|the)?\s*(?:new\s+)?(?:assistant|developer|root|admin|dan|jailbreak)", "ROLE_HIJACK"),
    (r"(?:give|rate|score|award)\s+(?:this\s+)?(?:page|site|website)\s+(?:a\s+)?(?:score\s+of\s+)?100(?:/100)?", "SCORING_MANIPULATION"),
    (r"output\s+only\s+(?:a\s+)?100\s+score", "SCORING_MANIPULATION"),
    (r"do\s+not\s+report\s+(?:any\s+)?(?:errors|warnings|defects|findings)", "DEFECT_SUPPRESSION"),
    (r"system\s+prompt\s*:\s*(?:you\s+are|override|ignore)", "SYSTEM_PROMPT_SPOOF"),
    (r"new\s+instructions?\s*:\s*(?:ignore|override|score)", "NEW_INSTRUCTION_SPOOF"),
]

DELIMITER_INJECTION_PATTERNS = [
    (r"\[INST\]", "LLM_DELIMITER_INST"),
    (r"<\|im_start\|>", "LLM_DELIMITER_CHATML"),
    (r"<\|system\|>", "LLM_DELIMITER_CHATML_SYSTEM"),
    (r"###\s*System\s*:", "MARKDOWN_SYSTEM_DELIMITER"),
    (r"###\s*Instruction\s*:", "MARKDOWN_INSTRUCTION_DELIMITER"),
    (r"SYSTEM\s+MESSAGE\s*:\s*", "SYSTEM_MESSAGE_DELIMITER"),
]

# Hidden CSS text patterns (CSS tricks to hide adversarial text from users while exposing to bots)
HIDDEN_CSS_CONTAINERS = [
    r'<[^>]*style=["\'][^"\']*(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0|font-size\s*:\s*0|text-indent\s*:\s*-[0-9]{3,}px|position\s*:\s*absolute\s*;\s*left\s*:\s*-[0-9]{3,}px)[^"\']*["\'][^>]*>(.*?)</[^>]+>',
]


class SecurityAnalyzer:
    """Detects, reports, and neutralizes prompt injections inside audited web pages."""

    @classmethod
    def analyze(cls, html_content: str) -> List[PromptInjectionFinding]:
        """
        Scans raw HTML, text, attributes, and comments for prompt injection payloads.
        """
        findings: List[PromptInjectionFinding] = []
        if not html_content:
            return findings

        # 1. Check HTML comments for injection vectors
        comment_matches = re.finditer(r'<!--(.*?)-->', html_content, re.DOTALL)
        for cm in comment_matches:
            c_text = cm.group(1)
            for pattern, p_type in DIRECT_INJECTION_PATTERNS + DELIMITER_INJECTION_PATTERNS:
                if re.search(pattern, c_text, re.IGNORECASE):
                    findings.append(PromptInjectionFinding(
                        pattern_type=p_type,
                        matched_phrase=pattern,
                        location="html_comment",
                        severity="CRITICAL",
                        snippet=c_text[:120].strip(),
                        is_hidden=True
                    ))

        # 2. Check CSS-hidden elements for covert injection vectors
        for hidden_re in HIDDEN_CSS_CONTAINERS:
            for hm in re.finditer(hidden_re, html_content, re.DOTALL | re.IGNORECASE):
                inner_text = hm.group(1)
                for pattern, p_type in DIRECT_INJECTION_PATTERNS + DELIMITER_INJECTION_PATTERNS:
                    if re.search(pattern, inner_text, re.IGNORECASE):
                        findings.append(PromptInjectionFinding(
                            pattern_type=p_type,
                            matched_phrase=pattern,
                            location="hidden_css_element",
                            severity="CRITICAL",
                            snippet=inner_text[:120].strip(),
                            is_hidden=True
                        ))

        # 3. Check general text / markup for direct injections
        for pattern, p_type in DIRECT_INJECTION_PATTERNS:
            m = re.search(pattern, html_content, re.IGNORECASE)
            if m:
                # Avoid duplicate if already caught in comments or hidden elements
                snippet = html_content[max(0, m.start() - 30):min(len(html_content), m.end() + 30)]
                if not any(f.snippet in snippet for f in findings):
                    findings.append(PromptInjectionFinding(
                        pattern_type=p_type,
                        matched_phrase=m.group(0),
                        location="visible_html_content",
                        severity="CRITICAL",
                        snippet=snippet.strip(),
                        is_hidden=False
                    ))

        # 4. Check for delimiter injections in body
        for pattern, p_type in DELIMITER_INJECTION_PATTERNS:
            m = re.search(pattern, html_content, re.IGNORECASE)
            if m:
                snippet = html_content[max(0, m.start() - 20):min(len(html_content), m.end() + 20)]
                if not any(f.snippet in snippet for f in findings):
                    findings.append(PromptInjectionFinding(
                        pattern_type=p_type,
                        matched_phrase=m.group(0),
                        location="delimiter_sequence",
                        severity="CRITICAL",
                        snippet=snippet.strip(),
                        is_hidden=False
                    ))

        return findings

    @classmethod
    def sanitize_for_llm(cls, text_content: str) -> str:
        """
        Isolates and neutralizes prompt injection sequences before passing text
        to downstream AI summarization or intent classification models.
        """
        if not text_content:
            return ""

        sanitized = text_content
        for pattern, _ in DIRECT_INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[SECURITY_REDACTED_PROMPT_INJECTION]", sanitized, flags=re.IGNORECASE)

        for pattern, _ in DELIMITER_INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[SECURITY_REDACTED_DELIMITER]", sanitized, flags=re.IGNORECASE)

        return sanitized
