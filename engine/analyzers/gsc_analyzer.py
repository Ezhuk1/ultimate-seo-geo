"""
Deterministic Google Search Console (GSC) CSV Analyzer for ultimate-seo-geo.

Analyzes performance export CSVs (Queries.csv, Pages.csv) to discover
high-leverage 'Striking Distance' queries (positions 5.0 - 20.0 with >= 50 impressions),
position-aware CTR underperformers, quick-win page mappings, and keyword
cannibalization (same query served by multiple URLs with split impression share).
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
    expected_ctr: Optional[float] = None  # position-model expectation, when computed

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "query": self.query,
            "clicks": self.clicks,
            "impressions": self.impressions,
            "ctr": round(self.ctr, 2),
            "position": round(self.position, 1),
            "page": self.page,
            "opportunity_type": self.opportunity_type
        }
        if self.expected_ctr is not None:
            d["expected_ctr"] = round(self.expected_ctr, 1)
            d["ctr_deficit_pct"] = round(max(0.0, (self.expected_ctr - self.ctr) / self.expected_ctr * 100.0), 1)
        return d


@dataclass
class GscCannibalizationItem:
    """Multiple URLs on the same site competing for one query (split authority)."""
    query: str
    pages: List[str]
    page_impressions: Dict[str, int]
    page_positions: Dict[str, float]
    total_impressions: int
    best_position: float
    top_page: str
    top_page_impression_share_pct: float  # 0-100
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "pages": self.pages,
            "page_impressions": self.page_impressions,
            "page_positions": {k: round(v, 1) for k, v in self.page_positions.items()},
            "total_impressions": self.total_impressions,
            "best_position": round(self.best_position, 1),
            "top_page": self.top_page,
            "top_page_impression_share_pct": round(self.top_page_impression_share_pct, 1),
            "recommendation": self.recommendation
        }


@dataclass
class GscDecayItem:
    query: str
    prior_clicks: int
    recent_clicks: int
    clicks_drop_pct: float
    prior_impressions: int
    recent_impressions: int
    impressions_drop_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "prior_clicks": self.prior_clicks,
            "recent_clicks": self.recent_clicks,
            "clicks_drop_pct": round(self.clicks_drop_pct, 1),
            "prior_impressions": self.prior_impressions,
            "recent_impressions": self.recent_impressions,
            "impressions_drop_pct": round(self.impressions_drop_pct, 1)
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
    cannibalization: List[GscCannibalizationItem] = field(default_factory=list)
    cannibalization_count: int = 0
    cannibalization_note: str = ""  # set when the export lacks query+page columns
    decay_items: List[GscDecayItem] = field(default_factory=list)
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
            "cannibalization_count": self.cannibalization_count,
            "cannibalization_note": self.cannibalization_note,
            "cannibalization": [c.to_dict() for c in self.cannibalization[:20]],
            "decay_items": [d.to_dict() for d in self.decay_items[:30]],
            "error_message": self.error_message
        }


# Aggregate organic CTR benchmarks by Google position (piecewise-linear anchors).
# Heuristic model aggregated from public industry CTR studies (Advanced Web Ranking /
# Backlinko-style curves); used as a *relative* underperformance reference, never as
# an absolute expectation. Tunable per niche.
EXPECTED_CTR_CURVE: Dict[int, float] = {
    1: 28.0, 2: 15.0, 3: 10.0, 4: 7.0, 5: 5.0,
    6: 3.8, 7: 3.0, 8: 2.4, 9: 2.0, 10: 1.7,
    11: 1.4, 12: 1.2, 13: 1.0, 14: 0.9, 15: 0.8,
    16: 0.7, 17: 0.6, 18: 0.55, 19: 0.5, 20: 0.45
}


def expected_organic_ctr(position: float) -> Optional[float]:
    """Interpolated expected CTR (%) for a given average position, or None beyond the curve."""
    if position is None or position <= 0:
        return None
    anchors = sorted(EXPECTED_CTR_CURVE.items())
    if position <= anchors[0][0]:
        return anchors[0][1]
    if position >= anchors[-1][0]:
        return None
    for (pos_a, ctr_a), (pos_b, ctr_b) in zip(anchors, anchors[1:]):
        if pos_a <= position <= pos_b:
            return ctr_a + (ctr_b - ctr_a) * ((position - pos_a) / (pos_b - pos_a))
    return None


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
    # Excel/Windows exports keep a UTF-8 BOM in the first header cell, which
    # makes the query column unrecognizable ("\ufeffЗапрос"). Strip it once here.
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
    raw_text = raw_text.lstrip("\ufeff").lstrip()

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
        # Zero-impression rows carry no weight in either term (pos*max(1,0)
        # used to add pos to the numerator while adding nothing to the denominator)
        if impressions > 0:
            weighted_pos_sum += pos * impressions

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
            # Quick win: top-10 striking distance (pos 5.0 - 10.0 with high impressions).
            # Append a copy: mutating the shared item used to relabel the entry already
            # sitting in striking_distance ("widget" showed opportunity_type=quick_win there).
            if item.position <= 10.0 and item.impressions >= (min_impressions * 2):
                quick_wins.append(GscQueryItem(
                    query=item.query, clicks=item.clicks, impressions=item.impressions,
                    ctr=item.ctr, position=item.position, page=item.page,
                    opportunity_type="quick_win"
                ))

        # CTR Opportunity (position-aware): flag snippets that underperform the
        # position-typical CTR curve by >= 50%, in addition to the static < 2.0%
        # floor for Page-1 ranks. E.g. position 1 with 5% CTR is a snippet failure
        # even though 5% > 2.0%.
        exp_ctr = expected_organic_ctr(item.position)
        ctr_deficit = (exp_ctr is not None and exp_ctr > 0 and item.ctr < 0.5 * exp_ctr)
        is_low_ctr_static = 0 < item.position <= 10.0 and item.impressions >= (min_impressions * 2) and item.ctr < 2.0
        if item.position > 0 and item.impressions >= (min_impressions * 2) and (is_low_ctr_static or ctr_deficit):
            ctr_item = GscQueryItem(
                query=item.query,
                clicks=item.clicks,
                impressions=item.impressions,
                ctr=item.ctr,
                position=item.position,
                page=item.page,
                opportunity_type="low_ctr",
                expected_ctr=exp_ctr
            )
            ctr_opps.append(ctr_item)

    # Keyword Cannibalization: same query served by multiple URLs on the site
    # (split authority). Only measurable when the export carries both query and
    # page dimensions; otherwise recorded as NOT MEASURED with a note.
    cannibal_items: List[GscCannibalizationItem] = []
    if col_query != -1 and col_page != -1:
        q_page_agg: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for item in parsed_items:
            if not item.page:
                continue
            q_entry = q_page_agg.setdefault(item.query, {})
            page_agg = q_entry.setdefault(item.page, {"impr": 0, "best_pos": None})
            page_agg["impr"] += item.impressions
            if item.position > 0 and (page_agg["best_pos"] is None or item.position < page_agg["best_pos"]):
                page_agg["best_pos"] = item.position

        for q_text, pages_agg in q_page_agg.items():
            if len(pages_agg) < 2:
                continue
            total_impr = sum(a["impr"] for a in pages_agg.values())
            if total_impr < min_impressions:
                continue
            if total_impr <= 0:
                continue
            top_page, _top_agg = max(pages_agg.items(), key=lambda kv: kv[1]["impr"])
            top_impr = pages_agg[top_page]["impr"]
            top_share = top_impr / total_impr * 100.0
            top_page_pos = pages_agg[top_page].get("best_pos")
            best_pos = min((a["best_pos"] for a in pages_agg.values() if a["best_pos"] is not None), default=None)
            # Healthy pattern: one dominant URL (>= 60% of impressions) that ITSELF
            # ranks top-3. Judging by the best position across all pages used to
            # mask a dominant URL stuck on #8 behind a minor #2 hit.
            if top_share >= 60.0 and top_page_pos is not None and top_page_pos <= 3.0:
                continue
            if top_page_pos is not None and top_page_pos <= 3.0:
                rec = (f"Primary URL {top_page} ranks top-3 but competes with {len(pages_agg) - 1} secondary page(s). "
                       "Canonicalize or 301 secondary pages into the primary and align anchors.")
            elif top_share >= 60.0:
                rec = (f"{top_page} dominates this query but ranks outside top-3. Consolidate remaining "
                       "secondary URLs into it, then strengthen internal links and on-page focus.")
            else:
                rec = ("No single URL owns this query (split impression share). Pick one canonical target, "
                       "differentiate or fold the rest, and point internal anchors at the chosen primary.")
            cannibal_items.append(GscCannibalizationItem(
                query=q_text,
                pages=sorted(pages_agg.keys(), key=lambda p: -pages_agg[p]["impr"]),
                page_impressions={p: a["impr"] for p, a in pages_agg.items()},
                page_positions={p: a["best_pos"] for p, a in pages_agg.items() if a["best_pos"] is not None},
                total_impressions=total_impr,
                best_position=best_pos if best_pos is not None else 0.0,
                top_page=top_page,
                top_page_impression_share_pct=top_share,
                recommendation=rec
            ))
    elif col_query != -1 or col_page != -1:
        res.cannibalization_note = ("NOT MEASURED: cannibalization detection requires a GSC export with both "
                                    "query and page dimensions; this export provides only one of them.")

    # Sort opportunities by impressions descending (highest leverage first)
    res.striking_distance = sorted(striking_dist, key=lambda x: x.impressions, reverse=True)
    res.quick_wins = sorted(quick_wins, key=lambda x: x.impressions, reverse=True)
    res.ctr_opportunities = sorted(ctr_opps, key=lambda x: x.impressions, reverse=True)
    res.striking_distance_count = len(res.striking_distance)
    res.cannibalization = sorted(cannibal_items, key=lambda x: x.total_impressions, reverse=True)
    res.cannibalization_count = len(res.cannibalization)
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
        md.append("### ⚠️ Snippet Underperformers (CTR Below Position Benchmark)")
        md.append("These queries already rank on Page 1, but searchers skip your snippet. Rewrite `<title>` pixel width (~580px) and `<meta description>`:")
        md.append("")
        md.append("| Query | Position | Impressions | Current CTR | Expected CTR* | Recommended Snippet Fix |")
        md.append("|---|:---:|:---:|:---:|:---:|---|")
        for q in res.ctr_opportunities[:15]:
            exp_label = f"{q.expected_ctr:.1f}%" if q.expected_ctr is not None else "—"
            if q.expected_ctr is not None:
                fix = "Far below position-typical CTR: rewrite snippet with direct value proposition"
            else:
                fix = "Rewrite `<title>` (~580px) & `<meta description>` with active CTA"
            md.append(f"| `{q.query}` | #{q.position:.1f} | {q.impressions:,} | {q.ctr:.2f}% | {exp_label} | {fix} |")
        md.append("")
        md.append("*Expected CTR is a heuristic aggregate benchmark for the average position — tune per niche.")

    if res.cannibalization:
        md.append("")
        md.append("### 🔀 Keyword Cannibalization (Split Authority)")
        md.append("One query is served by multiple URLs, splitting ranking signals across them. Consolidate to concentrate authority:")
        md.append("")
        md.append("| Query | URLs | Best Spot | Top URL Share | Total Impressions | Recommended Consolidation |")
        md.append("|---|:---:|:---:|:---:|:---:|---|")
        for c in res.cannibalization[:15]:
            spot = f"#{c.best_position:.1f}" if c.best_position > 0 else "—"
            md.append(f"| `{c.query}` | {len(c.pages)} | {spot} | {c.top_page_impression_share_pct:.0f}% | {c.total_impressions:,} | {c.recommendation} |")
        md.append("")
        md.append(f"<details><summary>Primary URL mapping ({len(res.cannibalization)} queries)</summary>\n")
        for c in res.cannibalization[:20]:
            md.append(f"- `{c.query}` → keep `{c.top_page}` ({c.top_page_impression_share_pct:.0f}% of impressions); fold: {', '.join(f'`{p}`' for p in c.pages if p != c.top_page)}")
        md.append("\n</details>")

    if res.cannibalization_note:
        md.append("")
        md.append(f"> [!NOTE]\n> **Cannibalization {res.cannibalization_note}**")

    if res.decay_items:
        md.append("")
        md.append("### 📉 Content Decay Alerts (Queries Losing $\\ge$20% Traffic)")
        md.append("These queries experienced significant traffic drops. Prioritize content refresh, temporal updates, and entity expansion:")
        md.append("")
        md.append("| Query | Prior Clicks | Recent Clicks | Clicks Drop | Prior Impressions | Recent Impressions |")
        md.append("|---|:---:|:---:|:---:|:---:|:---:|")
        for d in res.decay_items[:15]:
            md.append(f"| `{d.query}` | {d.prior_clicks:,} | {d.recent_clicks:,} | -{d.clicks_drop_pct:.1f}% | {d.prior_impressions:,} | {d.recent_impressions:,} |")

    md.append("")
    return "\n".join(md)


def analyze_gsc_decay(
    historical_csv_or_content: str,
    recent_csv_or_content: str,
    min_drop_pct: float = 20.0,
    min_prior_clicks: int = 10
) -> List[GscDecayItem]:
    """
    Compares two GSC CSV snapshots (e.g. 16-month vs 3-month, or previous period)
    to identify queries suffering significant Content Decay (>= 20% traffic loss).
    """
    def _extract_query_map(content_or_path: str) -> Dict[str, tuple[int, int]]:
        text = ""
        if os.path.exists(content_or_path):
            with open(content_or_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = content_or_path
        if not text.strip():
            return {}
        sample = text[:2048]
        delim = "\t" if "\t" in sample and sample.count("\t") > sample.count(",") else (";" if ";" in sample and sample.count(";") > sample.count(",") else ",")
        reader = csv.reader(io.StringIO(text.lstrip("\ufeff")), delimiter=delim)
        header = next(reader, None)
        if not header:
            return {}
        q_idx, c_idx, i_idx = -1, -1, -1
        for idx, col in enumerate(header):
            c_low = col.strip().lower()
            if c_low in QUERY_ALIASES:
                q_idx = idx
            elif c_low in CLICKS_ALIASES:
                c_idx = idx
            elif c_low in IMPRESSIONS_ALIASES:
                i_idx = idx
        if q_idx == -1 or c_idx == -1:
            return {}
        q_map = {}
        for row in reader:
            if not row or len(row) <= max(q_idx, c_idx):
                continue
            q_text = row[q_idx].strip()
            if not q_text or q_text.lower().startswith(("total", "всего", "итог")):
                continue
            c_val = _parse_int(row[c_idx])
            i_val = _parse_int(row[i_idx]) if i_idx != -1 and len(row) > i_idx else 0
            q_map[q_text] = (c_val, i_val)
        return q_map

    hist_map = _extract_query_map(historical_csv_or_content)
    rec_map = _extract_query_map(recent_csv_or_content)

    decay_items = []
    for q_text, (prior_c, prior_i) in hist_map.items():
        if prior_c < min_prior_clicks:
            continue
        recent_c, recent_i = rec_map.get(q_text, (0, 0))
        if prior_c > recent_c:
            drop_pct = (prior_c - recent_c) / prior_c * 100.0
            if drop_pct >= min_drop_pct:
                impr_drop = ((prior_i - recent_i) / prior_i * 100.0) if prior_i > recent_i and prior_i > 0 else 0.0
                decay_items.append(GscDecayItem(
                    query=q_text,
                    prior_clicks=prior_c,
                    recent_clicks=recent_c,
                    clicks_drop_pct=drop_pct,
                    prior_impressions=prior_i,
                    recent_impressions=recent_i,
                    impressions_drop_pct=impr_drop
                ))

    return sorted(decay_items, key=lambda x: (x.prior_clicks - x.recent_clicks), reverse=True)

