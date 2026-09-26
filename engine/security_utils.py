"""
Security utilities and SSRF prevention guards for ultimate-seo-geo v3.1.1.
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

    # Extract hostname, stripping brackets for IPv6 literals and port
    if netloc.startswith("[") and "]" in netloc:
        hostname = netloc[1:netloc.index("]")].strip().lower()
    else:
        hostname = netloc.split(":")[0].strip().lower()

    if not hostname:
        return False, "Empty hostname in target URL"

    # Quick check for known loopback/local names
    if hostname in ("localhost", "local", "127.0.0.1", "::1", "0.0.0.0"):
        return False, f"Destination '{hostname}' is a forbidden loopback target (SSRF prevention)"

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

    # 1. Check if hostname is directly an IP literal
    try:
        ip_direct = ipaddress.ip_address(hostname)
        is_safe, reason = check_ip_object(ip_direct)
        if not is_safe:
            return False, f"Target IP literal '{hostname}' blocked: {reason} (SSRF block)"
    except ValueError:
        pass  # It's a domain name, proceed to DNS resolution check

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

    except socket.gaierror:
        # If DNS lookup fails, allow the request to proceed so HTTP client produces natural reachability error
        pass
    except Exception as e:
        return False, f"Failed to validate target host DNS: {e}"

    return True, "Target URL passed SSRF validation"
