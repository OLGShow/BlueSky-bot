#!/usr/bin/env python3
"""
MED-001 / TEST-001: SSRF URL validation helper.

Hermetic: url_safety only — no network (resolve=False or mocked DNS).

Covers:
  - scheme allowlist (http/https) / reject file:// data:// ftp://
  - private / loopback / link-local / metadata IP literals blocked
  - blocked hostnames (localhost, metadata.google.internal)
  - userinfo rejected
  - public http(s) URLs accepted (no resolve)
  - resolve path rejects private DNS answers (mocked getaddrinfo)

Run:
  python tests/test_url_safety_med001.py
  python -m unittest tests.test_url_safety_med001
"""

from __future__ import annotations

import ipaddress
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from url_safety import (  # noqa: E402
    UnsafeURLError,
    is_blocked_ip,
    is_safe_outbound_url,
    validate_outbound_url,
)


class TestUrlSafetySchemesMed001(unittest.TestCase):
    def test_accepts_https(self):
        url = "https://example.com/feed.xml"
        self.assertEqual(validate_outbound_url(url, resolve=False), url)

    def test_accepts_http(self):
        url = "http://example.com/rss"
        self.assertEqual(validate_outbound_url(url, resolve=False), url)

    def test_rejects_file_scheme(self):
        with self.assertRaises(UnsafeURLError) as ctx:
            validate_outbound_url("file:///etc/passwd", resolve=False)
        self.assertIn("scheme", str(ctx.exception).lower())

    def test_rejects_data_scheme(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("data:text/plain,hi", resolve=False)

    def test_rejects_ftp_scheme(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("ftp://files.example.com/a", resolve=False)

    def test_rejects_empty_and_whitespace(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("", resolve=False)
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("   ", resolve=False)
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("https://example.com/a b", resolve=False)

    def test_rejects_userinfo(self):
        with self.assertRaises(UnsafeURLError) as ctx:
            validate_outbound_url("https://user:pass@example.com/", resolve=False)
        self.assertIn("userinfo", str(ctx.exception).lower())

    def test_rejects_missing_hostname(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("https:///path", resolve=False)


class TestUrlSafetyIpBlockingMed001(unittest.TestCase):
    def test_blocks_loopback_ipv4(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("http://127.0.0.1/secret", resolve=False)

    def test_blocks_rfc1918(self):
        for host in ("10.0.0.1", "172.16.5.5", "192.168.1.1"):
            with self.assertRaises(UnsafeURLError, msg=host):
                validate_outbound_url(f"http://{host}/", resolve=False)

    def test_blocks_link_local_and_metadata(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("http://169.254.169.254/latest/meta-data/", resolve=False)
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("http://169.254.1.1/", resolve=False)

    def test_blocks_ipv6_loopback(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("http://[::1]/", resolve=False)

    def test_blocks_ipv6_ula(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("http://[fd00::1]/", resolve=False)

    def test_is_blocked_ip_helpers(self):
        self.assertTrue(is_blocked_ip(ipaddress.ip_address("127.0.0.1")))
        self.assertTrue(is_blocked_ip(ipaddress.ip_address("169.254.169.254")))
        self.assertFalse(is_blocked_ip(ipaddress.ip_address("8.8.8.8")))

    def test_blocks_localhost_hostname(self):
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("http://localhost/admin", resolve=False)
        with self.assertRaises(UnsafeURLError):
            validate_outbound_url("http://metadata.google.internal/", resolve=False)

    def test_public_ipv4_literal_ok(self):
        url = "https://8.8.8.8/health"
        self.assertEqual(validate_outbound_url(url, resolve=False), url)


class TestUrlSafetyResolveMed001(unittest.TestCase):
    def test_resolve_rejects_private_answer(self):
        fake = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.9", 0)),
        ]
        with mock.patch("url_safety.socket.getaddrinfo", return_value=fake):
            with self.assertRaises(UnsafeURLError) as ctx:
                validate_outbound_url("https://evil.example/rss", resolve=True)
            self.assertIn("blocked", str(ctx.exception).lower())

    def test_resolve_accepts_public_answer(self):
        fake = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
        ]
        with mock.patch("url_safety.socket.getaddrinfo", return_value=fake):
            url = "https://example.com/path"
            self.assertEqual(validate_outbound_url(url, resolve=True), url)

    def test_resolve_dns_failure(self):
        with mock.patch(
            "url_safety.socket.getaddrinfo",
            side_effect=socket.gaierror(socket.EAI_NONAME, "nxdomain"),
        ):
            with self.assertRaises(UnsafeURLError):
                validate_outbound_url("https://does-not-resolve.test/", resolve=True)

    def test_is_safe_wrapper(self):
        self.assertTrue(is_safe_outbound_url("https://example.com/", resolve=False))
        self.assertFalse(is_safe_outbound_url("file:///tmp/x", resolve=False))
        self.assertFalse(is_safe_outbound_url("http://192.168.0.1/", resolve=False))


if __name__ == "__main__":
    unittest.main()
