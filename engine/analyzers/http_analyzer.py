"""
HTTP/HTTPS and local file observer.
Collects raw, immutable observations with SHA-256 provenance using standard library.
"""

import hashlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HAS_BROTLI = False
try:
    import brotli  # type: ignore
    HAS_BROTLI = True
except ImportError:
    try:
        import brotlicffi as brotli  # type: ignore
        HAS_BROTLI = True
    except ImportError:
        pass

from engine.security_utils import is_safe_target_url


def _detect_and_decode(raw_bytes: bytes, content_type_header: str | None) -> tuple[str, str]:
    """
    Detects charset from header or HTML <meta> tags in first 1024 bytes,
    and returns (decoded_text, detected_charset).
    """
    detected = None
    if content_type_header:
        m = re.search(r'charset=["\']?([a-zA-Z0-9_\-]+)', content_type_header, re.IGNORECASE)
        if m:
            detected = m.group(1).strip().lower()

    if not detected and raw_bytes:
        prefix = raw_bytes[:1024].decode("latin-1", errors="replace")
        m_meta = re.search(r'<meta[^>]+charset=["\']?([a-zA-Z0-9_\-]+)', prefix, re.IGNORECASE)
        if m_meta:
            detected = m_meta.group(1).strip().lower()
        else:
            m_equiv = re.search(r'<meta[^>]+http-equiv=["\']?content-type["\']?[^>]+content=["\'][^"\']*charset=([a-zA-Z0-9_\-]+)', prefix, re.IGNORECASE)
            if m_equiv:
                detected = m_equiv.group(1).strip().lower()

    if detected:
        try:
            return raw_bytes.decode(detected, errors="replace"), detected
        except (LookupError, UnicodeDecodeError):
            pass

    # Try utf-8
    try:
        return raw_bytes.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    # Try windows-1251
    try:
        return raw_bytes.decode("windows-1251"), "windows-1251"
    except UnicodeDecodeError:
        pass

    return raw_bytes.decode("latin-1", errors="replace"), detected or "latin-1"


