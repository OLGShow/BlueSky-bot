#!/usr/bin/env python3
"""
StateService — safe JSON-based state storage with schema versioning,
atomic writes, pickle migration, action ledger, retention controls,
single-instance lock, session persistence, and activity budget.
"""

import json
import os
import pickle
import shutil
import tempfile
import logging
import time as _time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

_DEFAULT_RETENTION = {
    'successful_posts': 500,
    'failed_posts': 200,
    'repost_performance': 200,
    'viral_posts': 100,
    'pattern_blacklist': 50,
    'published_content_hashes': 2000,
    'published_urls': 2000,
}


def _dt_serial(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, timedelta):
        return obj.total_seconds()
    raise TypeError(f"Non-serialisable type: {type(obj)}")


def _sets_from_lists(data: dict) -> dict:
    """Convert known set-fields back from lists after JSON load."""
    for key in ('published_content_hashes', 'published_urls',
                'commented_posts_cache', 'liked_posts_cache',
                'reposted_posts_cache', 'followed_users_cache'):
        if key in data and isinstance(data[key], list):
            data[key] = set(data[key])
    return data


class StateService:
    """JSON state file with atomic writes and schema migration."""

    def __init__(self, path: str = 'bot_memory.json',
                 legacy_pickle: str = 'bot_memory.pkl',
                 retention: Optional[Dict[str, int]] = None):
        self.path = path
        self.legacy_pickle = legacy_pickle
        self.retention = retention or dict(_DEFAULT_RETENTION)

    def save(self, memory) -> None:
        data = self._memory_to_dict(memory)
        data['_schema_version'] = SCHEMA_VERSION
        data['_saved_at'] = datetime.now().isoformat()

        self._apply_retention(data)

        dir_name = os.path.dirname(self.path) or '.'
        try:
            fd, tmp = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1, default=_dt_serial)
            if os.path.exists(self.path):
                backup = self.path + '.bak'
                try:
                    shutil.copy2(self.path, backup)
                except Exception:
                    pass
            shutil.move(tmp, self.path)
        except Exception as e:
            logger.error(f"State save failed: {e}")
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def load(self, memory_cls):
        """Load from JSON; fallback to pickle migration; fallback to fresh."""
        if os.path.exists(self.path):
            return self._load_json(memory_cls)
        if os.path.exists(self.legacy_pickle):
            return self._migrate_pickle(memory_cls)
        logger.info("No state file found — creating fresh memory.")
        return self._fresh(memory_cls)

    def _load_json(self, memory_cls):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            ver = data.pop('_schema_version', 1)
            data.pop('_saved_at', None)
            if ver < SCHEMA_VERSION:
                data = self._upgrade_schema(data, ver)
            data = _sets_from_lists(data)
            data = self._ensure_fields(data)
            mem = self._dict_to_memory(memory_cls, data)
            logger.info(f"State loaded from {self.path} (schema v{ver})")
            return mem
        except Exception as e:
            logger.error(f"JSON state load failed: {e}. Trying pickle fallback.")
            if os.path.exists(self.legacy_pickle):
                return self._migrate_pickle(memory_cls)
            logger.warning("No fallback available — starting with fresh memory. THIS MEANS ALL PREVIOUS STATE IS LOST.")
            return self._fresh(memory_cls)

    def _migrate_pickle(self, memory_cls):
        logger.info(f"Migrating state from pickle ({self.legacy_pickle}) to JSON ({self.path})...")
        try:
            with open(self.legacy_pickle, 'rb') as f:
                old_mem = pickle.load(f)
            data = self._memory_to_dict(old_mem)
            data = self._ensure_fields(data)
            mem = self._dict_to_memory(memory_cls, _sets_from_lists(data))
            self.save(mem)
            archive = self.legacy_pickle + '.migrated'
            shutil.move(self.legacy_pickle, archive)
            logger.info(f"Pickle migrated and archived as {archive}")
            return mem
        except Exception as e:
            logger.error(f"Pickle migration failed: {e}. Starting fresh. THIS MEANS ALL PREVIOUS STATE IS LOST.")
            return self._fresh(memory_cls)

    @staticmethod
    def _upgrade_schema(data: dict, from_ver: int) -> dict:
        if from_ver < 2:
            for fld, default in [('ab_results', {}), ('topic_outcomes', {}),
                                 ('source_outcomes', {}), ('pattern_blacklist', [])]:
                data.setdefault(fld, default)
        return data

    @staticmethod
    def _ensure_fields(data: dict) -> dict:
        defaults = {
            'successful_posts': [], 'failed_posts': [],
            'interaction_patterns': {}, 'trending_topics': {},
            'user_relationships': {}, 'content_performance': {},
            'last_update': datetime.now().isoformat(),
            'published_content_hashes': set(),
            'published_urls': set(),
            'repost_performance': [], 'viral_posts': [],
            'engagement_metrics': {},
            'ab_results': {}, 'topic_outcomes': {},
            'source_outcomes': {}, 'pattern_blacklist': [],
        }
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data

    def _apply_retention(self, data: dict) -> None:
        for key, limit in self.retention.items():
            if key in data and isinstance(data[key], (list, set)):
                collection = data[key]
                if isinstance(collection, set):
                    if len(collection) > limit:
                        data[key] = set(list(collection)[-limit:])
                elif len(collection) > limit:
                    data[key] = collection[-limit:]

    @staticmethod
    def _memory_to_dict(memory) -> dict:
        """Convert a BotMemory dataclass instance to a plain dict."""
        result = {}
        for fld in ('successful_posts', 'failed_posts', 'interaction_patterns',
                     'trending_topics', 'user_relationships', 'content_performance',
                     'last_update', 'published_content_hashes', 'published_urls',
                     'repost_performance', 'viral_posts', 'engagement_metrics',
                     'ab_results', 'topic_outcomes', 'source_outcomes', 'pattern_blacklist'):
            val = getattr(memory, fld, None)
            if val is not None:
                result[fld] = val
        for cache in ('commented_posts_cache', 'recent_comments_cache',
                      'liked_posts_cache', 'reposted_posts_cache', 'followed_users_cache'):
            val = getattr(memory, cache, None)
            if val is not None:
                result[cache] = val
        return result

    @staticmethod
    def _dict_to_memory(memory_cls, data: dict):
        init_keys = {
            'successful_posts', 'failed_posts', 'interaction_patterns',
            'trending_topics', 'user_relationships', 'content_performance',
            'last_update', 'published_content_hashes', 'published_urls',
            'repost_performance', 'viral_posts', 'engagement_metrics',
            'ab_results', 'topic_outcomes', 'source_outcomes', 'pattern_blacklist',
        }
        init_data = {}
        extra_data = {}
        for k, v in data.items():
            if k.startswith('_'):
                continue
            if k in init_keys:
                init_data[k] = v
            else:
                extra_data[k] = v
        if 'last_update' in init_data and isinstance(init_data['last_update'], str):
            try:
                init_data['last_update'] = datetime.fromisoformat(init_data['last_update'])
            except Exception:
                init_data['last_update'] = datetime.now()
        mem = memory_cls(**init_data)
        for k, v in extra_data.items():
            setattr(mem, k, v)
        return mem

    @staticmethod
    def _fresh(memory_cls):
        return memory_cls(
            successful_posts=[], failed_posts=[],
            interaction_patterns={}, trending_topics={},
            user_relationships={}, content_performance={},
            last_update=datetime.now(),
            published_content_hashes=set(), published_urls=set(),
            repost_performance=[], viral_posts=[],
            engagement_metrics={},
            ab_results={}, topic_outcomes={},
            source_outcomes={}, pattern_blacklist=[],
        )


