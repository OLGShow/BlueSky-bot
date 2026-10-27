#!/usr/bin/env python3
"""
EngagementService — isolated execution layer for like/repost/follow actions.

Depends only on EngagementPorts (ADR-001 / REF-002). Must not import
bluesky_bot_v2; the bot remains the composition root that builds ports.
"""

from __future__ import annotations

import logging
from typing import Optional

from api_incident_log import record_incident
from engagement_ports import EngagementPorts

logger = logging.getLogger(__name__)


class EngagementService:
    def __init__(self, ports: EngagementPorts):
        self._ports = ports

    # --- engagement mode guard (fail-closed) ---

    def _engagement_allowed(self, target_did: Optional[str] = None,
                            target_handle: Optional[str] = None) -> bool:
        """Check if the current engagement_mode permits interaction with target."""
        cfg = self._ports.config
        mode = cfg.mode
        if mode == 'open':
            return True
        if mode == 'whitelist_only':
            whitelist = cfg.whitelist
            if not whitelist:
                return False
            return (target_did in whitelist) or (target_handle in whitelist)
        if mode == 'mention_only':
            return False
        return True

    def _budget_ok(self, action: str) -> bool:
        if not self._ports.budget.can_spend(action):
            logger.warning(f"ActivityBudget exhausted for '{action}' — skipping")
            return False
        return True

    def _budget_commit(self, action: str) -> None:
        self._ports.budget.spend(action)

    async def _atproto_write(self, fn, *args, **kwargs):
        """Run engagement ATProto write via optional RetryPolicy (RETRY-003)."""
        retry = self._ports.retry
        if retry is not None:
            return await retry.execute(fn, *args, **kwargs)
        return await fn(*args, **kwargs)

    async def like(self, uri: str, cid: str, score: float,
                   author_did: Optional[str] = None, author_handle: Optional[str] = None) -> bool:
        ports = self._ports
        if not self._engagement_allowed(author_did, author_handle):
            return False
        key = f"like:{uri}"
        if ports.ledger.contains(key) or uri in ports.identity.liked_posts:
            return False
        if not self._budget_ok('like'):
            return False
        if ports.dry_run.enabled:
            ports.dry_run.log('like', uri=uri, score=score)
        else:
            try:
                await self._atproto_write(ports.client.like, uri, cid)
            except Exception as e:
                record_incident(
                    "like",
                    "like",
                    exc=e,
                    uri=uri,
                    did=author_did,
                )
                raise
        self._budget_commit('like')
        ports.ledger.record(key)
        ports.stats['likes_given'] += 1
        ports.identity.liked_posts.add(uri)
        logging.getLogger('audit').info(f"LIKE uri={uri} score={score:.2f}")
        return True

    async def repost(self, uri: str, cid: str, score: float, author_did: str,
                     author_handle: Optional[str] = None) -> bool:
        ports = self._ports
        if not self._engagement_allowed(author_did, author_handle):
            return False
        key = f"repost:{uri}"
        if ports.ledger.contains(key) or uri in ports.identity.reposted_posts:
            return False
        if not self._budget_ok('repost'):
            return False
        if ports.dry_run.enabled:
            ports.dry_run.log('repost', uri=uri, score=score)
        else:
            try:
                await self._atproto_write(ports.client.repost, uri, cid)
            except Exception as e:
                record_incident(
                    "repost",
                    "repost",
                    exc=e,
                    uri=uri,
                    did=author_did,
                )
                raise
        self._budget_commit('repost')
        ports.ledger.record(key)
        ports.stats['reposts_made'] += 1
        ports.identity.reposted_posts.add(uri)
        ports.identity.recent_repost_authors.append(author_did)
        logging.getLogger('audit').info(f"REPOST uri={uri} score={score:.2f}")
        return True

    async def follow(self, did: str, handle: str, source: Optional[str] = None) -> bool:
        ports = self._ports
        if not self._engagement_allowed(did, handle):
            return False
        key = f"follow:{did}"
        if ports.ledger.contains(key) or did in ports.identity.followed_users:
            return False
        if not self._budget_ok('follow'):
            return False
        if ports.dry_run.enabled:
            ports.dry_run.log('follow', handle=handle, did=did, source=source or 'suggestions')
        else:
            try:
                await self._atproto_write(ports.client.follow, did)
            except Exception as e:
                record_incident(
                    "follow",
                    "follow",
                    exc=e,
                    did=did,
                    extra={"source": source} if source else None,
                )
                raise
            ports.identity.followed_users.add(did)
        self._budget_commit('follow')
        ports.ledger.record(key)
        ports.stats['follows_made'] += 1
        suffix = f" source={source}" if source else ""
        logging.getLogger('audit').info(f"FOLLOW did={did}{suffix}")
        return True
