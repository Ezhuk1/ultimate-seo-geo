"""
Security utilities and SSRF prevention guards for ultimate-seo-geo v3.8.1.
Protects against SSRF, cloud metadata access, DNS rebinding, and private network exploitation.
"""

from __future__ import annotations
import ipaddress
import socket
from typing import Tuple
from urllib.parse import urlsplit


def is_safe_target_url(url: str) -> Tuple[bool, str]:
    """
    Validates a target or redirect URL against SSRF and protocol exploits.
    Rejects:
    - Non-HTTP/HTTPS schemes (file://, ftp://, gopher://, etc.)
    - Loopback addresses (127.0.0.0/8, ::1, localhost)
    - RFC 1918 private networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local and cloud metadata addresses (169.254.0.0/16, fe80::/10)
    - Carrier-grade NAT (100.64.0.0/10)
    - IPv6 Unique Local (fc00::/7)
    - IPv4-mapped IPv6 equivalents (::ffff:127.0.0.1, etc.)
    - Reserved and unspecified addresses (0.0.0.0/8, ::/128)
    """
    if not url or not isinstance(url, str):
        return False, "Target URL must be a non-empty string"

    clean_url = url.strip()
    try:
        parsed = urlsplit(clean_url)
    except Exception as e:
        return False, f"Malformed URL syntax: {e}"

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False, f"Insecure or invalid URI scheme '{scheme}' (only HTTP/HTTPS permitted)"

    netloc = parsed.netloc
    if not netloc:
        return False, "Missing hostname in target URL"

    # Extract hostname via parsed.hostname: strips port, brackets and — critically —
    # userinfo ("user@host"), which netloc.split(":") left in place and let
    # "http://x@127.0.0.1/" slip through when DNS lookup failed.
    hostname = (parsed.hostname or "").strip().lower()

    if not hostname:
        return False, "Empty hostname in target URL"

    # Quick check for known loopback/local names. Covers trailing-dot FQDN
    # ("localhost.") and the whole *.localhost subdomain space, which are
    # resolved to loopback by some OS resolvers without leaving the host.
    _host_core = hostname.rstrip(".")
    if hostname in ("localhost", "local", "127.0.0.1", "::1", "0.0.0.0") or _host_core == "localhost" or _host_core.endswith(".localhost"):
        return False, f"Destination '{hostname}' is a forbidden loopback target (SSRF prevention)"

    # Cloud metadata domains and internal private TLDs (RFC 6762 / RFC 8375)
    METADATA_HOSTS = {
        "metadata.google.internal",
        "metadata.google",
        "instance-data",
        "metadata.azure.com",
    }
    if _host_core in METADATA_HOSTS or any(_host_core.endswith("." + m) for m in METADATA_HOSTS):
        return False, f"Destination '{hostname}' is a forbidden cloud metadata endpoint (SSRF block)"

    INTERNAL_TLDS = (".internal", ".local", ".lan", ".corp", ".home", ".onion")
    if _host_core.endswith(INTERNAL_TLDS):
        return False, f"Destination '{hostname}' uses a private or internal TLD (SSRF block)"

    def check_ip_object(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> Tuple[bool, str]:
        if ip_obj.is_loopback:
            return False, f"IP {ip_obj} is a loopback address"
        if ip_obj.is_private:
            return False, f"IP {ip_obj} is a private RFC network address"
        if ip_obj.is_link_local:
            return False, f"IP {ip_obj} is a link-local / cloud metadata address"
        if ip_obj.is_unspecified:
            return False, f"IP {ip_obj} is an unspecified address"
        if ip_obj.is_reserved:
            return False, f"IP {ip_obj} is a reserved address"
        if ip_obj.is_multicast:
            return False, f"IP {ip_obj} is a multicast address"

        # Check IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
        if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
            mapped_ipv4 = ip_obj.ipv4_mapped
            return check_ip_object(mapped_ipv4)

        # Carrier-grade NAT check (100.64.0.0/10)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            cgnat = ipaddress.ip_network("100.64.0.0/10")
            if ip_obj in cgnat:
                return False, f"IP {ip_obj} is within Carrier-Grade NAT (RFC 6598)"

        return True, "OK"

    def parse_alternative_ipv4(host: str) -> ipaddress.IPv4Address | None:
        """Parses alternative IPv4 notations: decimal integer, hex, octal, short dotted."""
        if host.isdigit():
            try:
                val = int(host)
                if 0 <= val <= 0xFFFFFFFF:
                    return ipaddress.IPv4Address(val)
            except Exception:
                pass
        if host.startswith(("0x", "0X")):
            try:
                val = int(host, 16)
                if 0 <= val <= 0xFFFFFFFF:
                    return ipaddress.IPv4Address(val)
            except Exception:
                pass
        parts = host.split(".")
        if 1 <= len(parts) <= 4:
            int_parts = []
            for p in parts:
                if not p:
                    return None
                try:
                    if p.startswith(("0x", "0X")):
                        int_parts.append(int(p, 16))
                    elif p.startswith("0") and len(p) > 1 and p.isdigit():
                        int_parts.append(int(p, 8))
                    elif p.isdigit():
                        int_parts.append(int(p, 10))
                    else:
                        return None
                except ValueError:
                    return None
            if len(int_parts) == 4 and all(0 <= x <= 255 for x in int_parts):
                return ipaddress.IPv4Address((int_parts[0] << 24) | (int_parts[1] << 16) | (int_parts[2] << 8) | int_parts[3])
            elif len(int_parts) == 2 and 0 <= int_parts[0] <= 255 and 0 <= int_parts[1] <= 0xFFFFFF:
                return ipaddress.IPv4Address((int_parts[0] << 24) | int_parts[1])
            elif len(int_parts) == 3 and 0 <= int_parts[0] <= 255 and 0 <= int_parts[1] <= 255 and 0 <= int_parts[2] <= 0xFFFF:
                return ipaddress.IPv4Address((int_parts[0] << 24) | (int_parts[1] << 16) | int_parts[2])
            elif len(int_parts) == 1 and 0 <= int_parts[0] <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(int_parts[0])
        return None

    # 1. Check if hostname is an IP literal or alternative notation (decimal, hex, octal, short)
    alt_ip = parse_alternative_ipv4(hostname)
    if alt_ip is not None:
        is_safe, reason = check_ip_object(alt_ip)
        if not is_safe:
            return False, f"Target IP literal '{hostname}' blocked: {reason} (SSRF block)"

    try:
        ip_direct = ipaddress.ip_address(hostname)
        is_safe, reason = check_ip_object(ip_direct)
        if not is_safe:
            return False, f"Target IP literal '{hostname}' blocked: {reason} (SSRF block)"
    except ValueError:
        pass  # It's a domain name, proceed to DNS resolution check

    # Single-label hosts without dots (e.g. http://intranet/) cannot be public FQDNs
    if "." not in _host_core:
        return False, f"Destination '{hostname}' is an internal single-label hostname (SSRF block)"

    # 2. Resolve domain name and verify all returned addresses
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False, f"Target hostname '{hostname}' could not be resolved"

        for entry in addr_info:
            ip_str = entry[4][0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                is_safe, reason = check_ip_object(ip_obj)
                if not is_safe:
                    return False, f"Target hostname '{hostname}' resolves to restricted IP {ip_str}: {reason} (SSRF block)"
            except ValueError:
                return False, f"Invalid IP address returned during DNS resolution: {ip_str}"

    except socket.gaierror as exc:
        return False, f"Target hostname '{hostname}' DNS resolution failed (fail-closed for SSRF safety): {exc}"
    except Exception as e:
        return False, f"Failed to validate target host DNS: {e}"

    return True, "Target URL passed SSRF validation"
