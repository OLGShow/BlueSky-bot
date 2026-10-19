#!/usr/bin/env python3
"""
EngagementService — isolated execution layer for like/repost/follow actions.
Keeps bot behavior unchanged while reducing orchestration coupling.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EngagementService:
    def __init__(self, bot):
        self.bot = bot

    # --- engagement mode guard (fail-closed) ---

    def _engagement_allowed(self, target_did: Optional[str] = None,
                            target_handle: Optional[str] = None) -> bool:
        """Check if the current engagement_mode permits interaction with target."""
        cfg = getattr(self.bot, 'config', {})
        mode = cfg.get('engagement_mode', 'open')
        if mode == 'open':
            return True
        if mode == 'whitelist_only':
            whitelist = set(cfg.get('engagement_whitelist', []))
            if not whitelist:
                return False
            return (target_did in whitelist) or (target_handle in whitelist)
        if mode == 'mention_only':
            return False
        return True

    def _budget_ok(self, action: str) -> bool:
        budget = getattr(self.bot, 'activity_budget', None)
        if budget and not budget.can_spend(action):
            logger.warning(f"ActivityBudget exhausted for '{action}' — skipping")
            return False
        return True

    def _budget_commit(self, action: str) -> None:
        budget = getattr(self.bot, 'activity_budget', None)
        if budget:
            budget.spend(action)

    async def like(self, uri: str, cid: str, score: float,
                   author_did: Optional[str] = None, author_handle: Optional[str] = None) -> bool:
        if not self._engagement_allowed(author_did, author_handle):
            return False
        key = f"like:{uri}"
        if self.bot.action_ledger.contains(key) or uri in self.bot.liked_posts:
            return False
        if not self._budget_ok('like'):
            return False
        if self.bot.dry_run:
            self.bot.dry_run_log.log('like', uri=uri, score=score)
        else:
            await self.bot.bluesky_client.like(uri, cid)
        self._budget_commit('like')
        self.bot.action_ledger.record(key)
        self.bot.session_stats['likes_given'] += 1
        self.bot.liked_posts.add(uri)
        logging.getLogger('audit').info(f"LIKE uri={uri} score={score:.2f}")
        return True

    async def repost(self, uri: str, cid: str, score: float, author_did: str,
                     author_handle: Optional[str] = None) -> bool:
        if not self._engagement_allowed(author_did, author_handle):
            return False
        key = f"repost:{uri}"
        if self.bot.action_ledger.contains(key) or uri in self.bot.reposted_posts:
            return False
        if not self._budget_ok('repost'):
            return False
        if self.bot.dry_run:
            self.bot.dry_run_log.log('repost', uri=uri, score=score)
        else:
            await self.bot.bluesky_client.repost(uri, cid)
        self._budget_commit('repost')
        self.bot.action_ledger.record(key)
        self.bot.session_stats['reposts_made'] += 1
        self.bot.reposted_posts.add(uri)
        self.bot.recent_repost_authors.append(author_did)
        logging.getLogger('audit').info(f"REPOST uri={uri} score={score:.2f}")
        return True

    async def follow(self, did: str, handle: str, source: Optional[str] = None) -> bool:
        if not self._engagement_allowed(did, handle):
            return False
        key = f"follow:{did}"
        if self.bot.action_ledger.contains(key) or did in self.bot.followed_users:
            return False
        if not self._budget_ok('follow'):
            return False
        if self.bot.dry_run:
            self.bot.dry_run_log.log('follow', handle=handle, did=did, source=source or 'suggestions')
        else:
            await self.bot.bluesky_client.follow(did)
            self.bot.followed_users.add(did)
        self._budget_commit('follow')
        self.bot.action_ledger.record(key)
        self.bot.session_stats['follows_made'] += 1
        suffix = f" source={source}" if source else ""
        logging.getLogger('audit').info(f"FOLLOW did={did}{suffix}")
        return True

