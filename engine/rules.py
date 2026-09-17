"""
Unified Rule Registry.

Loads and caches declarative rule specifications from rules/*.json.
Enables rule-driven scoring without hardcoded Python branching.
"""

from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class RuleDefinition:
    id: str
    name: str
    category: str
    severity: str
    impact: str
    score_weight: int
    max_penalty_cap: int
    confidence_type: str
    unknown_policy: str
    tier: str = ""
    selector: str = ""
    description: str = ""
    remediation: str = ""
    geo_points: Dict[str, int] = field(default_factory=dict)


_REGISTRY_CACHE: Optional[Dict[str, RuleDefinition]] = None


def get_rule_registry(force_reload: bool = False) -> Dict[str, RuleDefinition]:
    """
    Returns cached mapping of rule_id -> RuleDefinition.
    Loads rules/technical_rules.json, rules/schema_rules.json, rules/geo_rules.json.
    """
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None and not force_reload:
        return _REGISTRY_CACHE

    rules_dir = Path(__file__).resolve().parent.parent / "rules"
    registry: Dict[str, RuleDefinition] = {}

    rule_files = ["technical_rules.json", "schema_rules.json", "geo_rules.json"]
    for rf in rule_files:
        path = rules_dir / rf
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                category = data.get("category", "technical")
                for item in data.get("rules", []):
                    r_id = item.get("id")
                    if not r_id:
                        continue
                    rule = RuleDefinition(
                        id=r_id,
                        name=item.get("name", r_id),
                        category=item.get("category", category),
                        severity=item.get("severity", "WARNING"),
                        impact=item.get("impact", "P1"),
                        score_weight=item.get("score_weight", 10),
                        max_penalty_cap=item.get("max_penalty_cap", 25),
                        confidence_type=item.get("confidence_type", "deterministic"),
                        unknown_policy=item.get("unknown_policy", "exclude"),
                        tier=item.get("tier", ""),
                        selector=item.get("selector", ""),
                        description=item.get("description", ""),
                        remediation=item.get("remediation", ""),
                        geo_points=item.get("geo_points", {})
                    )
                    registry[r_id] = rule
        except Exception:
            pass

    _REGISTRY_CACHE = registry
    return _REGISTRY_CACHE
