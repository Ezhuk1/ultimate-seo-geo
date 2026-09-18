"""
AI Citation Benchmark & Experimental Layer.

Implements empirical GEO validation:
- Analyzes AI search engine responses (Perplexity, Google AIO, ChatGPT Search, Claude)
- Extracts source citations, entity mentions, and brand references
- Computes core GEO empirical metrics:
  * Citation Rate
  * Brand Mention Rate
  * Source Selection Rate (Top-3)
  * Average Citation Position
  * Competitor Citation Share
- Compares Before / After experiments without false causality claims
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from urllib.parse import urlsplit


@dataclass
class CitationQuerySample:
    query_id: str
    query_text: str
    engine: str
    answer_text: str
    sources: List[str] = field(default_factory=list)


@dataclass
class CitationMetrics:
    total_queries: int
    cited_queries: int
    citation_rate_pct: float
    brand_mention_queries: int
    brand_mention_rate_pct: float
    source_selection_queries: int  # Top 3 source selection
    source_selection_rate_pct: float
    avg_citation_position: Optional[float]
    competitor_citation_rates: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _normalize_domain(url_or_domain: str) -> str:
    cleaned = url_or_domain.strip().lower()
    if "://" in cleaned:
        cleaned = urlsplit(cleaned).netloc
    return cleaned.split(":")[0].lstrip("www.")


def evaluate_citation_benchmark(
    samples: List[CitationQuerySample],
    target_brand: str,
    target_domain: str,
    competitor_domains: Optional[List[str]] = None
) -> CitationMetrics:
    """
    Evaluates a set of AI engine response samples against target brand and domain.
    """
    competitors = [_normalize_domain(c) for c in (competitor_domains or [])]
    norm_target_domain = _normalize_domain(target_domain)
    brand_pattern = re.compile(rf"\b{re.escape(target_brand.strip())}\b", re.IGNORECASE) if target_brand else None

    total_queries = len(samples)
    if total_queries == 0:
        return CitationMetrics(
            total_queries=0,
            cited_queries=0,
            citation_rate_pct=0.0,
            brand_mention_queries=0,
            brand_mention_rate_pct=0.0,
            source_selection_queries=0,
            source_selection_rate_pct=0.0,
            avg_citation_position=None,
            competitor_citation_rates={c: 0.0 for c in competitors}
        )

    cited_count = 0
    brand_mention_count = 0
    top3_count = 0
    positions: List[int] = []
    comp_cited_counts: Dict[str, int] = {c: 0 for c in competitors}

    for s in samples:
        # Check brand mention in answer text
        if brand_pattern and brand_pattern.search(s.answer_text):
            brand_mention_count += 1

        # Check citations in sources
        norm_sources = [_normalize_domain(src) for src in s.sources]
        is_cited = False
        target_pos: Optional[int] = None

        for idx, src_domain in enumerate(norm_sources):
            if norm_target_domain in src_domain or src_domain in norm_target_domain:
                if not is_cited:
                    is_cited = True
                    target_pos = idx + 1
                    positions.append(target_pos)
                    if target_pos <= 3:
                        top3_count += 1

        if is_cited:
            cited_count += 1

        # Track competitor citations
        for comp in competitors:
            if any(comp in src_d or src_d in comp for src_d in norm_sources):
                comp_cited_counts[comp] += 1

    cit_rate = round(cited_count / total_queries * 100, 1)
    brand_rate = round(brand_mention_count / total_queries * 100, 1)
    top3_rate = round(top3_count / total_queries * 100, 1)
    avg_pos = round(sum(positions) / len(positions), 2) if positions else None
    comp_rates = {c: round(cnt / total_queries * 100, 1) for c, cnt in comp_cited_counts.items()}

    return CitationMetrics(
        total_queries=total_queries,
        cited_queries=cited_count,
        citation_rate_pct=cit_rate,
        brand_mention_queries=brand_mention_count,
        brand_mention_rate_pct=brand_rate,
        source_selection_queries=top3_count,
        source_selection_rate_pct=top3_rate,
        avg_citation_position=avg_pos,
        competitor_citation_rates=comp_rates
    )


def load_benchmark_samples(file_path: str) -> tuple[List[CitationQuerySample], str, str, List[str]]:
    """
    Loads benchmark samples from JSON file.
    Expected schema:
    {
      "target_brand": "ExampleCorp",
      "target_domain": "example.com",
      "competitors": ["comp1.com", "comp2.com"],
      "samples": [
        {
          "query_id": "q1",
          "query_text": "best headless cms",
          "engine": "Perplexity",
          "answer_text": "ExampleCorp offers an enterprise headless CMS...",
          "sources": ["https://example.com/cms", "https://comp1.com"]
        }
      ]
    }
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    brand = data.get("target_brand", "")
    domain = data.get("target_domain", "")
    competitors = data.get("competitors", [])
    raw_samples = data.get("samples", [])

    samples = []
    for s in raw_samples:
        samples.append(CitationQuerySample(
            query_id=str(s.get("query_id", "")),
            query_text=str(s.get("query_text", "")),
            engine=str(s.get("engine", "AI Search")),
            answer_text=str(s.get("answer_text", "")),
            sources=list(s.get("sources", []))
        ))

    return samples, brand, domain, competitors


