"""
Deterministic Google Search Console (GSC) CSV Analyzer for ultimate-seo-geo.

Analyzes performance export CSVs (Queries.csv, Pages.csv) to discover
high-leverage 'Striking Distance' queries (positions 5.0 - 20.0 with >= 50 impressions),
CTR optimization opportunities, and quick-win page mappings.
Pure Python standard library with zero external dependencies.
"""

from __future__ import annotations
import csv
import io
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class GscQueryItem:
    query: str
    clicks: int
    impressions: int
    ctr: float  # e.g., 2.5 for 2.5%
    position: float
    page: Optional[str] = None
    opportunity_type: str = "striking_distance"  # striking_distance, quick_win, low_ctr

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "clicks": self.clicks,
            "impressions": self.impressions,
            "ctr": round(self.ctr, 2),
            "position": round(self.position, 1),
            "page": self.page,
            "opportunity_type": self.opportunity_type
        }


@dataclass
class GscAnalysisResult:
    is_valid: bool = False
    file_path: str = ""
    total_rows: int = 0
    total_clicks: int = 0
    total_impressions: int = 0
    average_ctr: float = 0.0
    average_position: float = 0.0
    striking_distance_count: int = 0
    striking_distance: List[GscQueryItem] = field(default_factory=list)
    quick_wins: List[GscQueryItem] = field(default_factory=list)
    ctr_opportunities: List[GscQueryItem] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "file_path": self.file_path,
            "total_rows": self.total_rows,
            "total_clicks": self.total_clicks,
            "total_impressions": self.total_impressions,
            "average_ctr": round(self.average_ctr, 2),
            "average_position": round(self.average_position, 1),
            "striking_distance_count": self.striking_distance_count,
            "striking_distance": [q.to_dict() for q in self.striking_distance[:50]],
            "quick_wins": [q.to_dict() for q in self.quick_wins[:20]],
            "ctr_opportunities": [q.to_dict() for q in self.ctr_opportunities[:20]],
            "error_message": self.error_message
        }


# Header aliases for multilingual/varied exports
QUERY_ALIASES = {"query", "top queries", "запрос", "поисковый запрос", "search query", "keyword", "keywords"}
PAGE_ALIASES = {"page", "top pages", "страница", "url", "landing page"}
CLICKS_ALIASES = {"clicks", "клики", "переходы"}
IMPRESSIONS_ALIASES = {"impressions", "показы"}
CTR_ALIASES = {"ctr", "click-through rate", "ctr (%)", "ctr(%)", "кликабельность"}
POSITION_ALIASES = {"position", "позиция", "average position", "средняя позиция"}


