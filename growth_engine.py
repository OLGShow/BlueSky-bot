#!/usr/bin/env python3
"""
Growth Engine — Quality Gate, A/B Engine, Trend Radar,
Repost Stage-2 Filter, Audience Memory, Daily Reports, Dry-Run.
"""

import re
import json
import math
import logging
import os
from datetime import datetime, timedelta
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1) Quality Gate
# ---------------------------------------------------------------------------

FLUFF_PATTERNS = [
    r'\bjust saying\b', r'\bto be honest\b', r'\bin my opinion\b',
    r'\bit is what it is\b', r'\bat the end of the day\b',
    r'\blet that sink in\b', r'\bthis is huge\b', r'\bbreaking\b',
    r'\byou won\'t believe\b', r'\bmind blown\b', r'\bgame changer\b',
    r'\bthoughts\?\s*$', r'^(good morning|gm|hello world)',
]
_FLUFF_RE = [re.compile(p, re.IGNORECASE) for p in FLUFF_PATTERNS]


def _signal_density(text: str) -> float:
    """Return 0-1 signal density: facts, conclusions, questions."""
    signals = 0
    if '?' in text:
        signals += 1
    if re.search(r'\d+%|\d+\.\d|\$\d|#\w', text):
        signals += 1
    if re.search(r'\b(because|therefore|however|result|data|study|report|shows?|found)\b', text, re.I):
        signals += 1
    if re.search(r'\b(key takeaway|bottom line|in short|tldr|takeaway)\b', text, re.I):
        signals += 1
    words = len(text.split())
    if words < 5:
        return 0.0
    return min(signals / 3.0, 1.0)


def _fluff_score(text: str) -> float:
    """Return 0-1 where higher = more fluff."""
    hits = sum(1 for rx in _FLUFF_RE if rx.search(text))
    return min(hits / 3.0, 1.0)


def _ngram_fingerprint(text: str, n: int = 3) -> Set[str]:
    words = re.findall(r'\b\w+\b', text.lower())
    return {' '.join(words[i:i+n]) for i in range(len(words) - n + 1)}


def semantic_similarity(a: str, b: str) -> float:
    fp_a = _ngram_fingerprint(a)
    fp_b = _ngram_fingerprint(b)
    if not fp_a or not fp_b:
        return 0.0
    return len(fp_a & fp_b) / len(fp_a | fp_b)


class QualityGate:
    def __init__(self, config: dict):
        qg = config.get('quality_gate_settings', {})
        self.min_signal = qg.get('min_signal_density', 0.3)
        self.max_fluff = qg.get('max_fluff_score', 0.4)
        self.max_semantic_sim = qg.get('max_semantic_similarity', 0.45)
        self.recent_window = qg.get('recent_posts_window', 15)
        self.max_regen = qg.get('max_regenerations', 2)

    def check(self, text: str, recent_posts: List[str]) -> Tuple[bool, str]:
        if not text or len(text.strip()) < 20:
            return False, 'too_short'

        sig = _signal_density(text)
        if sig < self.min_signal:
            return False, f'low_signal({sig:.2f}<{self.min_signal})'

        fluff = _fluff_score(text)
        if fluff > self.max_fluff:
            return False, f'too_fluffy({fluff:.2f}>{self.max_fluff})'

        for prev in recent_posts[-self.recent_window:]:
            sim = semantic_similarity(text, prev)
            if sim > self.max_semantic_sim:
                return False, f'semantic_dup({sim:.2f})'

        return True, 'ok'


# ---------------------------------------------------------------------------
# 2) A/B Engine
# ---------------------------------------------------------------------------

AB_FORMATS = {
    'format_a': {
        'name': '3 bullets + takeaway + question',
        'prompt_suffix': (
            '\n\nFormat: exactly 3 bullet points (use bullet chars), '
            'then one line "Takeaway:" with a concise insight, '
            'then end with an engaging question.'
        ),
    },
    'format_b': {
        'name': 'short argument + question',
        'prompt_suffix': (
            '\n\nFormat: one short paragraph (2-3 sentences) making a clear argument, '
            'then end with a thought-provoking question on a new line.'
        ),
    },
}


class ABEngine:
    def __init__(self, memory_ab: Dict):
        self.results = memory_ab  # {format_key: {impressions, total_er_1h, total_er_6h, total_er_24h}}
        for k in AB_FORMATS:
            self.results.setdefault(k, {'impressions': 0, 'total_er_1h': 0.0, 'total_er_6h': 0.0, 'total_er_24h': 0.0})

    def pick_format(self) -> str:
        total = sum(v['impressions'] for v in self.results.values())
        if total < 10:
            import random
            return random.choice(list(AB_FORMATS.keys()))
        scores = {}
        for k, v in self.results.items():
            n = max(v['impressions'], 1)
            scores[k] = v['total_er_24h'] / n
        best = max(scores, key=scores.get)
        import random
        if random.random() < 0.2:
            return random.choice(list(AB_FORMATS.keys()))
        return best

    def get_prompt_suffix(self, fmt_key: str) -> str:
        return AB_FORMATS.get(fmt_key, {}).get('prompt_suffix', '')

    def record_impression(self, fmt_key: str):
        self.results.setdefault(fmt_key, {'impressions': 0, 'total_er_1h': 0.0, 'total_er_6h': 0.0, 'total_er_24h': 0.0})
        self.results[fmt_key]['impressions'] += 1

    def record_er(self, fmt_key: str, er_1h: float = 0, er_6h: float = 0, er_24h: float = 0):
        if fmt_key not in self.results:
            return
        self.results[fmt_key]['total_er_1h'] += er_1h
        self.results[fmt_key]['total_er_6h'] += er_6h
        self.results[fmt_key]['total_er_24h'] += er_24h

    def summary(self) -> Dict:
        out = {}
        for k, v in self.results.items():
            n = max(v['impressions'], 1)
            out[k] = {
                'impressions': v['impressions'],
                'avg_er_24h': round(v['total_er_24h'] / n, 4),
            }
        return out