def compare_experiments(
    before_path: str,
    after_path: str,
    target_brand: Optional[str] = None,
    target_domain: Optional[str] = None
) -> Dict[str, Any]:
    """
    Performs empirical Before / After comparison between two benchmark runs.
    """
    b_samples, b_brand, b_domain, b_comp = load_benchmark_samples(before_path)
    a_samples, a_brand, a_domain, a_comp = load_benchmark_samples(after_path)

    brand = target_brand or a_brand or b_brand
    domain = target_domain or a_domain or b_domain
    competitors = list(set(b_comp + a_comp))

    b_metrics = evaluate_citation_benchmark(b_samples, brand, domain, competitors)
    a_metrics = evaluate_citation_benchmark(a_samples, brand, domain, competitors)

    cit_delta = round(a_metrics.citation_rate_pct - b_metrics.citation_rate_pct, 1)
    brand_delta = round(a_metrics.brand_mention_rate_pct - b_metrics.brand_mention_rate_pct, 1)
    source_delta = round(a_metrics.source_selection_rate_pct - b_metrics.source_selection_rate_pct, 1)
    pos_delta = None
    if a_metrics.avg_citation_position is not None and b_metrics.avg_citation_position is not None:
        pos_delta = round(a_metrics.avg_citation_position - b_metrics.avg_citation_position, 2)

    return {
        "target_brand": brand,
        "target_domain": domain,
        "before": b_metrics.to_dict(),
        "after": a_metrics.to_dict(),
        "deltas": {
            "citation_rate_pct": cit_delta,
            "brand_mention_rate_pct": brand_delta,
            "source_selection_rate_pct": source_delta,
            "avg_citation_position": pos_delta
        },
        "epistemic_disclaimer": (
            "NOTICE: Observed score and citation rate differences reflect benchmark query sample "
            "correlations and cannot guarantee causal ranking outcomes across dynamic production AI search models."
        )
    }


def render_experiment_markdown(comp: Dict[str, Any]) -> str:
    """Formats experiment comparison into publication-ready markdown."""
    md = []
    md.append("# AI Citation Benchmark: Before / After Empirical Comparison")
    md.append("")
    md.append(f"> **Target Domain**: `{comp['target_domain']}`  ")
    md.append(f"> **Target Brand**: `{comp['target_brand']}`  ")
    md.append(f"> **Methodology Tier**: `Tier C (Empirical Research)`  ")
    md.append("")
    md.append("## Benchmark Summary")
    md.append("")
    md.append("| Metric | Before Optimization | After Optimization | Delta |")
    md.append("| :--- | :--- | :--- | :--- |")

    b = comp["before"]
    a = comp["after"]
    d = comp["deltas"]

    c_sign = "+" if d["citation_rate_pct"] > 0 else ""
    m_sign = "+" if d["brand_mention_rate_pct"] > 0 else ""
    s_sign = "+" if d["source_selection_rate_pct"] > 0 else ""

    md.append(f"| **Citation Rate** | {b['citation_rate_pct']}% ({b['cited_queries']}/{b['total_queries']}) | {a['citation_rate_pct']}% ({a['cited_queries']}/{a['total_queries']}) | **{c_sign}{d['citation_rate_pct']}%** |")
    md.append(f"| **Brand Mention Rate** | {b['brand_mention_rate_pct']}% | {a['brand_mention_rate_pct']}% | **{m_sign}{d['brand_mention_rate_pct']}%** |")
    md.append(f"| **Source Selection Rate (Top-3)** | {b['source_selection_rate_pct']}% | {a['source_selection_rate_pct']}% | **{s_sign}{d['source_selection_rate_pct']}%** |")

    b_pos = f"#{b['avg_citation_position']}" if b['avg_citation_position'] else "N/A"
    a_pos = f"#{a['avg_citation_position']}" if a['avg_citation_position'] else "N/A"
    p_delta_str = f"{d['avg_citation_position']:+.2f}" if d['avg_citation_position'] is not None else "N/A"
    md.append(f"| **Avg Citation Rank** | {b_pos} | {a_pos} | {p_delta_str} |")
    md.append("")

    md.append("> [!NOTE]")
    md.append(f"> {comp['epistemic_disclaimer']}")
    md.append("")

    return "\n".join(md)