def _parse_float(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).strip().replace("%", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_int(val: Any) -> int:
    if val is None:
        return 0
    s = str(val).strip().replace(" ", "").replace(",", "").replace("\xa0", "")
    try:
        return int(float(s))
    except ValueError:
        return 0


def analyze_gsc_csv(
    file_path_or_content: str,
    min_position: float = 5.0,
    max_position: float = 20.0,
    min_impressions: int = 50
) -> GscAnalysisResult:
    """
    Parses a Google Search Console CSV export and extracts actionable query opportunities.
    """
    res = GscAnalysisResult()

    raw_text = ""
    if os.path.exists(file_path_or_content):
        res.file_path = file_path_or_content
        try:
            with open(file_path_or_content, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        except Exception as e:
            res.error_message = f"Failed to read CSV file: {e}"
            return res
    else:
        raw_text = file_path_or_content

    if not raw_text.strip():
        res.error_message = "CSV content is empty."
        return res

    # Sniff dialect / delimiter (comma, tab, semicolon)
    sample = raw_text[:2048]
    delimiter = ","
    if "\t" in sample and sample.count("\t") > sample.count(","):
        delimiter = "\t"
    elif ";" in sample and sample.count(";") > sample.count(","):
        delimiter = ";"

    reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)
    try:
        header = next(reader, None)
    except Exception as e:
        res.error_message = f"Failed to parse CSV header: {e}"
        return res

    if not header:
        res.error_message = "Empty CSV header."
        return res

    # Map column indices
    col_query = -1
    col_page = -1
    col_clicks = -1
    col_impressions = -1
    col_ctr = -1
    col_position = -1

    for idx, col_name in enumerate(header):
        c_clean = col_name.strip().lower()
        if c_clean in QUERY_ALIASES:
            col_query = idx
        elif c_clean in PAGE_ALIASES:
            col_page = idx
        elif c_clean in CLICKS_ALIASES:
            col_clicks = idx
        elif c_clean in IMPRESSIONS_ALIASES:
            col_impressions = idx
        elif c_clean in CTR_ALIASES:
            col_ctr = idx
        elif c_clean in POSITION_ALIASES:
            col_position = idx

    if col_query == -1 and col_page == -1:
        res.error_message = f"Unrecognized GSC CSV format: missing query or page column. Found: {header}"
        return res

    parsed_items: List[GscQueryItem] = []
    tot_clicks = 0
    tot_impr = 0
    weighted_pos_sum = 0.0

    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue

        q_text = row[col_query].strip() if col_query != -1 and col_query < len(row) else ""
        p_text = row[col_page].strip() if col_page != -1 and col_page < len(row) else None
        
        # If this is a Pages export without Query, use page as main entity
        main_key = q_text or p_text or ""
        if not main_key:
            continue

        clicks = _parse_int(row[col_clicks]) if col_clicks != -1 and col_clicks < len(row) else 0
        impressions = _parse_int(row[col_impressions]) if col_impressions != -1 and col_impressions < len(row) else 0
        ctr = _parse_float(row[col_ctr]) if col_ctr != -1 and col_ctr < len(row) else 0.0
        pos = _parse_float(row[col_position]) if col_position != -1 and col_position < len(row) else 0.0

        tot_clicks += clicks
        tot_impr += impressions
        weighted_pos_sum += pos * max(1, impressions)

        item = GscQueryItem(
            query=main_key,
            clicks=clicks,
            impressions=impressions,
            ctr=ctr,
            position=pos,
            page=p_text
        )
        parsed_items.append(item)

    res.total_rows = len(parsed_items)
    res.total_clicks = tot_clicks
    res.total_impressions = tot_impr
    res.average_ctr = (tot_clicks / tot_impr * 100.0) if tot_impr > 0 else 0.0
    res.average_position = (weighted_pos_sum / tot_impr) if tot_impr > 0 else 0.0

    # Classify Opportunities
    striking_dist = []
    quick_wins = []
    ctr_opps = []

    for item in parsed_items:
        # Striking Distance: position in [min_position, max_position] and impressions >= threshold
        if min_position <= item.position <= max_position and item.impressions >= min_impressions:
            striking_dist.append(item)
            # Quick win: top-10 striking distance (pos 5.0 - 10.0 with high impressions)
            if item.position <= 10.0 and item.impressions >= (min_impressions * 2):
                item.opportunity_type = "quick_win"
                quick_wins.append(item)

        # CTR Opportunity: top 10 (pos <= 10.0), healthy impressions, but CTR underperforms (< 2.0%)
        if item.position <= 10.0 and item.impressions >= (min_impressions * 2) and item.ctr < 2.0:
            ctr_item = GscQueryItem(
                query=item.query,
                clicks=item.clicks,
                impressions=item.impressions,
                ctr=item.ctr,
                position=item.position,
                page=item.page,
                opportunity_type="low_ctr"
            )
            ctr_opps.append(ctr_item)

    # Sort opportunities by impressions descending (highest leverage first)
    res.striking_distance = sorted(striking_dist, key=lambda x: x.impressions, reverse=True)
    res.quick_wins = sorted(quick_wins, key=lambda x: x.impressions, reverse=True)
    res.ctr_opportunities = sorted(ctr_opps, key=lambda x: x.impressions, reverse=True)
    res.striking_distance_count = len(res.striking_distance)
    res.is_valid = True

    return res


def format_gsc_markdown_summary(res: GscAnalysisResult) -> str:
    """
    Renders an executive Striking-Distance Action Plan from GSC analysis.
    """
    if not res.is_valid:
        return f"> [!WARNING]\n> **GSC CSV Analysis Failed:** {res.error_message}\n"

    md = [
        "## 🎯 Google Search Console: Striking Distance & Opportunity Plan",
        "",
        f"- **Dataset Scope:** {res.total_rows:,} queries/pages analyzed ({res.total_impressions:,} impressions, {res.total_clicks:,} clicks, Avg CTR: {res.average_ctr:.2f}%).",
        f"- **Striking Distance Queries (Positions 5.0–20.0, $\\ge$50 imp):** **{res.striking_distance_count}** high-leverage terms ready for Top-3 push.",
        "",
        "### 🚀 Highest-Leverage Striking Distance Queries",
        "Targeted on-page tuning (H1, direct answer frontloading, schema entity links) on these queries yields maximum qualified traffic lift without requiring new URLs:",
        "",
        "| Query / Keyword | Current Spot | Monthly Impressions | Clicks | CTR | Action Plan |",
        "|---|:---:|:---:|:---:|:---:|---|"
    ]

    for q in res.striking_distance[:15]:
        spot_label = f"#{q.position:.1f} (Page {int((q.position - 1) // 10) + 1})"
        action = "Front-load definition & add entity Schema" if q.position > 10 else "Optimize title snippet & CTA for CTR"
        md.append(f"| `{q.query}` | {spot_label} | {q.impressions:,} | {q.clicks:,} | {q.ctr:.2f}% | {action} |")

    if res.ctr_opportunities:
        md.append("")
        md.append("### ⚠️ Snippet Underperformers (Top-10 Rank with Low CTR < 2%)")
        md.append("These queries already rank on Page 1, but searchers skip your snippet. Rewrite `<title>` pixel width (~580px) and `<meta description>`:")
        md.append("")
        md.append("| Query | Position | Impressions | Current CTR | Recommended Snippet Fix |")
        md.append("|---|:---:|:---:|:---:|---|")
        for q in res.ctr_opportunities[:10]:
            md.append(f"| `{q.query}` | #{q.position:.1f} | {q.impressions:,} | {q.ctr:.2f}% | Add direct differentiator and active verb |")

    md.append("")
    return "\n".join(md)