class ActionLedger:
    """Append-only log of bot actions for idempotency.

    Each action is identified by a key (e.g. 'like:<uri>', 'repost:<uri>').
    Keys older than ``ttl_hours`` are evicted on periodic compact().
    The ledger is flushed to disk after every write for crash safety.
    """

    def __init__(self, path: str = 'action_ledger.jsonl', ttl_hours: int = 72):
        self.path = path
        self.ttl = timedelta(hours=ttl_hours)
        self._keys: Dict[str, str] = {}  # key -> iso timestamp
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    self._keys[entry['key']] = entry['ts']
        except Exception as e:
            logger.warning(f"ActionLedger load error: {e}")

    def contains(self, key: str) -> bool:
        if key not in self._keys:
            return False
        ts = datetime.fromisoformat(self._keys[key])
        if datetime.now() - ts > self.ttl:
            del self._keys[key]
            return False
        return True

    def record(self, key: str) -> None:
        ts = datetime.now().isoformat()
        self._keys[key] = ts
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'key': key, 'ts': ts}) + '\n')
        except Exception as e:
            logger.warning(f"ActionLedger write error: {e}")

    def compact(self) -> int:
        """Remove expired entries and rewrite file. Returns number removed."""
        cutoff = datetime.now() - self.ttl
        before = len(self._keys)
        self._keys = {
            k: ts for k, ts in self._keys.items()
            if datetime.fromisoformat(ts) > cutoff
        }
        removed = before - len(self._keys)
        if removed > 0:
            self._rewrite()
            logger.info(f"ActionLedger compacted: {removed} expired entries removed")
        return removed

    def _rewrite(self) -> None:
        try:
            dir_name = os.path.dirname(self.path) or '.'
            fd, tmp = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                for key, ts in self._keys.items():
                    f.write(json.dumps({'key': key, 'ts': ts}) + '\n')
            shutil.move(tmp, self.path)
        except Exception as e:
            logger.warning(f"ActionLedger rewrite error: {e}")


