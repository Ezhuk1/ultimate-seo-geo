"""
Deterministic Google Analytics 4 (GA4) AI-Referral Analyzer for ultimate-seo-geo.

Analyzes Traffic Acquisition export CSVs to discover and quantify real-user
referral traffic coming from AI search engines and assistants (ChatGPT, Perplexity,
Claude, Google Gemini/AI Overviews, Microsoft Copilot).
Pure Python standard library with zero external dependencies.
"""

from __future__ import annotations
import csv
import io
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from pathlib import Path


@dataclass
class AiReferralSource:
    source_name: str
    ai_platform: str
    sessions: int
    engaged_sessions: int
    engagement_rate: float  # percentage e.g. 65.4
    avg_engagement_time_sec: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "ai_platform": self.ai_platform,
            "sessions": self.sessions,
            "engaged_sessions": self.engaged_sessions,
            "engagement_rate": round(self.engagement_rate, 2),
            "avg_engagement_time_sec": round(self.avg_engagement_time_sec, 1)
        }


@dataclass
class Ga4AnalysisResult:
    is_valid: bool = False
    file_path: str = ""
    total_sessions: int = 0
    total_ai_sessions: int = 0
    ai_traffic_share_pct: float = 0.0
    ai_sources_count: int = 0
    ai_sources: List[AiReferralSource] = field(default_factory=list)
    top_ai_platform: str = "None"
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "file_path": self.file_path,
            "total_sessions": self.total_sessions,
            "total_ai_sessions": self.total_ai_sessions,
            "ai_traffic_share_pct": round(self.ai_traffic_share_pct, 2),
            "ai_sources_count": self.ai_sources_count,
            "top_ai_platform": self.top_ai_platform,
            "ai_sources": [s.to_dict() for s in self.ai_sources],
            "error_message": self.error_message
        }


# Known AI Referrer Patterns
AI_REFERRAL_PATTERNS = [
    (re.compile(r"chatgpt|chat\.openai\.com", re.IGNORECASE), "ChatGPT"),
    (re.compile(r"perplexity", re.IGNORECASE), "Perplexity AI"),
    (re.compile(r"claude\.ai|claude", re.IGNORECASE), "Claude"),
    (re.compile(r"googlequicksearchbox|gemini\.google\.com", re.IGNORECASE), "Google Gemini / AIO"),
    (re.compile(r"copilot\.microsoft\.com|edgeservices\.bing\.com", re.IGNORECASE), "Microsoft Copilot"),
    (re.compile(r"meta\.ai", re.IGNORECASE), "Meta AI"),
    (re.compile(r"you\.com", re.IGNORECASE), "You.com"),
]

SOURCE_ALIASES = {"session source / medium", "session source", "source / medium", "source", "источник и канал сеанса", "источник сеанса", "источник"}
SESSIONS_ALIASES = {"sessions", "сеансы", "сессии", "visits"}
ENGAGED_ALIASES = {"engaged sessions", "сеансы с взаимодействием"}
ENGAGEMENT_RATE_ALIASES = {"engagement rate", "коэффициент взаимодействия", "доля взаимодействий"}
AVG_TIME_ALIASES = {"average engagement time", "average engagement time per session", "средняя продолжительность взаимодействия"}


