"""
Configuration management for ultimate-seo-geo v3.8.1.

Loads optional configuration from ultimate-seo-geo.json or custom path.
Provides sensible production defaults without requiring external dependencies.
"""

from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class ThresholdConfig:
    technical_score: int = 80
    geo_score: int = 70
    coverage_pct: float = 60.0
    security_score: int = 75


@dataclass
class CrawlConfig:
    seed_url: str = ""
    max_pages: int = 50
    max_depth: int = 3
    delay_seconds: float = 0.05
    rate_limit_delay: float = 0.05
    timeout: float = 10.0
    max_response_bytes: int = 5_000_000  # 5 MB
    respect_robots: bool = True
    allowed_domains: Optional[List[str]] = None
    user_agent: str = "UltimateSeoGeoCrawler/3.8.1"

    def __post_init__(self):
        # Synchronize delay_seconds and rate_limit_delay
        if self.rate_limit_delay != 0.05 and self.delay_seconds == 0.05:
            self.delay_seconds = self.rate_limit_delay
        elif self.delay_seconds != 0.05:
            self.rate_limit_delay = self.delay_seconds


@dataclass
class EngineConfig:
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    disabled_rules: List[str] = field(default_factory=list)
    strict_mode: bool = False

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> EngineConfig:
        """Loads configuration from specified file or searches workspace."""
        path_to_try: Optional[Path] = None
        if config_path:
            p = Path(config_path)
            if p.exists():
                path_to_try = p
        else:
            candidates = [
                Path("ultimate-seo-geo.json"),
                Path(".ultimate-seo-geo.json"),
                Path(__file__).resolve().parent.parent / "ultimate-seo-geo.json"
            ]
            for c in candidates:
                if c.exists():
                    path_to_try = c
                    break

        if not path_to_try:
            return cls()

        try:
            with open(path_to_try, "r", encoding="utf-8") as f:
                data = json.load(f)

            t_data = data.get("thresholds", {})
            thresholds = ThresholdConfig(
                technical_score=int(t_data.get("technical_score", 80)),
                geo_score=int(t_data.get("geo_score", 70)),
                coverage_pct=float(t_data.get("coverage_pct", 60.0)),
                security_score=int(t_data.get("security_score", 75))
            )

            c_data = data.get("crawl", {})
            delay = float(c_data.get("delay_seconds", c_data.get("rate_limit_delay", 0.05)))
            crawl = CrawlConfig(
                max_pages=int(c_data.get("max_pages", 50)),
                max_depth=int(c_data.get("max_depth", 3)),
                delay_seconds=delay,
                rate_limit_delay=delay,
                timeout=float(c_data.get("timeout", 10.0)),
                max_response_bytes=int(c_data.get("max_response_bytes", 5_000_000)),
                respect_robots=bool(c_data.get("respect_robots", True)),
                user_agent=str(c_data.get("user_agent", "UltimateSeoGeoCrawler/3.8.1"))
            )

            return cls(
                thresholds=thresholds,
                crawl=crawl,
                disabled_rules=list(data.get("disabled_rules", [])),
                strict_mode=bool(data.get("strict_mode", False))
            )
        except Exception:
            return cls()