class AtomicConfigWriter:
    """Write JSON config files atomically (write-tmp-then-rename)."""

    @staticmethod
    def save(config: dict, path: str) -> None:
        dir_name = os.path.dirname(path) or '.'
        fd, tmp = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False, default=str)
            shutil.move(tmp, path)
        except Exception as e:
            logger.error(f"Atomic config save failed: {e}")
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


# ---------------------------------------------------------------------------
# SingleInstanceLock — prevents duplicate bot processes
# ---------------------------------------------------------------------------

class SingleInstanceLock:
    """Advisory file-lock with PID + stale detection.

    Usage::

        lock = SingleInstanceLock()
        lock.acquire()          # raises RuntimeError if another instance runs
        try:
            ...
        finally:
            lock.release()
    """

    def __init__(self, path: str = 'bot.lock', stale_seconds: float = 300):
        self.path = path
        self.stale_seconds = stale_seconds
        self._acquired = False

    def acquire(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                pid = data.get('pid')
                ts = data.get('ts', 0)
                if pid and self._pid_alive(pid):
                    age = _time.time() - ts
                    if age < self.stale_seconds:
                        raise RuntimeError(
                            f"Another bot instance is running (PID {pid}, "
                            f"lock age {age:.0f}s). Remove {self.path} if stale."
                        )
                    logger.warning(
                        f"Lock file exists (PID {pid}) but age {age:.0f}s "
                        f"> {self.stale_seconds}s - treating as stale."
                    )
                else:
                    logger.warning(
                        f"Lock file exists but PID {pid} is dead - removing stale lock."
                    )
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("Corrupt lock file - removing.")
            self._remove()

        self._write()
        self._acquired = True
        logger.info(f"Single-instance lock acquired (PID {os.getpid()})")

    def release(self) -> None:
        if self._acquired:
            self._remove()
            self._acquired = False
            logger.info("Single-instance lock released")

    def heartbeat(self) -> None:
        """Refresh lock timestamp so watchdog won't treat it as stale."""
        if self._acquired:
            self._write()

    def _write(self) -> None:
        dir_name = os.path.dirname(self.path) or '.'
        fd, tmp = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({'pid': os.getpid(), 'ts': _time.time()}, f)
            shutil.move(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _remove(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError, PermissionError, ValueError):
            return False


# ---------------------------------------------------------------------------
# SessionStore — persists ATProto session to avoid repeated logins
# ---------------------------------------------------------------------------

class SessionStore:
    """Atomic JSON persistence for ATProto client session string.

    The atproto ``AsyncClient`` exposes ``export_session_string()`` /
    ``AsyncClient()`` with a session-string constructor.  We save that
    opaque string and restore it on next startup so the bot doesn't
    call ``login()`` every time, which is rate-limited (30/5 min).
    """

    def __init__(self, path: str = 'session.json', max_age_hours: int = 23):
        self.path = path
        self.max_age = timedelta(hours=max_age_hours)

    def save(self, session_string: str) -> None:
        dir_name = os.path.dirname(self.path) or '.'
        fd, tmp = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({
                    'session': session_string,
                    'saved_at': datetime.now().isoformat(),
                }, f)
            shutil.move(tmp, self.path)
        except Exception as e:
            logger.warning(f"SessionStore save failed: {e}")
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load(self) -> Optional[str]:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            saved_at = datetime.fromisoformat(data['saved_at'])
            if datetime.now() - saved_at > self.max_age:
                logger.info("Persisted session expired — will login fresh.")
                return None
            return data['session']
        except Exception as e:
            logger.warning(f"SessionStore load failed: {e}")
            return None

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# ActivityBudget — hour/day rate-limit aware action budget
# ---------------------------------------------------------------------------

_DEFAULT_ACTION_COSTS = {
    'post': 3,
    'like': 3,
    'repost': 3,
    'follow': 3,
    'update': 2,
    'delete': 1,
}


class ActivityBudget:
    """Tracks action points against hourly and daily caps.

    All write operations in the Bluesky PDS cost *points* (CREATE=3,
    UPDATE=2, DELETE=1).  This class lets the bot pre-check whether
    an action fits the remaining budget and commit the cost after success.

    State is kept in-memory only; on restart the counters begin fresh,
    which is safe because PDS rate windows also reset.
    """

    def __init__(self, hourly_limit: int = 4500, daily_limit: int = 30000,
                 action_costs: Optional[Dict[str, int]] = None):
        self.hourly_limit = hourly_limit
        self.daily_limit = daily_limit
        self.costs = dict(_DEFAULT_ACTION_COSTS)
        if action_costs:
            self.costs.update(action_costs)

        self._hourly_used = 0
        self._daily_used = 0
        self._hour_start = _time.monotonic()
        self._day_start = _time.monotonic()

    def _maybe_reset(self) -> None:
        now = _time.monotonic()
        if now - self._hour_start >= 3600:
            self._hourly_used = 0
            self._hour_start = now
        if now - self._day_start >= 86400:
            self._daily_used = 0
            self._day_start = now

    def can_spend(self, action: str) -> bool:
        self._maybe_reset()
        cost = self.costs.get(action, 3)
        return (self._hourly_used + cost <= self.hourly_limit and
                self._daily_used + cost <= self.daily_limit)

    def spend(self, action: str) -> None:
        self._maybe_reset()
        cost = self.costs.get(action, 3)
        self._hourly_used += cost
        self._daily_used += cost

    @property
    def remaining_hourly(self) -> int:
        self._maybe_reset()
        return max(0, self.hourly_limit - self._hourly_used)

    @property
    def remaining_daily(self) -> int:
        self._maybe_reset()
        return max(0, self.daily_limit - self._daily_used)

    def summary(self) -> Dict[str, Any]:
        self._maybe_reset()
        return {
            'hourly': f'{self._hourly_used}/{self.hourly_limit}',
            'daily': f'{self._daily_used}/{self.daily_limit}',
            'remaining_hourly': self.remaining_hourly,
            'remaining_daily': self.remaining_daily,
        }
