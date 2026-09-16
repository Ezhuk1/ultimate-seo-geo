"""
RFC 9309 compliant robots.txt parser and AI crawler access simulator.

Implements:
- Directives grouping by User-agent
- Path matching with * (wildcard) and $ (end-of-string) per RFC 9309 Section 2.2.2
- Longest-match rule precedence (Allow wins on tie)
- Simulation for major AI search and training crawlers
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


KNOWN_AI_CRAWLERS = [
    ("GPTBot", "OpenAI Search & Training Crawler"),
    ("ChatGPT-User", "OpenAI Search Real-time Browser"),
    ("ClaudeBot", "Anthropic Web Crawler"),
    ("PerplexityBot", "Perplexity AI Search Crawler"),
    ("Google-Extended", "Google Gemini / Vertex AI Training"),
    ("Amazonbot", "Amazon Alexa & AI Crawler"),
    ("Bytespider", "ByteDance AI Crawler"),
    ("CCBot", "Common Crawl Dataset Crawler"),
]

DEFAULT_TEST_PATHS = ["/", "/robots.txt", "/sitemap.xml", "/api/", "/admin/", "/private/"]


@dataclass
class Rule:
    allow: bool
    pattern: str
    regex: re.Pattern
    length: int


@dataclass
class UserAgentGroup:
    user_agents: List[str] = field(default_factory=list)
    rules: List[Rule] = field(default_factory=list)


@dataclass
class RobotsData:
    raw_content: str
    groups: List[UserAgentGroup] = field(default_factory=list)
    sitemaps: List[str] = field(default_factory=list)
    disallowed_paths: List[str] = field(default_factory=list)


def _pattern_to_regex(pattern: str) -> re.Pattern:
    """Converts robots.txt path pattern to compiled regex according to RFC 9309."""
    if not pattern:
        return re.compile(r"^.*$")
    
    # Escape regex special characters except * and $
    escaped = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            escaped.append(".*")
        elif char == "$" and i == len(pattern) - 1:
            escaped.append("$")
        else:
            escaped.append(re.escape(char))
        i += 1
    
    regex_str = "^" + "".join(escaped)
    if not pattern.endswith("$"):
        regex_str += ".*"
    return re.compile(regex_str)


def parse_robots_txt(content: str) -> RobotsData:
    """Parses robots.txt content into structured AST."""
    data = RobotsData(raw_content=content)
    lines = content.splitlines()

    current_agents: List[str] = []
    current_rules: List[Rule] = []

    def commit_current_group():
        nonlocal current_agents, current_rules
        if current_agents:
            group = UserAgentGroup(
                user_agents=[a.lower() for a in current_agents],
                rules=list(current_rules)
            )
            data.groups.append(group)
            current_agents = []
            current_rules = []

    for raw_line in lines:
        line = raw_line.strip()
        # Remove comments
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if not line:
            continue

        if ":" not in line:
            continue

        directive, _, value = line.partition(":")
        directive = directive.strip().lower()
        value = value.strip()

        if directive == "user-agent":
            # If we were already collecting rules for a previous group, commit it
            if current_rules:
                commit_current_group()
            current_agents.append(value)
        elif directive in ("allow", "disallow"):
            if not current_agents:
                # Directives before any user-agent are ignored per RFC
                continue
            is_allow = (directive == "allow")
            if not value and directive == "disallow":
                # 'Disallow: ' means everything is allowed
                is_allow = True
                value = "/"
            
            rule = Rule(
                allow=is_allow,
                pattern=value,
                regex=_pattern_to_regex(value),
                length=len(value)
            )
            current_rules.append(rule)
            if not is_allow and value and value != "/":
                data.disallowed_paths.append(value)
        elif directive == "sitemap":
            if value and value not in data.sitemaps:
                data.sitemaps.append(value)

    commit_current_group()
    return data


def is_allowed(robots_data: RobotsData, user_agent: str, path: str) -> Tuple[bool, Optional[Rule], str]:
    """
    Evaluates RFC 9309 access rule for a specific user-agent and path.
    Returns: (is_allowed, matching_rule, reason)
    """
    ua_clean = user_agent.strip().lower()
    
    # 1. Find matching group for user_agent
    matched_group: Optional[UserAgentGroup] = None
    wildcard_group: Optional[UserAgentGroup] = None

    for group in robots_data.groups:
        if ua_clean in group.user_agents:
            matched_group = group
            break
        if "*" in group.user_agents:
            wildcard_group = group

    target_group = matched_group or wildcard_group

    if not target_group or not target_group.rules:
        return True, None, "No matching group or rules found (default allow)"

    # 2. Evaluate all rules in group using RFC 9309 longest match
    best_rule: Optional[Rule] = None
    best_length = -1

    for rule in target_group.rules:
        if rule.regex.match(path):
            if rule.length > best_length:
                best_length = rule.length
                best_rule = rule
            elif rule.length == best_length:
                # If equal length, Allow takes precedence
                if rule.allow:
                    best_rule = rule

    if best_rule is None:
        return True, None, f"No matching rule in group for path '{path}' (default allow)"

    status_str = "Allowed" if best_rule.allow else "Disallowed"
    return best_rule.allow, best_rule, f"{status_str} by rule: {'Allow' if best_rule.allow else 'Disallow'}: {best_rule.pattern}"


def simulate_ai_crawlers(robots_data: RobotsData, test_paths: Optional[List[str]] = None) -> Dict[str, dict]:
    """
    Simulates access for key AI search and training crawlers.
    Returns structured simulation report.
    """
    paths = test_paths or DEFAULT_TEST_PATHS
    simulation_results = {}

    for bot_name, bot_desc in KNOWN_AI_CRAWLERS:
        path_results = {}
        for path in paths:
            allowed, rule, reason = is_allowed(robots_data, bot_name, path)
            path_results[path] = {
                "allowed": allowed,
                "rule": rule.pattern if rule else None,
                "reason": reason
            }
        
        # Check root access
        root_access = path_results.get("/", {}).get("allowed", True)
        simulation_results[bot_name] = {
            "description": bot_desc,
            "root_allowed": root_access,
            "path_access": path_results
        }

    return simulation_results