def _parse_num(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).strip().replace("%", "").replace(",", ".").replace(" ", "").replace("\xa0", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_time_sec(val: Any) -> float:
    """Parses seconds, or formats like '0m 45s' or '00:00:45' into seconds."""
    if val is None:
        return 0.0
    s = str(val).strip()
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
        except ValueError:
            pass
    return _parse_num(s)


def analyze_ga4_csv(file_or_content: Union[str, Path, bytes]) -> Ga4AnalysisResult:
    """
    Parses a GA4 Traffic Acquisition CSV export and extracts AI-referral performance.
    """
    res = Ga4AnalysisResult()

    raw_text = ""
    if isinstance(file_or_content, bytes):
        raw_text = file_or_content.decode("utf-8", errors="replace")
    elif isinstance(file_or_content, (str, Path)) and os.path.exists(file_or_content):
        res.file_path = str(file_or_content)
        try:
            with open(file_or_content, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        except Exception as e:
            res.error_message = f"Failed to read file: {e}"
            return res
    elif isinstance(file_or_content, str):
        raw_text = file_or_content
    else:
        res.error_message = "Invalid CSV input provided"
        return res

    raw_text = raw_text.lstrip("\ufeff").strip()
    if not raw_text:
        res.error_message = "CSV content is empty"
        return res

    # Delimiter detection
    first_lines = raw_text.splitlines()[:5]
    sample = "\n".join(first_lines)
    delimiter = ","
    if sample.count(";") > sample.count(","):
        delimiter = ";"
    elif sample.count("\t") > sample.count(","):
        delimiter = "\t"

    reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        res.error_message = "No data rows found in CSV"
        return res

    # Find header row
    header_idx = -1
    col_map: Dict[str, int] = {}
    for idx, row in enumerate(rows[:10]):
        row_norm = [c.strip().lower() for c in row]
        has_source = any(c in SOURCE_ALIASES for c in row_norm)
        has_sessions = any(c in SESSIONS_ALIASES for c in row_norm)
        if has_source and has_sessions:
            header_idx = idx
            for c_idx, c_name in enumerate(row_norm):
                if c_name in SOURCE_ALIASES and "source" not in col_map:
                    col_map["source"] = c_idx
                elif c_name in SESSIONS_ALIASES and "sessions" not in col_map:
                    col_map["sessions"] = c_idx
                elif c_name in ENGAGED_ALIASES and "engaged" not in col_map:
                    col_map["engaged"] = c_idx
                elif c_name in ENGAGEMENT_RATE_ALIASES and "rate" not in col_map:
                    col_map["rate"] = c_idx
                elif c_name in AVG_TIME_ALIASES and "time" not in col_map:
                    col_map["time"] = c_idx
            break

    if header_idx == -1 or "source" not in col_map or "sessions" not in col_map:
        res.error_message = f"Required GA4 columns ('Session source', 'Sessions') not found in headers"
        return res

    total_sessions = 0
    ai_sources: List[AiReferralSource] = []

    for row in rows[header_idx + 1:]:
        if not row or len(row) <= max(col_map.values()):
            continue
        src = row[col_map["source"]].strip()
        if not src or src.lower().startswith(("total", "всего", "итог")):
            continue

        sess = int(_parse_num(row[col_map["sessions"]]))
        total_sessions += sess

        # Check if source matches AI patterns
        matched_platform: Optional[str] = None
        for pattern, platform in AI_REFERRAL_PATTERNS:
            if pattern.search(src):
                matched_platform = platform
                break

        if matched_platform:
            eng = int(_parse_num(row[col_map["engaged"]])) if "engaged" in col_map else 0
            rate = _parse_num(row[col_map["rate"]]) if "rate" in col_map else ((eng / sess * 100.0) if sess > 0 else 0.0)
            avg_time = _parse_time_sec(row[col_map["time"]]) if "time" in col_map else 0.0

            ai_sources.append(AiReferralSource(
                source_name=src,
                ai_platform=matched_platform,
                sessions=sess,
                engaged_sessions=eng,
                engagement_rate=rate,
                avg_engagement_time_sec=avg_time
            ))

    res.total_sessions = total_sessions
    res.ai_sources = sorted(ai_sources, key=lambda x: x.sessions, reverse=True)
    res.total_ai_sessions = sum(s.sessions for s in res.ai_sources)
    res.ai_sources_count = len(res.ai_sources)
    res.ai_traffic_share_pct = (res.total_ai_sessions / total_sessions * 100.0) if total_sessions > 0 else 0.0
    if res.ai_sources:
        res.top_ai_platform = res.ai_sources[0].ai_platform
    res.is_valid = True
    return res


def format_ga4_markdown_summary(res: Ga4AnalysisResult) -> str:
    """Renders executive summary of real AI-referred traffic from GA4."""
    if not res.is_valid:
        return f"> [!WARNING]\n> **GA4 CSV Analysis Failed:** {res.error_message}\n"

    md = [
        "## 🤖 Google Analytics 4: AI Referral Visibility & Traffic",
        "",
        f"- **Total Measured Traffic:** {res.total_sessions:,} sessions.",
        f"- **Actual AI-Referred Sessions:** **{res.total_ai_sessions:,}** ({res.ai_traffic_share_pct:.2f}% of total site traffic).",
        f"- **Leading AI Search Platform:** **{res.top_ai_platform}**.",
        ""
    ]

    if not res.ai_sources:
        md.append("> [!NOTE]")
        md.append("> **Zero AI Referral Sessions Detected:** No incoming sessions from ChatGPT, Perplexity, Claude, or Google Quick Search Box were found in this dataset.")
        md.append("")
        return "\n".join(md)

    md.append("### 📈 Breakdown of Actual AI-Referred Traffic")
    md.append("")
    md.append("| AI Platform | Source / Referral | Sessions | Engaged | Engagement Rate | Avg Time |")
    md.append("| :--- | :--- | :---: | :---: | :---: | :---: |")
    for s in res.ai_sources:
        mins = int(s.avg_engagement_time_sec // 60)
        secs = int(s.avg_engagement_time_sec % 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        md.append(f"| **{s.ai_platform}** | `{s.source_name}` | **{s.sessions:,}** | {s.engaged_sessions:,} | {s.engagement_rate:.1f}% | {time_str} |")

    has_gqsb = any("googlequicksearchbox" in s.source_name.lower() for s in res.ai_sources)
    if has_gqsb:
        md.append("")
        md.append("> [!NOTE]")
        md.append("> **Attribution Caution (`googlequicksearchbox`):** Referrals from `googlequicksearchbox` originate from the Google Android Search App / Widget. While this includes AI Overviews presented in the mobile app, it also includes standard Android organic search clicks. Isolating AI Overviews specifically requires Search Console Search Appearance telemetry.")

    md.append("")
    return "\n".join(md)
