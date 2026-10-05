# Security Policy

## Supported Versions

The following versions of `ultimate-seo-geo` currently receive security updates:

| Version | Supported          |
| ------- | ------------------ |
| 3.8.x   | :white_check_mark: |
| < 3.8.0 | :x:                |

## Security Philosophy

`ultimate-seo-geo` is designed for autonomous web content inspection and AI safety. Its security posture adheres to:
1. **Zero External Dependencies:** Built strictly on Python 3.10+ standard library, eliminating supply-chain vulnerabilities and transitive dependency risks.
2. **Deterministic SSRF Prevention:** Multi-layer validation against loopback, private RFC 1918 subnets, link-local / cloud metadata (169.254.169.254), CGNAT (100.64.0.0/10), IPv6 unique local, and IPv4-mapped IPv6 addresses.
3. **Prompt Injection Defense (`SEC-PROMPT-INJECTION-001`):** Autonomous scanning of untrusted web content for adversarial jailbreaks, role hijacking, and hidden instruction injection targeting LLM context windows.

## Reporting a Vulnerability

If you discover a security vulnerability or SSRF bypass:
1. **Do NOT open a public GitHub issue.**
2. Send an email to the repository maintainer with:
   - Description of the vulnerability and attack vector.
   - Proof of concept (PoC) URL or payload.
   - Expected vs observed behavior.
3. We will acknowledge receipt within 48 hours and coordinate a coordinated disclosure timeline.
