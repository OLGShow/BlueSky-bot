#!/usr/bin/env python3
"""
RSS Source Manager — dynamic source pool with quality scoring,
auto-discovery, and rotation (active / probation / disabled).
"""

import json
import os
import time
import logging
import aiohttp
import feedparser
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

SEED_FEEDS = {
    'ai': [
        'https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml',
        'https://feeds.feedburner.com/NewOnMit-TechnologyReview',
    ],
    'tech': [
        'https://news.ycombinator.com/rss',
        'https://dev.to/feed',
        'https://arstechnica.com/feed/',
        'https://www.wired.com/feed/rss',
        'https://techcrunch.com/feed/',
    ],
    'policy': [
        'https://www.theguardian.com/world/rss',
        'https://feeds.bbci.co.uk/news/world/rss.xml',
        'https://feeds.npr.org/1001/rss.xml',
    ],
    'economy': [
        'https://feeds.feedburner.com/venturebeat/SZYF',
        'https://feeds.feedburner.com/fastcompany/headlines',
    ],
    'climate': [
        'https://www.theguardian.com/technology/rss',
        'https://www.nature.com/subjects/computer-science.rss',
    ],
    'culture': [
        'https://boingboing.net/feed',
        'https://feeds.feedburner.com/slashdot/eqWf',
    ],
    'security': [
        'https://krebsonsecurity.com/feed/',
        'https://feeds.bbci.co.uk/news/technology/rss.xml',
    ],
}


class RSSSourceManager:
    STATE_FILE = 'rss_source_state.json'

    def __init__(self, config: dict, http_session: Optional[aiohttp.ClientSession] = None):
        self.config = config
        self.http_session = http_session
        self.sources: Dict[str, Dict] = {}
        self._load_state()
        self._ensure_seeds()

    def _ensure_seeds(self):
        for axis, urls in SEED_FEEDS.items():
            for url in urls:
                if url not in self.sources:
                    self.sources[url] = {
                        'url': url,
                        'axis': axis,
                        'state': 'active',
                        'success': 0,
                        'fail': 0,
                        'total_entries': 0,
                        'duplicates': 0,
                        'avg_latency': 0.0,
                        'last_ok': None,
                        'last_fail': None,
                        'added': datetime.now().isoformat(),
                    }

    def _load_state(self):
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE, 'r') as f:
                    self.sources = json.load(f)
                logger.info(f"📡 RSS state loaded: {len(self.sources)} sources")
            except Exception as e:
                logger.warning(f"⚠️ RSS state load error: {e}")
                self.sources = {}

    def save_state(self):
        try:
            with open(self.STATE_FILE, 'w') as f:
                json.dump(self.sources, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"⚠️ RSS state save error: {e}")

    def get_active_urls(self) -> List[str]:
        return [url for url, s in self.sources.items() if s.get('state') == 'active']

    def get_probation_urls(self) -> List[str]:
        return [url for url, s in self.sources.items() if s.get('state') == 'probation']

    def quality_score(self, url: str) -> float:
        s = self.sources.get(url, {})
        total = s.get('success', 0) + s.get('fail', 0)
        if total == 0:
            return 0.5
        success_rate = s.get('success', 0) / total
        latency_penalty = min(s.get('avg_latency', 1.0) / 5.0, 1.0)
        dup_rate = s.get('duplicates', 0) / max(s.get('total_entries', 1), 1)
        return max(0, success_rate - latency_penalty * 0.2 - dup_rate * 0.3)

    def record_fetch(self, url: str, success: bool, entries: int = 0, latency: float = 0, duplicates: int = 0):
        if url not in self.sources:
            return
        s = self.sources[url]
        if success:
            s['success'] = s.get('success', 0) + 1
            s['total_entries'] = s.get('total_entries', 0) + entries
            s['last_ok'] = datetime.now().isoformat()
            old_lat = s.get('avg_latency', latency)
            s['avg_latency'] = round(old_lat * 0.7 + latency * 0.3, 2)
        else:
            s['fail'] = s.get('fail', 0) + 1
            s['last_fail'] = datetime.now().isoformat()
        s['duplicates'] = s.get('duplicates', 0) + duplicates

    def rotate(self):
        for url, s in self.sources.items():
            q = self.quality_score(url)
            total = s.get('success', 0) + s.get('fail', 0)
            if total < 3:
                continue
            if s['state'] == 'active' and q < 0.3:
                s['state'] = 'probation'
                logger.info(f"📡 Source -> probation: {url} (q={q:.2f})")
            elif s['state'] == 'probation' and q < 0.15:
                s['state'] = 'disabled'
                logger.info(f"📡 Source -> disabled: {url} (q={q:.2f})")
            elif s['state'] == 'probation' and q > 0.5:
                s['state'] = 'active'
                logger.info(f"📡 Source -> active (recovered): {url} (q={q:.2f})")
        self.save_state()

    def add_candidate(self, url: str, axis: str = 'general'):
        if url not in self.sources:
            self.sources[url] = {
                'url': url, 'axis': axis, 'state': 'probation',
                'success': 0, 'fail': 0, 'total_entries': 0,
                'duplicates': 0, 'avg_latency': 0.0,
                'last_ok': None, 'last_fail': None,
                'added': datetime.now().isoformat(),
            }
            logger.info(f"📡 New RSS candidate added: {url} ({axis})")

    def summary(self) -> Dict:
        states = defaultdict(int)
        for s in self.sources.values():
            states[s.get('state', 'unknown')] += 1
        return dict(states)
