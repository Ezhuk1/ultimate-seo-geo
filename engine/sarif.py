"""
SARIF v2.1.0 Exporter for Ultimate SEO/GEO Engine.

Generates OASIS SARIF compliant JSON for GitHub Code Scanning, GitLab CI,
and automated code quality pipelines.
"""

from __future__ import annotations
import json
from typing import Dict, Any, List
from .ledger import EvidenceLedger, STATUS_CRITICAL, STATUS_WARNING, STATUS_INFO


def _severity_to_sarif_level(severity: str) -> str:
    if severity == STATUS_CRITICAL:
        return "error"
    elif severity == STATUS_WARNING:
        return "warning"
    return "note"


def generate_sarif_report(ledger: EvidenceLedger) -> Dict[str, Any]:
    """
    Transforms an EvidenceLedger into an OASIS SARIF v2.1.0 document.
    """
    target_uri = getattr(ledger, "target", None) or ledger.metadata.get("target") or "https://example.com"
    rules_dict: Dict[str, Dict[str, Any]] = {}
    results: List[Dict[str, Any]] = []

    for ev in ledger.evidence:
        if ev.status not in (STATUS_CRITICAL, STATUS_WARNING, STATUS_INFO):
            continue

        sarif_level = _severity_to_sarif_level(ev.status)

        if ev.rule_id not in rules_dict:
            rules_dict[ev.rule_id] = {
                "id": ev.rule_id,
                "name": ev.title.replace(" ", ""),
                "shortDescription": {"text": ev.title},
                "defaultConfiguration": {"level": sarif_level},
                "properties": {
                    "category": ev.category,
                    "confidence": ev.confidence
                }
            }

        result_item = {
            "ruleId": ev.rule_id,
            "level": sarif_level,
            "message": {"text": ev.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": target_uri
                        },
                        "region": {
                            "startLine": 1,
                            "startColumn": 1
                        }
                    }
                }
            ],
            "properties": {
                "status": ev.status,
                "observed": str(ev.observed) if ev.observed is not None else None,
                "expected": str(ev.expected) if ev.expected is not None else None
            }
        }
        results.append(result_item)

    sarif_doc = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ultimate-seo-geo",
                        "version": "3.0.0",
                        "informationUri": "https://github.com/Ezhuk1/ultimate-seo-geo",
                        "rules": list(rules_dict.values())
                    }
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": True
                    }
                ]
            }
        ]
    }
    return sarif_doc


def format_sarif_json(ledger: EvidenceLedger, indent: int = 2) -> str:
    """Returns SARIF report formatted as a JSON string."""
    doc = generate_sarif_report(ledger)
    return json.dumps(doc, indent=indent, ensure_ascii=False)
