#!/usr/bin/env python3
"""
LogSanitizer — logging filter that masks sensitive data (handles, tokens,
passwords, emails) and provides separate audit/debug loggers.
"""

import logging
import re
import os
import sys

_TOKEN_RE = re.compile(
    r'(sk-[A-Za-z0-9_-]{20,})'   # OpenAI keys
    r'|([A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4})'  # app passwords
    r'|(eyJ[A-Za-z0-9_-]{30,})',  # JWT-like tokens
)
_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}')
_HANDLE_RE = re.compile(r'@([A-Za-z0-9_-]+\.bsky\.social)')


def _mask(match: re.Match) -> str:
    val = match.group(0)
    if len(val) <= 8:
        return '***'
    return val[:4] + '***' + val[-3:]


class SanitizingFilter(logging.Filter):
    """Replaces sensitive patterns in log records before they are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._sanitize(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._sanitize(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._sanitize(a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True

    @staticmethod
    def _sanitize(text: str) -> str:
        text = _TOKEN_RE.sub(_mask, text)
        text = _EMAIL_RE.sub(_mask, text)
        text = _HANDLE_RE.sub(_mask, text)
        return text


def setup_logging(log_dir: str, level: str = 'INFO') -> None:
    """Configure root logger with sanitization, file rotation and separate channels."""
    log_file = os.path.join(log_dir, 'bot.log')
    audit_file = os.path.join(log_dir, 'audit.log')
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    sanitizer = SanitizingFilter()

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setFormatter(fmt)
    file_handler.addFilter(sanitizer)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.addFilter(sanitizer)
    root.addHandler(console_handler)

    audit_logger = logging.getLogger('audit')
    audit_handler = logging.FileHandler(audit_file, encoding='utf-8', mode='a')
    audit_handler.setFormatter(fmt)
    audit_handler.addFilter(sanitizer)
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False

    debug_logger = logging.getLogger('debug')
    debug_logger.setLevel(logging.DEBUG)
    debug_handler = logging.FileHandler(
        os.path.join(log_dir, 'debug.log'), encoding='utf-8', mode='a'
    )
    debug_handler.setFormatter(fmt)
    debug_handler.addFilter(sanitizer)
    debug_logger.addHandler(debug_handler)
    debug_logger.propagate = False