def _extract_header_canonical(headers_obj: Any, headers_dict: dict[str, str]) -> str | None:
    link_headers = []
    if hasattr(headers_obj, "get_all"):
        link_headers = headers_obj.get_all("link") or []
    elif "link" in headers_dict:
        link_headers = [headers_dict["link"]]

    for lh in link_headers:
        for part in lh.split(","):
            m = re.search(r'<([^>]+)>;\s*rel=["\']?canonical["\']?', part, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return None


def _is_challenge_page(status_code: int, headers: dict[str, str], raw_content: str) -> bool:
    # Dedicated Cloudflare mitigation header
    if headers.get("cf-mitigated") == "challenge":
        return True
    content_lower = raw_content[:4096].lower() if raw_content else ""
    challenge_indicators = (
        "cf-browser-verification",
        "cf-challenge",
        "turnstile",
        "just a moment...",
        "attention required! | cloudflare",
        "cloudflare ray id",
        "please wait while your request is being verified",
        "verify you are human",
    )
    return any(ind in content_lower for ind in challenge_indicators)


def _is_soft_404(status_code: int, raw_content: str) -> bool:
    if status_code != 200 or not raw_content:
        return False
    lower_content = raw_content[:8192].lower()
    patterns = [
        "404 not found",
        "page not found",
        "document not found",
        "страница не найдена",
        "запрашиваемая страница не найдена",
        "404 ошибка",
        "error 404",
        "not found 404",
    ]
    exemption_words = ("how to", "как исправить", "fixing", "tutorial", "guide to", "руководство")

    m_title = re.search(r'<title[^>]*>(.*?)</title>', lower_content, re.DOTALL)
    if m_title:
        title_val = m_title.group(1).strip()
        if any(p in title_val for p in patterns) and not any(ex in title_val for ex in exemption_words):
            return True

    m_h1 = re.search(r'<h1[^>]*>(.*?)</h1>', lower_content, re.DOTALL)
    if m_h1:
        h1_val = m_h1.group(1).strip()
        if any(p in h1_val for p in patterns) and not any(ex in h1_val for ex in exemption_words):
            return True

    return False


def _has_redirect_loop(redirect_chain: list[dict[str, Any]]) -> bool:
    if len(redirect_chain) > 5:
        return True
    seen_urls = set()
    for hop in redirect_chain:
        from_url = hop.get("from")
        to_url = hop.get("to")
        if from_url and from_url in seen_urls:
            return True
        if to_url and to_url in seen_urls:
            return True
        if from_url:
            seen_urls.add(from_url)
    return False


def analyze_target_http(target: str, timeout: float = 10.0, user_agent: str | None = None) -> dict[str, Any]:
    """
    Fetches the target URL or reads the local file, capturing raw HTTP metadata
    and computing SHA-256 provenance hash.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    ua = user_agent or "Mozilla/5.0 (compatible; UltimateSeoGeoEngine/3.2.0; +https://github.com/Ezhuk1/ultimate-seo-geo)"

    # Check if target is a local file
    local_path = Path(target)
    if not target.startswith(("http://", "https://")) and local_path.exists():
        try:
            raw_bytes = local_path.read_bytes()
            content, detected_charset = _detect_and_decode(raw_bytes, None)
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            return {
                "target": str(local_path.resolve()),
                "final_url": str(local_path.resolve()),
                "is_local": True,
                "status_code": 200,
                "headers": {
                    "content-type": f"text/html; charset={detected_charset}",
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
                "detected_charset": detected_charset,
                "header_canonical": None,
                "content_encoding": None,
                "body_bytes_len": len(raw_bytes),
                "is_challenge_page": False,
                "cache_control": None,
                "expires": None,
                "hsts": None,
                "content_language": None,
                "last_modified": None,
                "etag": None,
                "is_soft_404": _is_soft_404(200, content),
                "has_redirect_loop": False,
                "timestamp": timestamp,
                "error": None,
            }
        except Exception as e:
            return {
                "target": target,
                "final_url": target,
                "is_local": True,
                "status_code": 500,
                "headers": {},
                "x_robots_tag": None,
                "x_robots_raw": [],
                "x_robots_directives": [],
                "x_robots_bot_directives": {},
                "redirect_chain": [],
                "response_time_ms": 0.0,
                "tls_valid": False,
                "content_sha256": "",
                "raw_content": "",
                "detected_charset": "utf-8",
                "header_canonical": None,
                "content_encoding": None,
                "body_bytes_len": 0,
                "is_challenge_page": False,
                "cache_control": None,
                "expires": None,
                "hsts": None,
                "content_language": None,
                "last_modified": None,
                "etag": None,
                "is_soft_404": False,
                "has_redirect_loop": False,
                "timestamp": timestamp,
                "error": f"Failed to read local file: {e}",
            }

    # Otherwise treat as remote HTTP/HTTPS target
    if not target.startswith(("http://", "https://")):
        target = f"https://{target}"

    # Enforce SSRF validation on target
    is_safe, ssrf_reason = is_safe_target_url(target)
    if not is_safe:
        return {
            "target": target,
            "final_url": target,
            "is_local": False,
            "status_code": 403,
            "headers": {},
            "x_robots_tag": None,
            "x_robots_raw": [],
            "x_robots_directives": [],
            "x_robots_bot_directives": {},
            "redirect_chain": [],
            "response_time_ms": 0.0,
            "tls_valid": False,
            "content_sha256": "",
            "raw_content": "",
            "detected_charset": "utf-8",
            "header_canonical": None,
            "content_encoding": None,
            "body_bytes_len": 0,
            "is_challenge_page": False,
            "cache_control": None,
            "expires": None,
            "hsts": None,
            "content_language": None,
            "last_modified": None,
            "etag": None,
            "is_soft_404": False,
            "has_redirect_loop": False,
            "timestamp": timestamp,
            "error": f"SSRF Protection Blocked Request: {ssrf_reason}",
        }

    redirect_chain = []

    class SafeRedirectTracker(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            resolved_newurl = urllib.parse.urljoin(req.full_url, newurl)
            is_hop_safe, hop_reason = is_safe_target_url(resolved_newurl)
            if not is_hop_safe:
                raise urllib.error.HTTPError(
                    resolved_newurl,
                    403,
                    f"SSRF Protection Blocked Redirect: destination '{resolved_newurl}' is forbidden ({hop_reason})",
                    headers,
                    fp,
                )
            redirect_chain.append({"code": code, "from": req.full_url, "to": resolved_newurl})
            return super().redirect_request(req, fp, code, msg, headers, resolved_newurl)

    opener = urllib.request.build_opener(SafeRedirectTracker)
    accept_encoding = "gzip, deflate, br" if HAS_BROTLI else "gzip, deflate"
    req = urllib.request.Request(
        target,
        headers={
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": accept_encoding,
        },
    )

    start_time = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            raw_bytes = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            c_encoding = headers.get("content-encoding", "").lower()
            payload_bytes = raw_bytes
            if "br" in c_encoding:
                if HAS_BROTLI:
                    try:
                        payload_bytes = brotli.decompress(raw_bytes)
                    except Exception:
                        payload_bytes = raw_bytes
            elif "gzip" in c_encoding:
                import gzip
                try:
                    payload_bytes = gzip.decompress(raw_bytes)
                except Exception:
                    payload_bytes = raw_bytes
            elif "deflate" in c_encoding:
                import zlib
                try:
                    payload_bytes = zlib.decompress(raw_bytes)
                except Exception:
                    payload_bytes = raw_bytes
            ct_header = headers.get("content-type")
            content, detected_charset = _detect_and_decode(payload_bytes, ct_header)
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            header_canonical = _extract_header_canonical(resp.headers, headers)
            is_challenge = _is_challenge_page(resp.status, headers, content)
            
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
                "detected_charset": detected_charset,
                "header_canonical": header_canonical,
                "content_encoding": headers.get("content-encoding"),
                "body_bytes_len": len(raw_bytes),
                "is_challenge_page": is_challenge,
                "cache_control": headers.get("cache-control"),
                "expires": headers.get("expires"),
                "hsts": headers.get("strict-transport-security"),
                "content_language": headers.get("content-language"),
                "last_modified": headers.get("last-modified"),
                "etag": headers.get("etag"),
                "is_soft_404": _is_soft_404(resp.status, content),
                "has_redirect_loop": _has_redirect_loop(redirect_chain),
                "timestamp": timestamp,
                "error": None,
            }
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        raw_bytes = e.read() if hasattr(e, "read") else b""
        headers = {k.lower(): v for k, v in e.headers.items()} if hasattr(e, "headers") and e.headers else {}
        err_c_encoding = headers.get("content-encoding", "").lower()
        err_payload_bytes = raw_bytes
        if "br" in err_c_encoding:
            if HAS_BROTLI:
                try:
                    err_payload_bytes = brotli.decompress(raw_bytes)
                except Exception:
                    err_payload_bytes = raw_bytes
        elif "gzip" in err_c_encoding:
            import gzip
            try:
                err_payload_bytes = gzip.decompress(raw_bytes)
            except Exception:
                err_payload_bytes = raw_bytes
        elif "deflate" in err_c_encoding:
            import zlib
            try:
                err_payload_bytes = zlib.decompress(raw_bytes)
            except Exception:
                err_payload_bytes = raw_bytes
        ct_header = headers.get("content-type")
        content, detected_charset = _detect_and_decode(err_payload_bytes, ct_header)
        content_hash = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes else ""
        header_canonical = _extract_header_canonical(e.headers, headers) if hasattr(e, "headers") else None
        is_challenge = _is_challenge_page(e.code, headers, content)

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
            "detected_charset": detected_charset,
            "header_canonical": header_canonical,
            "content_encoding": headers.get("content-encoding"),
            "body_bytes_len": len(raw_bytes),
            "is_challenge_page": is_challenge,
            "cache_control": headers.get("cache-control"),
            "expires": headers.get("expires"),
            "hsts": headers.get("strict-transport-security"),
            "content_language": headers.get("content-language"),
            "last_modified": headers.get("last-modified"),
            "etag": headers.get("etag"),
            "is_soft_404": False,
            "has_redirect_loop": _has_redirect_loop(redirect_chain),
            "timestamp": timestamp,
            "error": f"HTTP Error {e.code}: {e.reason}",
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "target": target,
            "final_url": target,
            "is_local": False,
            "status_code": 0,
            "headers": {},
            "x_robots_tag": None,
            "x_robots_raw": [],
            "x_robots_directives": [],
            "x_robots_bot_directives": {},
            "redirect_chain": redirect_chain,
            "response_time_ms": round(elapsed_ms, 2),
            "tls_valid": False,
            "content_sha256": "",
            "raw_content": "",
            "detected_charset": "utf-8",
            "header_canonical": None,
            "content_encoding": None,
            "body_bytes_len": 0,
            "is_challenge_page": False,
            "cache_control": None,
            "expires": None,
            "hsts": None,
            "content_language": None,
            "last_modified": None,
            "etag": None,
            "is_soft_404": False,
            "has_redirect_loop": _has_redirect_loop(redirect_chain),
            "timestamp": timestamp,
            "error": str(e),
        }
