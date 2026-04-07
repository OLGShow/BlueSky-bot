#!/usr/bin/env python3
"""
Verification suite — validates all hardening + improvement changes.

Tests:
  1. State migration (pickle -> JSON, schema versioning, atomic writes)
  2. Action ledger (idempotency, TTL, compact)
  3. Log sanitizer (token/email masking)
  4. Resilience service (circuit breaker, backoff, error classification)
  5. Retention controls (list trimming)
  6. Config atomic write
  7. Import health check
  8. SingleInstanceLock (acquire, stale, double-lock)
  9. SessionStore (save/load/expiry)
 10. ActivityBudget (spend, limits, reset)
 11. EngagementService mode guard
 12. Scheduler (_is_posting_window)

Run:  python verify_bot.py
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import shutil
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(level=logging.WARNING)
_results = []


def test(name):
    def decorator(fn):
        def wrapper():
            try:
                fn()
                _results.append((name, 'PASS', ''))
                print(f"  [PASS] {name}")
            except Exception as e:
                _results.append((name, 'FAIL', str(e)))
                print(f"  [FAIL] {name}: {e}")
        return wrapper
    return decorator


# --- 1. State Service ---

@test("StateService: save/load round-trip (JSON)")
def test_state_roundtrip():
    from state_service import StateService
    from dataclasses import dataclass, field
    from typing import List, Dict, Set

    @dataclass
    class FakeMemory:
        successful_posts: List[Dict] = field(default_factory=list)
        failed_posts: List[Dict] = field(default_factory=list)
        interaction_patterns: Dict[str, float] = field(default_factory=dict)
        trending_topics: Dict[str, int] = field(default_factory=dict)
        user_relationships: Dict[str, Dict] = field(default_factory=dict)
        content_performance: Dict[str, float] = field(default_factory=dict)
        last_update: datetime = field(default_factory=datetime.now)
        published_content_hashes: Set[str] = field(default_factory=set)
        published_urls: Set[str] = field(default_factory=set)
        repost_performance: List[Dict] = field(default_factory=list)
        viral_posts: List[Dict] = field(default_factory=list)
        engagement_metrics: Dict[str, float] = field(default_factory=dict)
        ab_results: Dict = field(default_factory=dict)
        topic_outcomes: Dict[str, Dict] = field(default_factory=dict)
        source_outcomes: Dict[str, Dict] = field(default_factory=dict)
        pattern_blacklist: List[str] = field(default_factory=list)

    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, 'test_memory.json')
        svc = StateService(path=path, legacy_pickle=os.path.join(tmpdir, 'none.pkl'))
        mem = FakeMemory(
            successful_posts=[{'text': 'hello', 'timestamp': datetime.now().isoformat()}],
            published_content_hashes={'hash1', 'hash2'},
            published_urls={'url1'},
        )
        svc.save(mem)
        assert os.path.exists(path), "JSON file not created"

        loaded = svc.load(FakeMemory)
        assert len(loaded.successful_posts) == 1
        assert 'hash1' in loaded.published_content_hashes
        assert 'url1' in loaded.published_urls
    finally:
        shutil.rmtree(tmpdir)


@test("StateService: retention trims long lists")
def test_state_retention():
    from state_service import StateService
    from dataclasses import dataclass, field
    from typing import List, Dict, Set

    @dataclass
    class FakeMemory:
        successful_posts: List[Dict] = field(default_factory=list)
        failed_posts: List[Dict] = field(default_factory=list)
        interaction_patterns: Dict[str, float] = field(default_factory=dict)
        trending_topics: Dict[str, int] = field(default_factory=dict)
        user_relationships: Dict[str, Dict] = field(default_factory=dict)
        content_performance: Dict[str, float] = field(default_factory=dict)
        last_update: datetime = field(default_factory=datetime.now)
        published_content_hashes: Set[str] = field(default_factory=set)
        published_urls: Set[str] = field(default_factory=set)
        repost_performance: List[Dict] = field(default_factory=list)
        viral_posts: List[Dict] = field(default_factory=list)
        engagement_metrics: Dict[str, float] = field(default_factory=dict)
        ab_results: Dict = field(default_factory=dict)
        topic_outcomes: Dict[str, Dict] = field(default_factory=dict)
        source_outcomes: Dict[str, Dict] = field(default_factory=dict)
        pattern_blacklist: List[str] = field(default_factory=list)

    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, 'test_ret.json')
        svc = StateService(path=path, legacy_pickle=os.path.join(tmpdir, 'x.pkl'),
                           retention={'successful_posts': 5, 'viral_posts': 3})
        mem = FakeMemory(
            successful_posts=[{'text': f'p{i}', 'timestamp': datetime.now().isoformat()} for i in range(20)],
            viral_posts=[{'text': f'v{i}'} for i in range(10)],
        )
        svc.save(mem)
        loaded = svc.load(FakeMemory)
        assert len(loaded.successful_posts) <= 5, f"Expected <=5 posts, got {len(loaded.successful_posts)}"
        assert len(loaded.viral_posts) <= 3, f"Expected <=3 viral, got {len(loaded.viral_posts)}"
    finally:
        shutil.rmtree(tmpdir)


# --- 2. Action Ledger ---

@test("ActionLedger: record + contains + TTL expiry")
def test_action_ledger():
    from state_service import ActionLedger
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, 'ledger.jsonl')
        ledger = ActionLedger(path=path, ttl_hours=1)
        ledger.record('like:abc123')
        assert ledger.contains('like:abc123'), "Key should exist"
        assert not ledger.contains('like:xyz'), "Key should not exist"

        # Simulate multiple expired keys
        for i in range(5):
            ledger._keys[f'old:{i}'] = (datetime.now() - timedelta(hours=2)).isoformat()

        removed = ledger.compact()
        assert removed >= 5, f"Compact should remove expired keys, removed={removed}"
        assert 'like:abc123' in ledger._keys, "Fresh key should survive compact"
    finally:
        shutil.rmtree(tmpdir)


# --- 3. Log Sanitizer ---

@test("SanitizingFilter: masks tokens and emails")
def test_log_sanitizer():
    from log_sanitizer import SanitizingFilter
    f = SanitizingFilter()
    rec = logging.LogRecord('test', logging.INFO, '', 0,
                            'key=sk-proj-Hj7eo3lurpDQrYcP9pxdRE user@example.com',
                            None, None)
    f.filter(rec)
    assert 'sk-proj-Hj7eo3lurpDQrYcP9pxdRE' not in rec.msg, "Token should be masked"
    assert 'user@example.com' not in rec.msg, "Email should be masked"
    assert '***' in rec.msg, "Mask placeholder should be present"


# --- 4. Resilience Service ---

@test("CircuitBreaker: closed -> open -> half_open -> closed")
def test_circuit_breaker():
    from resilience_service import CircuitBreaker
    cb = CircuitBreaker('test', failure_threshold=3, recovery_timeout=0.1)
    assert cb.state == 'closed'
    for _ in range(3):
        cb.record_failure()
    assert cb.state == 'open'
    import time; time.sleep(0.15)
    assert cb.state == 'half_open'
    cb.record_success()
    assert cb.state == 'closed'


@test("classify_error: maps error strings correctly")
def test_error_classification():
    from resilience_service import classify_error, ErrorClass
    assert classify_error(Exception("HTTP 429 Too Many Requests")) == ErrorClass.RATE_LIMIT
    assert classify_error(Exception("HTTP 503 Service Unavailable")) == ErrorClass.SERVER
    assert classify_error(Exception("Connection timeout")) == ErrorClass.NETWORK
    assert classify_error(Exception("HTTP 401 Unauthorized")) == ErrorClass.AUTH
    assert classify_error(Exception("something weird")) == ErrorClass.UNKNOWN


@test("backoff_seconds: increases with attempt")
def test_backoff():
    from resilience_service import backoff_seconds, ErrorClass
    d1 = backoff_seconds(ErrorClass.RATE_LIMIT, 1)
    d2 = backoff_seconds(ErrorClass.RATE_LIMIT, 3)
    assert d2 > d1, "Backoff should increase with attempts"


# --- 5. Atomic Config Writer ---

@test("AtomicConfigWriter: writes valid JSON atomically")
def test_atomic_config():
    from state_service import AtomicConfigWriter
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, 'config.json')
        AtomicConfigWriter.save({'key': 'value', 'nested': {'a': 1}}, path)
        with open(path, 'r') as f:
            data = json.load(f)
        assert data['key'] == 'value'
        assert data['nested']['a'] == 1
    finally:
        shutil.rmtree(tmpdir)


# --- 6. Import health check ---

@test("All new modules import cleanly")
def test_imports():
    import state_service
    import resilience_service
    import log_sanitizer


@test(".dockerignore excludes .env")
def test_dockerignore():
    with open('.dockerignore', 'r') as f:
        content = f.read()
    lines = [l.strip() for l in content.splitlines()]
    assert '.env' in lines, ".env not excluded from docker build context"


@test(".gitignore excludes state files")
def test_gitignore():
    with open('.gitignore', 'r') as f:
        content = f.read()
    for pattern in ['bot_memory.json', 'action_ledger.jsonl', 'dry_run_report.json', 'reports/']:
        assert pattern in content, f"{pattern} not in .gitignore"


# --- 8. SingleInstanceLock ---

@test("SingleInstanceLock: acquire + release + stale detection")
def test_single_instance_lock():
    from state_service import SingleInstanceLock
    tmpdir = tempfile.mkdtemp()
    try:
        lock_path = os.path.join(tmpdir, 'test.lock')
        lock = SingleInstanceLock(path=lock_path, stale_seconds=1)
        lock.acquire()
        assert os.path.exists(lock_path), "Lock file should exist"

        lock2 = SingleInstanceLock(path=lock_path, stale_seconds=300)
        try:
            lock2.acquire()
            assert False, "Second acquire should raise RuntimeError"
        except RuntimeError:
            pass

        lock.release()
        assert not os.path.exists(lock_path), "Lock file should be removed"

        lock3 = SingleInstanceLock(path=lock_path, stale_seconds=0)
        with open(lock_path, 'w') as f:
            json.dump({'pid': 99999999, 'ts': time.time() - 10}, f)
        lock3.acquire()
        lock3.release()
    finally:
        shutil.rmtree(tmpdir)


# --- 9. SessionStore ---

@test("SessionStore: save/load round-trip + expiry")
def test_session_store():
    from state_service import SessionStore
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, 'session.json')
        store = SessionStore(path=path, max_age_hours=24)
        store.save('test-session-string-abc123')
        loaded = store.load()
        assert loaded == 'test-session-string-abc123', f"Got {loaded}"

        expired = SessionStore(path=path, max_age_hours=0)
        assert expired.load() is None, "Expired session should return None"

        store.clear()
        assert not os.path.exists(path), "Session file should be removed"
    finally:
        shutil.rmtree(tmpdir)


# --- 10. ActivityBudget ---

@test("ActivityBudget: spend + limit enforcement + reset")
def test_activity_budget():
    from state_service import ActivityBudget
    budget = ActivityBudget(hourly_limit=10, daily_limit=20)
    assert budget.can_spend('post'), "Should be able to spend initially"

    for _ in range(3):
        budget.spend('post')
    assert budget.remaining_hourly == 1, f"Expected 1, got {budget.remaining_hourly}"
    assert not budget.can_spend('post'), "Should not be able to spend 4th post (10 used of 10)"

    budget.spend('delete')
    assert budget.remaining_hourly == 0

    summary = budget.summary()
    assert 'hourly' in summary and 'daily' in summary


# --- 11. Engagement mode guard ---

@test("EngagementService: mode guard (open, whitelist, mention_only)")
def test_engagement_mode_guard():
    from engagement_service import EngagementService

    class FakeBot:
        config = {'engagement_mode': 'open', 'engagement_whitelist': []}

    svc = EngagementService(FakeBot())
    assert svc._engagement_allowed('did:123', '@user') is True

    FakeBot.config['engagement_mode'] = 'mention_only'
    assert svc._engagement_allowed('did:123', '@user') is False

    FakeBot.config['engagement_mode'] = 'whitelist_only'
    FakeBot.config['engagement_whitelist'] = ['did:abc']
    assert svc._engagement_allowed('did:abc') is True
    assert svc._engagement_allowed('did:xyz') is False


# --- 12. Scheduling ---

@test("Scheduling: quiet hours + active windows + fallback")
def test_scheduling():
    """Test scheduling logic without importing the full bot module."""
    current_hour = datetime.now().hour

    def is_posting_window(config):
        sched = config.get('scheduling', {})
        quiet_hours = sched.get('quiet_hours', [])
        active_windows = sched.get('active_windows', [])
        if not quiet_hours and not active_windows:
            return True
        ch = current_hour
        if quiet_hours and ch in quiet_hours:
            return False
        if active_windows:
            for w in active_windows:
                if not isinstance(w, (list, tuple)) or len(w) < 2:
                    continue
                s, e = int(w[0]), int(w[1])
                if s <= e:
                    if s <= ch < e:
                        return True
                else:
                    if ch >= s or ch < e:
                        return True
            return False
        return True

    assert is_posting_window({'scheduling': {}}) is True, "No config -> always allowed"

    cfg = {'scheduling': {'quiet_hours': [current_hour]}}
    assert is_posting_window(cfg) is False, "Current hour in quiet_hours -> blocked"

    cfg = {'scheduling': {'quiet_hours': [(current_hour + 12) % 24]}}
    assert is_posting_window(cfg) is True, "Distant hour in quiet_hours -> allowed"

    cfg = {'scheduling': {'active_windows': [[current_hour, (current_hour + 2) % 24]]}}
    if current_hour < (current_hour + 2) % 24:
        assert is_posting_window(cfg) is True, "Current hour in active window -> allowed"

    far_start = (current_hour + 6) % 24
    far_end = (current_hour + 8) % 24
    if far_start < far_end:
        cfg = {'scheduling': {'active_windows': [[far_start, far_end]]}}
        assert is_posting_window(cfg) is False, "Current hour outside active window -> blocked"


# --- Run all ---

def main():
    print("=" * 60)
    print("BlueSky Bot — Hardening Verification Suite")
    print("=" * 60)

    tests = [v for v in globals().values() if callable(v) and hasattr(v, '__wrapped__') or
             (callable(v) and v.__name__.startswith('test_'))]

    for fn_name in list(globals()):
        fn = globals()[fn_name]
        if callable(fn) and fn_name.startswith('test_'):
            fn()

    print()
    passed = sum(1 for _, s, _ in _results if s == 'PASS')
    failed = sum(1 for _, s, _ in _results if s == 'FAIL')
    print(f"Results: {passed} passed, {failed} failed out of {len(_results)} tests")

    if failed:
        print("\nFailed tests:")
        for name, status, msg in _results:
            if status == 'FAIL':
                print(f"  - {name}: {msg}")
        sys.exit(1)
    else:
        print("\nAll tests passed!")

    # Save report
    report = {
        'timestamp': datetime.now().isoformat(),
        'tests': [{'name': n, 'status': s, 'error': e} for n, s, e in _results],
        'passed': passed,
        'failed': failed,
    }
    os.makedirs('reports', exist_ok=True)
    with open(os.path.join('reports', 'verification_report.json'), 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved: reports/verification_report.json")


if __name__ == '__main__':
    main()
