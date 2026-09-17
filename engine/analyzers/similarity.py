"""
Deterministic Duplicate & Near-Duplicate Content Detection Engine.

Uses standard-library hashlib to provide:
1. 64-bit SimHash for near-duplicate body text clustering.
2. Hamming distance calculation for SimHash fingerprints.
3. Shingled Jaccard similarity for token overlap.
4. Exact duplicate clustering for Titles, H1s, and Meta Descriptions.
"""

from __future__ import annotations
import hashlib
import re
from typing import List, Dict, Set, Any, Tuple


def tokenize_words(text: str) -> List[str]:
    """Tokenizes alphanumeric words, lowercased."""
    return re.findall(r'\b[a-zA-Z0-9_\u0400-\u04FF]{2,}\b', text.lower())


def get_shingles(tokens: List[str], n: int = 3) -> List[str]:
    """Generates n-gram token shingles."""
    if len(tokens) < n:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def compute_simhash(text: str, n_gram: int = 3) -> int:
    """
    Computes a 64-bit SimHash fingerprint of the given text using hashlib.md5.
    Returns 0 for empty text.
    """
    tokens = tokenize_words(text)
    shingles = get_shingles(tokens, n=n_gram)
    if not shingles:
        return 0

    v = [0] * 64
    for shingle in shingles:
        h = int(hashlib.md5(shingle.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            bit = (h >> i) & 1
            if bit:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(hash1: int, hash2: int) -> int:
    """Calculates bitwise Hamming distance between two 64-bit integer hashes."""
    x = (hash1 ^ hash2) & 0xFFFFFFFFFFFFFFFF
    dist = 0
    while x:
        dist += 1
        x &= x - 1
    return dist


def compute_jaccard(tokens1: Set[str], tokens2: Set[str]) -> float:
    """Calculates Jaccard similarity between two sets of tokens."""
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1.intersection(tokens2))
    union = len(tokens1.union(tokens2))
    return round(intersection / union, 4) if union > 0 else 0.0


def jaccard_similarity(text1: str, text2: str) -> float:
    """Convenience helper computing Jaccard word similarity between two text strings."""
    tokens1 = set(tokenize_words(text1))
    tokens2 = set(tokenize_words(text2))
    return compute_jaccard(tokens1, tokens2)


def cluster_near_duplicates(pages: List[Dict[str, Any]], max_distance: int = 3) -> List[Dict[str, Any]]:
    """Clusters pages by near-duplicate body content based on SimHash hamming distance."""
    simhashes: List[Tuple[str, int]] = []
    for p in pages:
        u = p.get("url", "")
        content = p.get("content") or p.get("text") or ""
        if content:
            sh = compute_simhash(content)
            simhashes.append((u, sh))

    clusters: List[Dict[str, Any]] = []
    visited: Set[str] = set()

    for i in range(len(simhashes)):
        u1, h1_val = simhashes[i]
        if u1 in visited or h1_val == 0:
            continue
        cluster = [u1]
        for j in range(i + 1, len(simhashes)):
            u2, h2_val = simhashes[j]
            if u2 in visited or h2_val == 0:
                continue
            if hamming_distance(h1_val, h2_val) <= max_distance:
                cluster.append(u2)
                visited.add(u2)
        if len(cluster) > 1:
            visited.add(u1)
            clusters.append({
                "representative_url": u1,
                "urls": cluster,
                "count": len(cluster)
            })
    return clusters


def find_duplicate_clusters(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Clusters pages by:
    1. Exact duplicate title
    2. Exact duplicate H1
    3. Exact duplicate meta description
    4. Near-duplicate body content (SimHash hamming distance <= 3)

    Each page in `pages` should be a dict with keys:
    - 'url': str
    - 'title': str
    - 'h1': str
    - 'description': str
    - 'content': str (or 'text')
    """
    titles: Dict[str, List[str]] = {}
    h1s: Dict[str, List[str]] = {}
    descriptions: Dict[str, List[str]] = {}
    simhashes: List[Tuple[str, int]] = []

    for p in pages:
        u = p.get("url", "")
        t = (p.get("title") or "").strip().lower()
        h = (p.get("h1") or "").strip().lower()
        d = (p.get("description") or "").strip().lower()
        content = p.get("content") or p.get("text") or ""

        if t and len(t) > 3:
            titles.setdefault(t, []).append(u)
        if h and len(h) > 3:
            h1s.setdefault(h, []).append(u)
        if d and len(d) > 10:
            descriptions.setdefault(d, []).append(u)

        if content and len(content.split()) >= 15:
            sh = compute_simhash(content)
            simhashes.append((u, sh))

    dup_titles = {k: v for k, v in titles.items() if len(v) > 1}
    dup_h1s = {k: v for k, v in h1s.items() if len(v) > 1}
    dup_descriptions = {k: v for k, v in descriptions.items() if len(v) > 1}

    # Near-duplicate body text clusters via SimHash
    content_clusters: List[Dict[str, Any]] = []
    visited: Set[str] = set()

    for i in range(len(simhashes)):
        u1, h1_val = simhashes[i]
        if u1 in visited or h1_val == 0:
            continue
        cluster = [u1]
        for j in range(i + 1, len(simhashes)):
            u2, h2_val = simhashes[j]
            if u2 in visited or h2_val == 0:
                continue
            if hamming_distance(h1_val, h2_val) <= 3:
                cluster.append(u2)
                visited.add(u2)
        if len(cluster) > 1:
            visited.add(u1)
            content_clusters.append({
                "representative_url": u1,
                "urls": cluster,
                "count": len(cluster)
            })

    return {
        "duplicate_titles": dup_titles,
        "duplicate_titles_count": len(dup_titles),
        "duplicate_h1s": dup_h1s,
        "duplicate_h1s_count": len(dup_h1s),
        "duplicate_descriptions": dup_descriptions,
        "duplicate_descriptions_count": len(dup_descriptions),
        "near_duplicate_content_clusters": content_clusters,
        "near_duplicate_clusters_count": len(content_clusters)
    }


# Alias for batch duplicate analysis
check_batch_duplicates = find_duplicate_clusters