# ---------------------------------------------------------------------------
# 3) Trend Radar
# ---------------------------------------------------------------------------

class TrendRadar:
    def __init__(self, topic_groups: Dict):
        self.topic_groups = topic_groups

    def extract_trending(self, texts: List[str], top_n: int = 5) -> List[Tuple[str, int]]:
        tokens = []
        for t in texts:
            tokens.extend(re.findall(r'\b[a-zA-Z]{3,}\b', t.lower()))
        freq = Counter(tokens)
        all_keywords = set()
        for g in self.topic_groups.values():
            for kw in g.get('keywords', []):
                all_keywords.add(kw.lower())
        relevant = {k: v for k, v in freq.items() if k in all_keywords}
        return sorted(relevant.items(), key=lambda x: -x[1])[:top_n]

    def get_topic_of_day(self, texts: List[str]) -> Optional[str]:
        trending = self.extract_trending(texts, top_n=1)
        if trending:
            word = trending[0][0]
            for group_name, gdata in self.topic_groups.items():
                if word in [k.lower() for k in gdata.get('keywords', [])]:
                    return group_name
        return None


# ---------------------------------------------------------------------------
# 4) Repost Stage-2 Policy Filter
# ---------------------------------------------------------------------------

CONFLICT_WORDS = {
    'kill', 'murder', 'genocide', 'nazi', 'terrorist', 'rape',
    'lynching', 'ethnic cleansing', 'death threat',
}


class RepostPolicyFilter:
    def __init__(self, config: dict):
        rpf = config.get('engagement_settings', {}).get('repost_policy_filter', {})
        self.max_conflict_words = rpf.get('max_conflict_words', 2)
        self.author_cooldown = rpf.get('author_cooldown_posts', 3)
        self.max_age_hours = rpf.get('max_age_hours', 24)

    def check(self, text: str, author_did: str, post_created: Optional[datetime],
              recent_repost_authors: List[str]) -> Tuple[bool, str]:
        text_lower = text.lower()
        conflict_hits = sum(1 for w in CONFLICT_WORDS if w in text_lower)
        if conflict_hits >= self.max_conflict_words:
            return False, f'conflict({conflict_hits})'

        recent_tail = recent_repost_authors[-self.author_cooldown:]
        if author_did in recent_tail:
            return False, 'author_repeat'

        if post_created:
            age = datetime.now() - post_created
            if age > timedelta(hours=self.max_age_hours):
                return False, f'stale({age.total_seconds()/3600:.0f}h)'

        return True, 'ok'


# ---------------------------------------------------------------------------
# 5) Daily Report
# ---------------------------------------------------------------------------

def generate_daily_report(session_stats: Dict, memory, config: Dict) -> Dict:
    report = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'timestamp': datetime.now().isoformat(),
        'session': dict(session_stats),
        'memory_size': {
            'successful_posts': len(getattr(memory, 'successful_posts', [])),
            'viral_posts': len(getattr(memory, 'viral_posts', [])),
        },
        'top_topics': dict(Counter(
            p.get('type', 'unknown')
            for p in getattr(memory, 'successful_posts', [])[-50:]
        ).most_common(5)),
    }
    ab = getattr(memory, 'ab_results', {})
    if ab:
        report['ab_summary'] = ABEngine(ab).summary()
    src = getattr(memory, 'source_outcomes', {})
    if src:
        report['source_quality'] = {k: round(v.get('avg_er', 0), 4) for k, v in list(src.items())[:10]}
    return report


def save_daily_report(report: Dict, reports_dir: str = 'reports'):
    os.makedirs(reports_dir, exist_ok=True)
    path = os.path.join(reports_dir, f"daily_{report['date']}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"📊 Daily report saved: {path}")


# ---------------------------------------------------------------------------
# 6) Dry-Run wrapper
# ---------------------------------------------------------------------------

class DryRunAction:
    def __init__(self):
        self.actions: List[Dict] = []

    def log(self, action: str, **kwargs):
        entry = {'action': action, 'timestamp': datetime.now().isoformat(), **kwargs}
        self.actions.append(entry)
        logger.info(f"🧪 [DRY-RUN] would {action}: {kwargs}")

    def save(self, path: str = 'dry_run_report.json'):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.actions, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"🧪 Dry-run report saved: {path} ({len(self.actions)} actions)")
