"""
Deterministic signal analyzers for ultimate-seo-geo v3.0.0.
"""

from .http_analyzer import analyze_target_http
from .html_analyzer import analyze_target_html
from .robots_simulator import parse_robots_txt, is_allowed, simulate_ai_crawlers, RobotsData
from .schema_analyzer import analyze_json_ld, SchemaAnalysisResult, SchemaFinding
from .content_analyzer import analyze_content, ContentAnalysisResult, ContentFinding
from .sitemap_analyzer import parse_sitemap_xml, SitemapAnalysisResult
from .eeat_analyzer import analyze_eeat, EeatAnalysisResult, EeatFinding
from .freshness_analyzer import analyze_freshness, FreshnessAnalysisResult, FreshnessFinding
from .similarity import compute_simhash, hamming_distance, jaccard_similarity

__all__ = [
    "analyze_target_http",
    "analyze_target_html",
    "parse_robots_txt",
    "is_allowed",
    "simulate_ai_crawlers",
    "RobotsData",
    "analyze_json_ld",
    "SchemaAnalysisResult",
    "SchemaFinding",
    "analyze_content",
    "ContentAnalysisResult",
    "ContentFinding",
    "parse_sitemap_xml",
    "SitemapAnalysisResult",
]
