"""
HTTP/HTTPS and local file observer.
Collects raw, immutable observations with SHA-256 provenance using standard library.
"""

import hashlib
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def analyze_target_http(target: str, timeout: float = 10.0) -> dict[str, Any]:
    """
    Fetches the target URL or reads the local file, capturing raw HTTP metadata
    and computing SHA-256 provenance hash.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Check if target is a local file
    local_path = Path(target)
    if not target.startswith(("http://", "https://")) and local_path.exists():
        try:
            raw_bytes = local_path.read_bytes()
            content = raw_bytes.decode("utf-8", errors="replace")
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            return {
                "target": str(local_path.resolve()),
                "is_local": True,
                "status_code": 200,
                "headers": {
                    "content-type": "text/html; charset=utf-8",
                    "content-length": str(len(raw_bytes)),
                },
                "x_robots_tag": None,
                "x_robots_raw": [],
                "x_robots_directives": [],
                "x_robots_bot_directives": {},
                "redirect_chain": [],
                "response_time_ms": 1.0,
                "tls_valid": True,
                "content_sha256": content_hash,
                "raw_content": content,
                "timestamp": timestamp,
                "error": None,
            }
        except Exception as e:
            return {
                "target": target,
                "is_local": True,
                "status_code": 500,
                "headers": {},
                "redirect_chain": [],
                "response_time_ms": 0.0,
                "tls_valid": False,
                "content_sha256": "",
                "raw_content": "",
                "timestamp": timestamp,
                "error": f"Failed to read local file: {e}",
            }

    # Otherwise treat as remote HTTP/HTTPS target
    if not target.startswith(("http://", "https://")):
        target = f"https://{target}"

    redirect_chain = []

    class RedirectTracker(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirect_chain.append({"code": code, "from": req.full_url, "to": newurl})
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(RedirectTracker)
    # Realistic User-Agent to avoid generic bot-blocks
    req = urllib.request.Request(
        target,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; UltimateSeoGeoEngine/2.0; +https://github.com/Ezhuk1/ultimate-seo-geo)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    start_time = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            raw_bytes = resp.read()
            content = raw_bytes.decode("utf-8", errors="replace")
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            
            # Extract all X-Robots-Tag headers preserving multiple occurrences
            x_robots_raw = []
            if hasattr(resp.headers, "get_all"):
                x_robots_raw = resp.headers.get_all("x-robots-tag") or []
            elif "x-robots-tag" in headers:
                x_robots_raw = [headers["x-robots-tag"]]

            x_global_dirs = set()
            x_bot_dirs = {}
            for h_val in x_robots_raw:
                for part in h_val.split(","):
                    p = part.strip().lower()
                    if not p:
                        continue
                    if ":" in p:
                        b_name, b_dir = p.split(":", 1)
                        x_bot_dirs.setdefault(b_name.strip(), []).append(b_dir.strip())
                    else:
                        x_global_dirs.add(p)

            return {
                "target": target,
                "final_url": resp.geturl(),
                "is_local": False,
                "status_code": resp.status,
                "headers": headers,
                "x_robots_tag": ", ".join(x_robots_raw) if x_robots_raw else None,
                "x_robots_raw": x_robots_raw,
                "x_robots_directives": sorted(list(x_global_dirs)),
                "x_robots_bot_directives": x_bot_dirs,
                "redirect_chain": redirect_chain,
                "response_time_ms": round(elapsed_ms, 2),
                "tls_valid": target.startswith("https://"),
                "content_sha256": content_hash,
                "raw_content": content,
                "timestamp": timestamp,
                "error": None,
            }
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        raw_bytes = e.read() if hasattr(e, "read") else b""
        content = raw_bytes.decode("utf-8", errors="replace")
        content_hash = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes else ""
        headers = {k.lower(): v for k, v in e.headers.items()} if hasattr(e, "headers") and e.headers else {}

        x_robots_raw = []
        if hasattr(e.headers, "get_all"):
            x_robots_raw = e.headers.get_all("x-robots-tag") or []
        elif "x-robots-tag" in headers:
            x_robots_raw = [headers["x-robots-tag"]]

        x_global_dirs = set()
        x_bot_dirs = {}
        for h_val in x_robots_raw:
            for part in h_val.split(","):
                p = part.strip().lower()
                if not p:
                    continue
                if ":" in p:
                    b_name, b_dir = p.split(":", 1)
                    x_bot_dirs.setdefault(b_name.strip(), []).append(b_dir.strip())
                else:
                    x_global_dirs.add(p)

        return {
            "target": target,
            "final_url": target,
            "is_local": False,
            "status_code": e.code,
            "headers": headers,
            "x_robots_tag": ", ".join(x_robots_raw) if x_robots_raw else None,
            "x_robots_raw": x_robots_raw,
            "x_robots_directives": sorted(list(x_global_dirs)),
            "x_robots_bot_directives": x_bot_dirs,
            "redirect_chain": redirect_chain,
            "response_time_ms": round(elapsed_ms, 2),
            "tls_valid": target.startswith("https://"),
            "content_sha256": content_hash,
            "raw_content": content,
            "timestamp": timestamp,
            "error": f"HTTP Error {e.code}: {e.reason}",
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "target": target,
            "is_local": False,
            "status_code": 0,
            "headers": {},
            "redirect_chain": redirect_chain,
            "response_time_ms": round(elapsed_ms, 2),
            "tls_valid": False,
            "content_sha256": "",
            "raw_content": "",
            "timestamp": timestamp,
            "error": str(e),
        }
