#!/usr/bin/env python3
"""
Outbound URL safety helpers (SSRF mitigation).

Allowlists http/https, rejects odd schemes (file://, data://, …), and blocks
private / link-local / loopback / metadata addresses where practical.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import FrozenSet, Iterable, Optional, Sequence, Union
from urllib.parse import urlparse

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

ALLOWED_SCHEMES: FrozenSet[str] = frozenset({"http", "https"})

# Hostnames that must never be fetched (cloud metadata / local aliases).
BLOCKED_HOSTNAMES: FrozenSet[str] = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
    }
)

# Well-known cloud metadata / link-local targets (also covered by IP checks).
_METADATA_IPV4 = ipaddress.ip_address("169.254.169.254")


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe for an outbound fetch."""


def _hostname_is_blocked(hostname: str) -> bool:
    host = hostname.strip(".").lower()
    if not host:
        return True
    if host in BLOCKED_HOSTNAMES:
        return True
    # Trailing .localhost / .local are typically local-only.
    if host.endswith(".localhost") or host.endswith(".local"):
        return True
    return False


def is_blocked_ip(ip: IPAddress) -> bool:
    """True if the IP must not be used as an outbound fetch target."""
    if ip == _METADATA_IPV4:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_blocked_ip(ip.ipv4_mapped)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _parse_ip_literal(hostname: str) -> Optional[IPAddress]:
    """Return an IP if hostname is a literal; None if it is a DNS name."""
    host = hostname.strip()
    # Bracketed IPv6 from urlparse (e.g. [::1]).
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _resolve_host_ips(hostname: str) -> Sequence[IPAddress]:
    """Resolve hostname to IPs. Raises UnsafeURLError on DNS failure."""
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"DNS resolution failed for host: {hostname}") from exc
    ips = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            ips.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue
    if not ips:
        raise UnsafeURLError(f"No usable addresses for host: {hostname}")
    return ips


def validate_outbound_url(
    url: str,
    *,
    allow_schemes: Optional[Iterable[str]] = None,
    resolve: bool = True,
) -> str:
    """
    Validate that ``url`` is safe for an outbound HTTP(S) fetch.

    Returns the stripped URL string on success.
    Raises ``UnsafeURLError`` when the URL must not be fetched.

    Args:
        url: Candidate URL (must be absolute).
        allow_schemes: Override scheme allowlist (default http/https).
        resolve: When True, resolve hostnames and reject private/metadata IPs.
                 Set False for hermetic format-only checks (IP literals still checked).
    """
    if url is None:
        raise UnsafeURLError("URL is empty")
    if not isinstance(url, str):
        raise UnsafeURLError("URL must be a string")

    candidate = url.strip()
    if not candidate:
        raise UnsafeURLError("URL is empty")

    # Reject whitespace / control characters that can confuse parsers.
    if any(ch.isspace() for ch in candidate):
        raise UnsafeURLError("URL contains whitespace")

    parsed = urlparse(candidate)
    schemes = frozenset(s.lower() for s in (allow_schemes or ALLOWED_SCHEMES))
    scheme = (parsed.scheme or "").lower()
    if scheme not in schemes:
        raise UnsafeURLError(f"Scheme not allowed: {scheme or '(none)'}")

    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURLError("URL userinfo is not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL has no hostname")

    if _hostname_is_blocked(hostname):
        raise UnsafeURLError(f"Hostname is blocked: {hostname}")

    literal_ip = _parse_ip_literal(hostname)
    if literal_ip is not None:
        if is_blocked_ip(literal_ip):
            raise UnsafeURLError(f"IP address is blocked: {literal_ip}")
        return candidate

    if resolve:
        for ip in _resolve_host_ips(hostname):
            if is_blocked_ip(ip):
                raise UnsafeURLError(
                    f"Host resolves to blocked address: {hostname} -> {ip}"
                )

    return candidate


def is_safe_outbound_url(url: str, *, resolve: bool = True) -> bool:
    """Boolean wrapper around ``validate_outbound_url``."""
    try:
        validate_outbound_url(url, resolve=resolve)
        return True
    except UnsafeURLError:
        return False
