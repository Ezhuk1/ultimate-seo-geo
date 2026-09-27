"""
Deterministic Project Context Manager for ultimate-seo-geo.

Provides a persistent project dossier (business overview, target audience,
key pages, competitors, and 30-day research log) across agent sessions.
Pure Python standard library with zero external dependencies.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path


DEFAULT_CONTEXT_FILENAMES = ["seo-project-context.json", ".seo-context.json"]


@dataclass
class KeyPage:
    url: str
    target_topic: str = ""
    role: str = ""  # e.g., "landing", "pricing", "guide", "comparison"

    def to_dict(self) -> Dict[str, str]:
        return {
            "url": self.url,
            "target_topic": self.target_topic,
            "role": self.role
        }


@dataclass
class ResearchLogEntry:
    timestamp: str
    summary: str
    verdict: str = ""
    mode: str = "audit"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "summary": self.summary,
            "verdict": self.verdict,
            "mode": self.mode
        }


@dataclass
class ProjectContext:
    project_name: str = ""
    domain: str = ""
    business_overview: str = ""
    target_audience: str = ""
    key_pages: List[Dict[str, str]] = field(default_factory=list)
    competitors: List[str] = field(default_factory=list)
    research_log: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: str = ""

    @classmethod
    def load(cls, path: Optional[str] = None) -> ProjectContext:
        """
        Loads project context from specified file or default locations.
        Returns a fresh instance if no file exists.
        """
        target_path: Optional[Path] = None
        if path:
            p = Path(path)
            if p.exists():
                target_path = p
        else:
            for fname in DEFAULT_CONTEXT_FILENAMES:
                p = Path(fname)
                if p.exists():
                    target_path = p
                    break

        if not target_path:
            return cls()

        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            return cls(
                project_name=str(data.get("project_name", "")),
                domain=str(data.get("domain", "")),
                business_overview=str(data.get("business_overview", "")),
                target_audience=str(data.get("target_audience", "")),
                key_pages=list(data.get("key_pages", [])),
                competitors=list(data.get("competitors", [])),
                research_log=list(data.get("research_log", [])),
                updated_at=str(data.get("updated_at", ""))
            )
        except Exception:
            return cls()

    def save(self, path: Optional[str] = None) -> str:
        """
        Saves project context to file. Defaults to 'seo-project-context.json'.
        """
        out_path = path or "seo-project-context.json"
        self.updated_at = datetime.now(timezone.utc).isoformat()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return out_path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "domain": self.domain,
            "business_overview": self.business_overview,
            "target_audience": self.target_audience,
            "key_pages": self.key_pages,
            "competitors": self.competitors,
            "research_log": self.research_log,
            "updated_at": self.updated_at
        }

    def add_key_page(self, url: str, target_topic: str = "", role: str = "") -> None:
        """Adds or updates a key page in project context."""
        clean_url = url.strip()
        if not clean_url:
            return
        for p in self.key_pages:
            if p.get("url") == clean_url:
                if target_topic:
                    p["target_topic"] = target_topic
                if role:
                    p["role"] = role
                return
        self.key_pages.append({
            "url": clean_url,
            "target_topic": target_topic,
            "role": role
        })

    def add_competitor(self, domain_or_name: str) -> None:
        """Adds a competitor if not already present."""
        clean = domain_or_name.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
        if clean and clean not in [c.lower() for c in self.competitors]:
            self.competitors.append(clean)

    def append_research_log(self, summary: str, verdict: str = "", mode: str = "audit") -> None:
        """Appends a new research log entry with current timestamp."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary.strip(),
            "verdict": verdict.strip(),
            "mode": mode
        }
        self.research_log.append(entry)

    def get_recent_research(self, topic_query: str, max_age_days: int = 30) -> Optional[Dict[str, Any]]:
        """
        Checks if research matching topic_query ran within the last max_age_days.
        Returns matching log entry if fresh, or None.
        """
        if not self.research_log or not topic_query:
            return None

        q_lower = topic_query.lower()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_age_days)

        for entry in reversed(self.research_log):
            summary = entry.get("summary", "").lower()
            if q_lower in summary:
                ts_str = entry.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts >= cutoff:
                        return entry
                except Exception:
                    continue
        return None
