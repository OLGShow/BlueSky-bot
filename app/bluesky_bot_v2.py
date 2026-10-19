#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автономный бот для BlueSky v2.1 с качественным оформлением постов
ИСПРАВЛЕНА ПРОБЛЕМА МАССОВОЙ ПУБЛИКАЦИИ И УЛУЧШЕНО КАЧЕСТВО КОНТЕНТА
"""

import asyncio
import random
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict
from typing import Any, List, Dict, Optional, Set, Tuple, Callable
import aiohttp
import feedparser
from atproto import AsyncClient, models
from dynamic_content_system import BlueSkyTrendingTracker, DynamicContentGenerator
from trends_engagement import (
    CallableFeedPage as TrendsCallableFeedPage,
    CallableRelevance as TrendsCallableRelevance,
    TrendsEngagementConfig,
    TrendsEngagementOrchestrator,
    TrendsEngagementPorts,
)
import openai
from openai import AsyncOpenAI
from dataclasses import dataclass, asdict, field
import re
import time
import html
import hashlib
from dotenv import load_dotenv
from policy_learner import (
    PolicyLearner,
    eligible_catch_up_checks,
    eligible_format_catch_up_checks,
)
from follower_tracker import delta_between
from engagement_learner import eligible_engagement_catch_up_checks
from learning_orchestrator import LearningOrchestrator

# Новые импорты для форматирования
from bluesky_post_formatter import BlueskyPostFormatter, PostTemplates, RichTextPost
from bluesky_rich_posts import BlueskyRichPostCreator, PostFactory, ImageData, LinkCard

# AI adapters: OpenRouter (preferred) or Pollinations (legacy)
from pollinations_adapter import PollinationsAI
from openrouter_adapter import OpenRouterAI

# Импорт улучшений AI
from ai_improvements import ContentQualityAnalyzer, EngagementOptimizer
from growth_engine import (
    QualityGate, ABEngine, TrendRadar, RepostPolicyFilter,
    DryRunAction, generate_daily_report, save_daily_report,
)
from rss_source_manager import RSSSourceManager
from state_service import (
    StateService, ActionLedger, AtomicConfigWriter,
    SingleInstanceLock, SessionStore, ActivityBudget,
)
from resilience_service import (
    CircuitBreaker,
    RetryPolicy,
    ErrorClass,
    classify_error,
    backoff_seconds,
    OutboundRetryPolicies,
    build_outbound_retry_policies,
)
from safety_governor import SafetyStatus
from log_sanitizer import SanitizingFilter
from engagement_ports import (
    DryRunGate,
    EngagementPorts,
    LiveEngagementConfig,
    LiveEngagementIdentity,
    UnlimitedBudget,
)
from engagement_service import EngagementService
from content_ports import (
    ContentPorts,
    LiveBackgroundScheduler,
    LivePromptContext,
)
from post_strategies import (
    PostStrategyRegistry,
    StrategyLookupError,
    build_bound_registry,
)
from content_service import (
    ContentService,
    OutboundContentError,
    BLUESKY_MAX_GRAPHEMES,
    validate_outbound_text,
    split_graphemes,
)
from http_session import (
    create_http_session,
    ensure_http_session,
    close_http_session,
)
from quality_pipeline import (
    QualityContext,
    QualityPipeline,
    QualityResult,
)
from url_safety import UnsafeURLError, validate_outbound_url
from strategies.dynamic_posts import (
    PERSONAL_OPINION_STRATEGY_NAME,
    QUALITY_DISCUSSION_STRATEGY_NAME,
    QUALITY_TIP_STRATEGY_NAME,
    PersonalOpinionStrategy,
    QualityDiscussionStrategy,
    QualityTipStrategy,
)
from strategies.image_post import ImagePostHelper, ThemePostHelper
from strategies.insight_posts import (
    PERSONAL_INSIGHT_STRATEGY_NAME,
    PREDICTION_STRATEGY_NAME,
    PersonalInsightStrategy,
    PredictionStrategy,
)
from strategies.poll_post import (
    STRATEGY_NAME as POLL_STRATEGY_NAME,
    QualityPollStrategy,
)
from strategies.ports import (
    CallableDuplicateContent,
    CallableDynamicContent,
    CallableFallbackPost,
    CallableImageGenerator,
    CallableImagePrompt,
    CallableImageUpload,
    CallableLinkPreview,
    CallablePollFactory,
    CallablePostFactory,
    CallableRssHeadlines,
    CallableStrategyLookup,
    CallableStructuredContent,
    CallableViralPrompts,
    DuplicateFallbackPorts,
    DynamicPostsPorts,
    ImagePostPorts,
    LiveRssFeeds,
    NewsStrategyPorts,
    PollStrategyPorts,
    SoftFailPorts,
    ThemePostPorts,
    ViralPostsPorts,
)
from strategies.quality_news import STRATEGY_NAME, QualityNewsStrategy
from strategies.soft_fail_posts import (
    EMERGENCY_STRATEGY_NAME,
    MOTIVATIONAL_STRATEGY_NAME,
    DuplicateFallbackHelper,
    EmergencyUniqueStrategy,
    MotivationalMomentStrategy,
)
from strategies.theme_posts import (
    AI_INSIGHT_STRATEGY_NAME,
    LIST_STRATEGY_NAME,
    QualityAiInsightStrategy,
    QualityListStrategy,
)
from strategies.viral_posts import (
    TRENDING_COMMENTARY_STRATEGY_NAME,
    VIRAL_HOT_TAKE_STRATEGY_NAME,
    TrendingCommentaryStrategy,
    ViralHotTakeStrategy,
)
from bot_cycle import BotCycleRunner, CallableBotCyclePorts, TickResult
from content_publish_state import ContentPublishState
from daily_reporting import DailyReportingFacade
from engagement_cache_sync import (
    hydrate_engagement_caches_from_memory,
    sync_engagement_caches_to_memory,
)
from follow_strategy import CallableFollowPorts, FollowStrategyOrchestrator
from follow_strategy import should_follow_user as follow_should_follow_user
from heartbeat_monitor import HeartbeatMonitor
from relevance_scoring import calculate_relevance as score_post_relevance
from rss_content import RssContentFetcher, RssContentPorts
from rss_content import clean_html as rss_clean_html
from smart_engagement import (
    CallableRelevance,
    CallableRepostPolicy,
    CallableTimelinePage,
    SmartEngagementConfig,
    SmartEngagementOrchestrator,
    SmartEngagementPorts,
)
from publish_ports import PublishPorts
from publish_orchestrator import ScheduledPostPublisher
from auth_service import AuthPorts, AuthService
from media_service import MediaPorts, MediaService
from health_service import HealthPorts, HealthService
# Настройка логирования с абсолютным путем
import sys

# На Windows консоль часто в cp1251/cp866, из-за чего эмодзи ломают logging.
# Принудительно переключаем stdout/stderr на UTF-8, чтобы не падать при логировании.
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

# Определяем путь к файлу лога
if hasattr(sys, '_MEIPASS'):
    # Если запущено из pyinstaller
    log_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
else:
    # Обычный запуск
    log_dir = os.path.dirname(os.path.abspath(__file__))

log_file_path = os.path.join(log_dir, 'bot.log')

# Создаем директорию если не существует
os.makedirs(log_dir, exist_ok=True)

# Ограничения логов для маленького диска (40GB)
LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', 20 * 1024 * 1024))        # 20MB на файл
LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', 8))                  # до 8 ротаций
LOG_TOTAL_BUDGET_BYTES = int(os.getenv('LOG_TOTAL_BUDGET_BYTES', 1024 * 1024 * 1024))  # 1GB суммарно


def _cleanup_log_budget(directory: str, budget_bytes: int) -> tuple[int, int]:
    """Удаляет самые старые log-файлы, если суммарный размер > budget_bytes."""
    candidates = []
    for name in os.listdir(directory):
        if not name.endswith('.log') and '.log.' not in name:
            continue
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            try:
                st = os.stat(path)
                candidates.append((path, st.st_mtime, st.st_size))
            except OSError:
                continue

    total = sum(s for _, _, s in candidates)
    removed_files = 0
    removed_bytes = 0
    if total <= budget_bytes:
        return removed_files, removed_bytes

    # Удаляем самые старые сначала
    for path, _, size in sorted(candidates, key=lambda x: x[1]):
        # Никогда не удаляем активный bot.log
        if os.path.basename(path) == 'bot.log':
            continue
        try:
            os.remove(path)
            removed_files += 1
            removed_bytes += size
            total -= size
            if total <= budget_bytes:
                break
        except OSError:
            continue
    return removed_files, removed_bytes

# Настройка логирования с санитизацией
_sanitizer = SanitizingFilter()
_file_handler = RotatingFileHandler(
    log_file_path, encoding='utf-8', maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT
)
_file_handler.addFilter(_sanitizer)
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.addFilter(_sanitizer)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[_file_handler, _console_handler],
    force=True,
)
logger = logging.getLogger(__name__)

# Audit logger — отдельный файл для аудита действий
_audit_handler = RotatingFileHandler(
    os.path.join(log_dir, 'audit.log'),
    encoding='utf-8',
    maxBytes=max(5 * 1024 * 1024, LOG_MAX_BYTES // 2),
    backupCount=max(4, LOG_BACKUP_COUNT // 2),
)
_audit_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
_audit_handler.addFilter(_sanitizer)
audit_logger = logging.getLogger('audit')
audit_logger.addHandler(_audit_handler)
audit_logger.propagate = False

# Логируем путь к файлу для отладки
logger.info(f"📝 Логирование настроено. Файл лога: {log_file_path}")
logger.info(f"📂 Рабочая директория: {os.getcwd()}")
logger.info(f"🐍 Python путь: {sys.executable}")
removed_files, removed_bytes = _cleanup_log_budget(log_dir, LOG_TOTAL_BUDGET_BYTES)
if removed_files:
    logger.warning(
        f"🧹 Очистка логов по бюджету: удалено {removed_files} файлов, "
        f"освобождено {removed_bytes / (1024 * 1024):.1f} MB"
    )

# Соблюдение правил BlueSky
BLUESKY_COMPLIANT_MODE = True  # Отключает автоматические комментарии и упоминания
NO_AUTO_COMMENTS = True  # Никаких автоматических комментариев (нарушение правил)
NO_AUTO_MENTIONS = True  # Никаких автоматических упоминаний (нарушение правил)
ONLY_LIKES_AND_REPOSTS = True  # Только лайки, репосты, подписки и собственные посты


@dataclass
class BotMemory:
    """Память бота для самообучения"""
    successful_posts: List[Dict]
    failed_posts: List[Dict]
    interaction_patterns: Dict[str, float]
    trending_topics: Dict[str, int]
    user_relationships: Dict[str, Dict]
    content_performance: Dict[str, float]
    last_update: datetime
    # Новое поле для предотвращения дубликатов
    published_content_hashes: Set[str] = field(default_factory=set)
    published_urls: Set[str] = field(default_factory=set)
    # НОВОЕ: Tracking репостов и вирусности
    repost_performance: List[Dict] = field(default_factory=list)
    viral_posts: List[Dict] = field(default_factory=list)
    engagement_metrics: Dict[str, float] = field(default_factory=dict)
    # Growth engine fields
    ab_results: Dict = field(default_factory=dict)
    topic_outcomes: Dict[str, Dict] = field(default_factory=dict)
    source_outcomes: Dict[str, Dict] = field(default_factory=dict)
    pattern_blacklist: List[str] = field(default_factory=list)
    # PLRN-011: liked/reposted foreign posts for topic-arm credit
    engagement_actions: List[Dict] = field(default_factory=list)
    
    _state_svc = StateService()

    def save(self, filename: str = 'bot_memory.json'):
        """Сохранение памяти через StateService (JSON, атомарная запись)."""
        self._state_svc.save(self)

    @classmethod
    def load(cls, filename: str = 'bot_memory.json'):
        """Загрузка памяти через StateService (JSON с миграцией с pickle)."""
        return cls._state_svc.load(cls)

class AutonomousBlueskyBotV2:
    """Улучшенная версия бота с качественным оформлением постов"""
    
    def __init__(self):
        """Инициализация автономного BlueSky бота"""
        
        # Credentials: env-only (no interactive prompt / vault)
        self.handle = (os.getenv('BLUESKY_HANDLE') or '').strip()
        self.password = (os.getenv('BLUESKY_PASSWORD') or '').strip()
        
        if not self.handle or not self.password:
            raise ValueError("❌ Необходимо установить BLUESKY_HANDLE и BLUESKY_PASSWORD в переменных окружения")
        
        # Клиенты для BlueSky
        self.bluesky_client = AsyncClient()
        self.authenticated = False
        self.session_store = SessionStore(
            path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'session.json')
        )
        
        # Единая HTTP сессия для всех операций с таймаутами
        self.http_session = None
        self._create_http_session()

        # Per-subsystem circuit breakers + outbound RetryPolicy bundle (RETRY-001/002).
        # Built before AI adapters so policies pass from composition root.
        self._cb_bluesky = CircuitBreaker('bluesky_api', failure_threshold=5, recovery_timeout=300)
        self._cb_ai = CircuitBreaker('ai_generation', failure_threshold=3, recovery_timeout=180)
        self._cb_rss = CircuitBreaker('rss_fetch', failure_threshold=4, recovery_timeout=120)
        self.retry_policies: OutboundRetryPolicies = build_outbound_retry_policies(
            cb_bluesky=self._cb_bluesky,
            cb_ai=self._cb_ai,
            cb_rss=self._cb_rss,
        )
        self.retry_atproto = self.retry_policies.atproto
        self.retry_ai = self.retry_policies.ai
        self.retry_rss_http = self.retry_policies.rss_http
        self.retry_media_upload = self.retry_policies.media_upload
        
        # AI clients — OpenRouter (gpt-4o-mini) preferred; Pollinations legacy fallback
        bot_language = (os.getenv('BOT_LANGUAGE') or 'en').split('#', 1)[0].strip().lower()
        if bot_language not in ('en', 'ru'):
            bot_language = 'en'

        openrouter_key = (os.getenv('OPENROUTER_API_KEY') or '').strip()
        if openrouter_key:
            self.pollinations_ai = OpenRouterAI(
                api_key=openrouter_key,
                default_model='creative',
                language=bot_language,
                model_id=os.getenv('OPENROUTER_MODEL') or 'openai/gpt-4o-mini',
                http_session=self.http_session,
                retry_policy=self.retry_ai,
            )
            logger.info(
                "OpenRouter AI primary (%s), text=%s, image=%s",
                bot_language.upper(),
                getattr(self.pollinations_ai, 'model_id', 'openai/gpt-4o-mini'),
                getattr(self.pollinations_ai, 'image_model_id', 'openai/gpt-image-1-mini'),
            )
        else:
            self.pollinations_ai = PollinationsAI(
                default_model='creative',
                language=bot_language,
                http_session=self.http_session,
                retry_policy=self.retry_ai,
            )
            logger.warning("OPENROUTER_API_KEY not set — using legacy Pollinations.AI")

        self._inject_http_session_into_adapters()

        self.ai_client = None  # Direct OpenAI as optional backup

        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key and openai_key != 'your-openai-key':
            try:
                self.ai_client = AsyncOpenAI(api_key=openai_key)
                logger.info("OpenAI client initialized as backup")
            except Exception as e:
                logger.warning(f"OpenAI backup unavailable: {e}")
        
        # Инициализация форматировщиков с передачей клиента для резолва DID
        self.formatter = BlueskyPostFormatter(
            client=self.bluesky_client,
            http_session=self.http_session,
        )
        self.rich_creator = BlueskyRichPostCreator(
            self.bluesky_client,
            http_session=self.http_session,
        )
        self._inject_http_session_into_adapters()
        
        # НОВОЕ: Проверка соблюдения правил BlueSky
        if BLUESKY_COMPLIANT_MODE:
            logger.info("🛡️ Включен режим соблюдения правил BlueSky:")
            logger.info("   🚫 Автоматические комментарии: ОТКЛЮЧЕНЫ")
            logger.info("   🚫 Автоматические упоминания: ОТКЛЮЧЕНЫ") 
            logger.info("   ✅ Лайки и репосты: РАЗРЕШЕНЫ")
            logger.info("   ✅ Собственные посты: РАЗРЕШЕНЫ")
        
        self.post_interval = (60, 90)
        self.max_posts_per_day = 10
        self.max_interactions_per_cycle = 5
        self.daily_post_count = 0
        self.last_post_date = datetime.now().date()
        
        # Контроль качества постов
        self.min_post_quality_score = 0.7  # Минимальный балл качества
        self.require_hashtags = True  # Обязательные хештеги
        self.require_visual_content = False  # Пока отключено
        
        # Bot settings optimized for English-speaking BlueSky audience (94.4%)
        # Topics based on popular BlueSky content analysis
        self.topics = [
            # TOP trending topics (based on analysis)
            'art and creativity', 'programming and development', 'philosophy of life',
            'culture and traditions', 'nature and ecology', 'modern technology', 
            'travel and discovery', 'education and self-development', 'humor and entertainment',
            
            # Tech topics (very popular on BlueSky)
            'artificial intelligence', 'machine learning', 'digital innovation',
            'process automation', 'startups and entrepreneurship', 'web development',
            'open source', 'cybersecurity', 'blockchain and crypto',
            
            # Creative topics
            'photography and visual arts', 'music and sound', 'design and aesthetics',
            'literature and books', 'movies and series', 'gaming and interactive',
            
            # Social topics
            'relationship psychology', 'career and professional growth', 'family and parenting',
            'health and wellness', 'sports and active lifestyle', 'mental health',
            
            # Everyday topics
            'food and cooking', 'home and comfort', 'animals and pets', 'news and events',
            'motivation and personal growth', 'dreams and plans', 'climate change',
            'social justice', 'politics and society'
        ]
        self.languages = ['en']  # Bluesky audience: English only
        
        # Состояние бота
        self.memory = BotMemory.load()
        self.session_stats = {
            'posts_created': 0,
            'likes_given': 0,
            'reposts_made': 0,
            'follows_made': 0,
            'comments_made': 0,  # Добавляем статистику комментариев
            'errors': 0
        }
        
        # НОВОЕ: Защита от повторных действий (с восстановлением из памяти / CACHE-001)
        _hydrated = hydrate_engagement_caches_from_memory(self.memory)
        self.commented_posts = _hydrated["commented_posts"]
        self.recent_comments = _hydrated["recent_comments"]
        self.liked_posts = _hydrated["liked_posts"]
        self.reposted_posts = _hydrated["reposted_posts"]
        self.followed_users = _hydrated["followed_users"]
        
        # Кэши
        self.hashtag_cache = {}
        self.user_cache = {}
        self.content_cache = []
        
        # RSS feeds optimized for English-speaking BlueSky audience
        self.rss_feeds = [
            # Tech & Programming - very popular on BlueSky
            'https://news.ycombinator.com/rss',  # Hacker News ✅ 0.9s, 30 entries
            'https://www.reddit.com/r/programming/.rss',  # Reddit Programming ✅ 0.7s, 25 entries
            'https://dev.to/feed',  # Dev.to articles ✅ Tech community favorite
            'https://techcrunch.com/feed/',  # TechCrunch ✅ Latest tech news
            'https://feeds.feedburner.com/venturebeat/SZYF',  # VentureBeat ✅ Startup news
            'https://www.theverge.com/rss/index.xml',  # The Verge ✅ Tech culture
            'https://arstechnica.com/feed/',  # Ars Technica ✅ Deep tech analysis
            
            # World News - international perspective
            'https://www.theguardian.com/world/rss',  # The Guardian World ✅ 0.3s, 45 entries
            'https://www.theguardian.com/technology/rss',  # The Guardian Tech ✅
            'https://rt.com/rss/',  # RT English ✅ 0.3s, 100 entries
            'https://www.reuters.com/rssFeed/technologyNews',  # Reuters Tech ✅
            'https://feeds.npr.org/1001/rss.xml',  # NPR News ✅
            'https://feeds.bbci.co.uk/news/technology/rss.xml',  # BBC Technology ✅
            'https://feeds.bbci.co.uk/news/world/rss.xml',  # BBC World ✅
            
            # Business & Startup - relevant for BlueSky audience
            'https://feeds.feedburner.com/entrepreneur/latest',  # Entrepreneur ✅
            'https://feeds.feedburner.com/fastcompany/headlines',  # Fast Company ✅
            'https://www.wired.com/feed/rss',  # Wired ✅ Innovation focus
            'https://feeds.feedburner.com/ommalik',  # GigaOm ✅ Future tech
            
            # Science & Innovation - popular topics
            'https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml',  # AI News ✅
            'https://www.nature.com/subjects/computer-science.rss',  # Nature CS ✅
            'https://feeds.feedburner.com/NewOnMit-TechnologyReview',  # MIT Tech Review ✅
            
            # Alternative/Independent voices - important for BlueSky demographic
            'https://boingboing.net/feed',  # Boing Boing ✅ Digital culture
            'https://feeds.feedburner.com/slashdot/eqWf',  # Slashdot ✅ Geek news
            'https://krebsonsecurity.com/feed/',  # Krebs Security ✅
            

        ]
        
        logger.info(f"🤖 Bot v2.1 optimized for English BlueSky audience initialized for {self.handle}")
        
        # Загрузка внешней конфигурации
        self.config = self.load_external_config()

        # Порог качества публикации из конфига (по умолчанию прежнее значение 0.7)
        quality_cfg = self.config.get('quality_gate_settings', {})
        cfg_min_quality = quality_cfg.get('min_combined_score', self.min_post_quality_score)
        try:
            self.min_post_quality_score = max(0.4, min(float(cfg_min_quality), 0.95))
        except (TypeError, ValueError):
            pass

        # Применяем лимиты из конфига (с безопасным потолком)
        limits = self.config.get('bluesky_limits', {})
        interval = limits.get('post_interval_minutes', [60, 90])
        if isinstance(interval, list) and len(interval) >= 2:
            self.post_interval = (interval[0], interval[1])
        self.max_posts_per_day = min(limits.get('max_posts_per_day', 10), 50)
        self.max_interactions_per_cycle = limits.get('max_interactions_per_cycle', 5)

        # Official «Актуальные» (getTrends) — filter applies to trends only, not RSS
        self.trending_tracker = BlueSkyTrendingTracker(
            self.bluesky_client,
            config=self.config.get("trends", {}),
        )
        self.dynamic_generator = DynamicContentGenerator(self.trending_tracker)
        
        # НОВОЕ: Инициализация улучшенных AI компонентов
        self.content_analyzer = ContentQualityAnalyzer()
        self.engagement_optimizer = EngagementOptimizer()

        # Action ledger for idempotency
        self.action_ledger = ActionLedger()

        # Activity budget (ATProto write-point caps)
        budget_cfg = self.config.get('activity_budget', {})
        self.activity_budget = ActivityBudget(
            hourly_limit=budget_cfg.get('hourly_points', 4500),
            daily_limit=budget_cfg.get('daily_points', 30000),
            action_costs=budget_cfg.get('action_costs'),
        )

        # Growth Engine
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() in ('true', '1', 'yes')
        self.dry_run_log = DryRunAction() if self.dry_run else None
        # A/B suffix for current generation cycle
        self._current_ab_format = 'format_a'
        self._current_ab_suffix = ''
        # Config key of the strategy chosen for the current post (PLRN-001)
        self._current_strategy_key: Optional[str] = None
        self._quality_gate_regen_mode = False
        # Circuit breaker (main loop level)
        self._consecutive_errors = 0
        # Trend Radar signal caches
        self._trend_timeline_snippets: list = []
        self._trend_rss_headlines: list = []
        # Async task registry
        self._background_tasks: set = set()
        self.quality_gate = QualityGate(self.config)
        # Unified quality entry (QUAL-002): same gate + analyzer instances
        self.quality_pipeline = QualityPipeline(
            self.config,
            gate=self.quality_gate,
            analyzer=self.content_analyzer,
            min_combined_score=self.min_post_quality_score,
            require_hashtags=self.require_hashtags,
        )
        self.ab_engine = ABEngine(self.memory.ab_results)
        rel_groups = self.config.get('relevance_settings', {}).get('topic_groups', {})
        self.trend_radar = TrendRadar(rel_groups)
        self.repost_policy = RepostPolicyFilter(self.config)
        self.rss_manager = RSSSourceManager(self.config, self.http_session)
        self.recent_repost_authors: List[str] = []
        # Content + engagement ports after AB flags / ledger / dry-run exist
        self.content_service = ContentService(self._build_content_ports())
        self.engagement_service = EngagementService(self._build_engagement_ports())
        # News/RSS strategy (STRAT-002); registry prefers instance (STRAT-003)
        self.quality_news_strategy = QualityNewsStrategy(
            self._build_news_strategy_ports()
        )
        # Shared image/theme helpers (STRAT-004) for upcoming strategy families
        self._image_post_ports = self._build_image_post_ports()
        self.image_post_helper = ImagePostHelper(self._image_post_ports)
        self._theme_post_ports = ThemePostPorts(
            content=CallableStructuredContent(
                self.generate_structured_post_content
            ),
            image=self._image_post_ports,
        )
        self.theme_post_helper = ThemePostHelper(self._theme_post_ports)
        # STATE-001: content dedup / publish façade
        self.content_publish_state = ContentPublishState(self.memory)
        # Soft-fail family (SOFT-002) before dynamic emergency wiring
        self._soft_fail_ports = SoftFailPorts(
            content=CallableStructuredContent(self.generate_structured_post_content),
            image=self._image_post_ports,
        )
        self.motivational_moment_strategy = MotivationalMomentStrategy(
            self._soft_fail_ports
        )
        self.emergency_unique_strategy = EmergencyUniqueStrategy(
            self._soft_fail_ports
        )
        # Theme family (STRAT-006): ai_insight + list via ThemePostHelper
        self.quality_ai_insight_strategy = QualityAiInsightStrategy(
            self.theme_post_helper
        )
        self.quality_list_strategy = QualityListStrategy(self.theme_post_helper)
        # Dynamic family (STRAT-005); registry prefers instances
        self._dynamic_posts_ports = self._build_dynamic_posts_ports()
        self.personal_opinion_strategy = PersonalOpinionStrategy(
            self._dynamic_posts_ports
        )
        self.quality_tip_strategy = QualityTipStrategy(self._dynamic_posts_ports)
        self.quality_discussion_strategy = QualityDiscussionStrategy(
            self._dynamic_posts_ports
        )
        # Insight + prediction (STRAT-008); registry prefers instances
        self.personal_insight_strategy = PersonalInsightStrategy(
            self._theme_post_ports
        )
        self.prediction_strategy = PredictionStrategy(self._theme_post_ports)
        # Poll family (STRAT-007); registry prefers instance over bound method
        self.quality_poll_strategy = QualityPollStrategy(
            self._build_poll_strategy_ports()
        )
        # Viral / trending family (STRAT-010); registry prefers instances
        self._viral_posts_ports = self._build_viral_posts_ports()
        self.viral_hot_take_strategy = ViralHotTakeStrategy(
            self._viral_posts_ports
        )
        self.trending_commentary_strategy = TrendingCommentaryStrategy(
            self._viral_posts_ports
        )
        # Hybrid registry: extracted strategies + bound methods for the rest.
        self.post_strategy_registry = self._build_post_strategy_registry()
        # Learning stack (PolicyLearner / FormatBandit / Engagement / Safety / Retro)
        if (
            not hasattr(self.memory, "engagement_actions")
            or self.memory.engagement_actions is None
        ):
            self.memory.engagement_actions = []
        self._config_path = getattr(self, "_config_path", None) or "bot_config.json"
        self.learning = LearningOrchestrator.from_config(
            self.config,
            config_path=self._config_path,
        )
        self.policy_learner = self.learning.policy_learner
        self.format_bandit = self.learning.format_bandit
        self.engagement_learner = self.learning.engagement_learner
        self.follower_tracker = self.learning.follower_tracker
        self.decision_log = self.learning.decision_log
        self.llm_retro = self.learning.llm_retro
        self.safety_governor = self.learning.safety_governor
        retro_cfg = self.config.get("llm_retro", {}) or {}
        self._llm_retro_enabled = bool(retro_cfg.get("enabled", False))
        self._llm_retro_interval_days = int(retro_cfg.get("interval_days", 7) or 7)
        # Soft-fail duplicate replacement chain (SOFT-003; needs registry)
        self.duplicate_fallback_helper = DuplicateFallbackHelper(
            self._build_duplicate_fallback_ports()
        )
        # Thin-shell: RSS / follow / relevance (REL/FOL/RSS-001)
        self.rss_content_fetcher = RssContentFetcher(self._build_rss_content_ports())
        self.follow_strategy_orchestrator = FollowStrategyOrchestrator(
            self._build_follow_ports()
        )
        # Phase 7: smart engagement orchestrator (ENG-001)
        self.smart_engagement_orchestrator = SmartEngagementOrchestrator(
            self._build_smart_engagement_ports()
        )
        self.trends_engagement_orchestrator = TrendsEngagementOrchestrator(
            self._build_trends_engagement_ports()
        )
        # Phase 7: daily report + dry-run flush (DRY-001)
        self.daily_reporting = DailyReportingFacade(
            _generate=generate_daily_report,
            _save=save_daily_report,
        )
        # Phase 7: one-tick cycle runner (CYCLE-001)
        self.bot_cycle_runner = BotCycleRunner(self._build_bot_cycle_ports())
        # Scheduled publish orchestration (slice A)
        self.publish_orchestrator = ScheduledPostPublisher(
            self._build_publish_ports()
        )
        # Thin-shell: auth / media / health
        self.auth_service = AuthService(self._build_auth_ports())
        self.media_service = MediaService(self._build_media_ports())
        self.health_service = HealthService(self._build_health_ports())
        if self.dry_run:
            logger.info("🧪 DRY-RUN режим: никакие действия не будут выполнены")

        # Система мониторинга активности (heartbeat / HB-001)
        self.heartbeat_file = "bot_heartbeat.txt"
        self.heartbeat_monitor = HeartbeatMonitor(self.heartbeat_file)
        self.last_heartbeat = datetime.now()

    def _build_news_strategy_ports(self) -> NewsStrategyPorts:
        """Composition-root wiring: bot attrs → NewsStrategyPorts (no strategy→bot)."""
        return NewsStrategyPorts(
            headlines=CallableRssHeadlines(self.fetch_external_content),
            feeds=LiveRssFeeds(lambda: list(getattr(self, "rss_feeds", []) or [])),
            duplicates=CallableDuplicateContent(self._is_duplicate_content),
            content=CallableStructuredContent(self.generate_structured_post_content),
            posts=CallablePostFactory(self.formatter.create_post),
            link_preview=CallableLinkPreview(self.create_post_with_link_preview),
            fallback=CallableFallbackPost(self._create_personal_opinion_post),
        )

    def _build_image_post_ports(self) -> ImagePostPorts:
        """Composition-root wiring: bot attrs → ImagePostPorts (STRAT-004)."""
        return ImagePostPorts(
            posts=CallablePostFactory(self.formatter.create_post),
            image_prompt=CallableImagePrompt(self.create_image_prompt_from_text),
            image_gen=CallableImageGenerator(
                self.pollinations_ai.generate_image_data
            ),
            image_upload=CallableImageUpload(self.upload_image_data_to_bluesky),
        )

    def _build_dynamic_posts_ports(self) -> DynamicPostsPorts:
        """Composition-root wiring: bot attrs → DynamicPostsPorts (STRAT-005)."""
        return DynamicPostsPorts(
            dynamic=CallableDynamicContent(
                self.dynamic_generator.generate_dynamic_content,
                self.dynamic_generator._generate_fallback_content,
            ),
            image=self._image_post_ports,
            emergency=CallableFallbackPost(self.emergency_unique_strategy.create),
        )

    def _lookup_fallback_strategy(self, name: str):
        """Registry resolve with getattr fallback (SOFT-003 / duplicate chain)."""
        try:
            return self.post_strategy_registry.resolve(name)
        except StrategyLookupError:
            fn = getattr(self, name, None)
            if fn is None or not callable(fn):
                return None
            return fn

    def _build_duplicate_fallback_ports(self) -> DuplicateFallbackPorts:
        """Composition-root wiring for DuplicateFallbackHelper (SOFT-003)."""
        return DuplicateFallbackPorts(
            lookup=CallableStrategyLookup(self._lookup_fallback_strategy),
            duplicates=CallableDuplicateContent(self._is_duplicate_content),
            emergency=CallableFallbackPost(self.emergency_unique_strategy.create),
        )

    def _build_poll_strategy_ports(self) -> PollStrategyPorts:
        """Composition-root wiring: bot attrs → PollStrategyPorts (STRAT-007)."""
        return PollStrategyPorts(
            content=CallableStructuredContent(self.generate_structured_post_content),
            poll=CallablePollFactory(self.formatter.create_poll),
        )

    def _build_viral_posts_ports(self) -> ViralPostsPorts:
        """Composition-root wiring: bot attrs → ViralPostsPorts (STRAT-010)."""
        return ViralPostsPorts(
            content=CallableStructuredContent(self.generate_structured_post_content),
            image=self._image_post_ports,
            viral_prompts=CallableViralPrompts(
                self.engagement_optimizer.generate_viral_post_prompts
            ),
            pick_trending_theme=self.trending_tracker.pick_theme_for_posts,
        )

    def _build_trends_engagement_ports(self) -> TrendsEngagementPorts:
        """Composition-root wiring for official trend-feed likes."""

        async def _fetch_feed(feed_uri: str, *, limit: int = 5) -> Any:
            client = self.bluesky_client
            try:
                return await client.app.bsky.feed.get_feed(
                    {"feed": feed_uri, "limit": limit}
                )
            except TypeError:
                return await client.app.bsky.feed.get_feed(
                    feed=feed_uri, limit=limit
                )
            except Exception:
                # Public AppView fallback (same feed URIs as sidebar «Актуальные»)
                await self._ensure_http_session()
                assert self.http_session is not None
                url = self.trending_tracker.feed_url(feed_uri, limit=limit)
                async with self.http_session.get(url) as resp:
                    resp.raise_for_status()
                    return await resp.json()

        return TrendsEngagementPorts(
            tracker=self.trending_tracker,
            feed=TrendsCallableFeedPage(_fetch_feed),
            relevance=TrendsCallableRelevance(self.calculate_relevance),
            like=self.engagement_service.like,
            get_my_did=lambda: getattr(
                getattr(self.bluesky_client, "me", None), "did", None
            ),
            sleep=asyncio.sleep,
        )

    def _sync_duplicate_caches_to_memory(self) -> None:
        """Persist duplicate-protection caches into BotMemory (CACHE-001)."""
        sync_engagement_caches_to_memory(
            self.memory,
            commented_posts=self.commented_posts,
            recent_comments=self.recent_comments,
            liked_posts=self.liked_posts,
            reposted_posts=self.reposted_posts,
            followed_users=self.followed_users,
        )

    def _rotate_rss_for_cycle(self) -> None:
        """RSS rotation + active URL refresh (CYCLE-001 adapter)."""
        self.rss_manager.rotate()
        self.rss_feeds = self.rss_manager.get_active_urls()
        logger.info(
            "📡 Active RSS: %s, probation: %s",
            len(self.rss_feeds),
            len(self.rss_manager.get_probation_urls()),
        )

    def _generate_and_save_daily_report(self) -> None:
        """Daily report + AB persist + dry-run flush (DRY-001)."""
        self.daily_reporting.generate_and_save(
            self.session_stats,
            self.memory,
            self.config,
            ab_results=self.ab_engine.results,
            dry_run=bool(self.dry_run),
            dry_run_log=self.dry_run_log,
        )

    def _build_rss_content_ports(self) -> RssContentPorts:
        """Composition-root wiring for RssContentFetcher (RSS-001)."""
        return RssContentPorts(
            http_get_text=self._http_get_text_with_retry,
            record_fetch=self.rss_manager.record_fetch,
            set_trend_headlines=lambda titles: setattr(
                self, "_trend_rss_headlines", list(titles)
            ),
            clean=self.clean_html,
        )

    def _build_follow_ports(self) -> CallableFollowPorts:
        """Composition-root wiring for FollowStrategyOrchestrator (FOL-001)."""

        async def _get_suggestions(*, limit: int = 30):
            async def _inner():
                return await self.bluesky_client.app.bsky.actor.get_suggestions(
                    params={"limit": limit}
                )

            return await self._atproto_execute(_inner)

        async def _get_profile(did: str):
            async def _inner():
                return await self.bluesky_client.app.bsky.actor.get_profile(
                    params={"actor": did}
                )

            return await self._atproto_execute(_inner)

        async def _get_timeline(*, limit: int = 30):
            return await self._atproto_execute(
                self.bluesky_client.get_timeline, limit=limit
            )

        return CallableFollowPorts(
            _get_suggestions=_get_suggestions,
            _get_profile=_get_profile,
            _get_timeline=_get_timeline,
            _follow=self.engagement_service.follow,
            _update_relationship=self.update_user_relationship,
            _get_my_did=lambda: (
                getattr(self.bluesky_client.me, "did", None)
                if hasattr(self.bluesky_client, "me") and self.bluesky_client.me
                else None
            ),
            _followed_users=self.followed_users,
        )

    def _build_smart_engagement_ports(self) -> SmartEngagementPorts:
        """Composition-root wiring for SmartEngagementOrchestrator (ENG-001)."""

        async def _fetch_timeline(*, limit: int, cursor: Optional[str] = None):
            return await self._atproto_execute(
                self.bluesky_client.get_timeline, limit=limit, cursor=cursor
            )

        eng = getattr(self, "engagement_learner", None)
        eng_enabled = bool(eng and eng.enabled)

        return SmartEngagementPorts(
            timeline=CallableTimelinePage(_fetch_timeline),
            relevance=CallableRelevance(self.calculate_relevance),
            like=self.engagement_service.like,
            repost=self.engagement_service.repost,
            repost_policy=CallableRepostPolicy(self.repost_policy.check),
            update_relationship=self.update_user_relationship,
            get_my_did=lambda: (
                getattr(self.bluesky_client.me, "did", None)
                if hasattr(self.bluesky_client, "me") and self.bluesky_client.me
                else None
            ),
            reposted_uris=self.reposted_posts,
            recent_repost_authors=self.recent_repost_authors,
            set_trend_snippets=lambda snippets: setattr(
                self, "_trend_timeline_snippets", list(snippets)
            ),
            get_session_likes=lambda: int(self.session_stats.get("likes_given", 0)),
            bump_errors=lambda: self.session_stats.__setitem__(
                "errors", self.session_stats.get("errors", 0) + 1
            ),
            infer_topic=eng.infer_topic if eng_enabled else None,
            topic_multiplier=eng.topic_multiplier if eng_enabled else None,
            on_like_action=self._on_engagement_like_action if eng_enabled else None,
        )

    def _log_bandit_pick(
        self,
        domain: str,
        action: str,
        arm: str,
        learner: Optional[PolicyLearner] = None,
        reason: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> None:
        """Write one AgentDecisionLog line from learner meta or explicit reason."""
        orch = getattr(self, "learning", None)
        if orch is None:
            return
        orch.log_pick(
            domain=domain,
            action=action,
            learner=learner,
            arm=arm,
            reason=reason,
            context=context,
        )

    def _on_engagement_like_action(
        self,
        *,
        kind: str = "like",
        topic: str = "_other",
        uri: str = "",
        ts: Optional[str] = None,
        rewarded_checks: Optional[List] = None,
        multiplier: Optional[float] = None,
        score: Optional[float] = None,
        effective_score: Optional[float] = None,
        **_kwargs,
    ) -> None:
        """Record liked URI for topic-arm credit; schedule 6h/24h checks."""
        if not uri or not getattr(self, "engagement_learner", None):
            return
        if not self.engagement_learner.enabled:
            return
        actions = self.memory.engagement_actions
        if actions is None:
            self.memory.engagement_actions = []
            actions = self.memory.engagement_actions
        action = self.engagement_learner.record_action(
            actions,
            kind=kind,
            topic=topic,
            uri=uri,
            ts=ts,
        )
        if rewarded_checks is not None and not action.get("rewarded_checks"):
            action["rewarded_checks"] = list(rewarded_checks)
        try:
            self.memory.save()
        except Exception as e:
            logger.warning("engagement_actions save failed: %s", e)
        mult = multiplier
        if mult is None:
            try:
                mult = float(self.engagement_learner.topic_multiplier(topic))
            except Exception:
                mult = 1.0
        self._log_bandit_pick(
            domain="engagement",
            action=kind or "like",
            arm=str(topic or "_other"),
            reason="topic_multiplier",
            context={
                "multiplier": float(mult),
                "score": score,
                "effective_score": effective_score,
                "uri": (uri or "")[:80],
            },
        )
        for hours in self.engagement_learner.action_credit_delays_hours(self.config):
            delay_s = int(float(hours) * 3600)
            if delay_s <= 0:
                continue
            self._spawn_background(
                self.delayed_engagement_credit_check(uri, delay_s)
            )

    def _build_auth_ports(self) -> AuthPorts:
        """Composition-root wiring: bot attrs → AuthPorts (no service→bot)."""

        async def _restore_login(session: str):
            return await self._atproto_execute(
                self.bluesky_client.login, session_string=session
            )

        async def _credential_login():
            return await self._atproto_execute(
                self.bluesky_client.login, self.handle, self.password
            )

        return AuthPorts(
            ensure_http=self._ensure_http_session,
            load_session=self.session_store.load,
            clear_session=self.session_store.clear,
            save_session=self.session_store.save,
            restore_login=_restore_login,
            credential_login=_credential_login,
            export_session_string=self.bluesky_client.export_session_string,
            set_authenticated=lambda v: setattr(self, "authenticated", bool(v)),
            get_handle=lambda: self.handle,
        )

    def _build_media_ports(self) -> MediaPorts:
        """Composition-root wiring: bot attrs → MediaPorts (no service→bot)."""
        return MediaPorts(
            ensure_http=self._ensure_http_session,
            get_http_session=lambda: self.http_session,
            media_upload_execute=self._media_upload_execute,
            upload_blob=self.bluesky_client.upload_blob,
            validate_outbound_url=validate_outbound_url,
            create_post=self.formatter.create_post,
            bump_errors=lambda: self.session_stats.__setitem__(
                "errors", self.session_stats.get("errors", 0) + 1
            ),
        )

    def _build_health_ports(self) -> HealthPorts:
        """Composition-root wiring: bot attrs → HealthPorts (no service→bot)."""

        def _memory_mb() -> float:
            try:
                import psutil

                return psutil.Process().memory_info().rss / 1024 / 1024
            except ImportError:
                logger.warning("⚠️ psutil не установлен, мониторинг памяти недоступен")
                return 0.0

        async def _reinit_http():
            await self._ensure_http_session(force_recreate=True)

        return HealthPorts(
            get_http_session=lambda: self.http_session,
            get_memory_mb=_memory_mb,
            get_successful_posts=lambda: self.memory.successful_posts,
            get_likes_given=lambda: int(self.session_stats.get("likes_given", 0)),
            cleanup_content_hashes=self._cleanup_old_content_hashes,
            cleanup_commented_posts=self._cleanup_old_commented_posts,
            reinit_http=_reinit_http,
            create_emergency_post=self._create_emergency_unique_post,
            authenticate=self.authenticate,
            save_memory=self.memory.save,
        )

    def _build_publish_ports(self) -> PublishPorts:
        """Composition-root wiring: bot attrs → PublishPorts (no orchestrator→bot)."""

        async def _resolve_strategy(name: str):
            return await self.post_strategy_registry.resolve(name)()

        async def _send_post(post):
            return await self._atproto_execute(
                self.bluesky_client.send_post,
                text=post.text,
                facets=post.facets if post.facets else None,
                embed=(
                    post.embed
                    if hasattr(post, "embed") and post.embed
                    else None
                ),
                langs=(
                    post.langs
                    if hasattr(post, "langs") and post.langs
                    else ["en"]
                ),
            )

        return PublishPorts(
            safety_status=self._safety_status,
            can_spend_post=lambda: self.activity_budget.can_spend("post"),
            spend_post=lambda: self.activity_budget.spend("post"),
            get_daily_post_count=lambda: int(self.daily_post_count),
            set_daily_post_count=lambda n: setattr(self, "daily_post_count", int(n)),
            get_max_posts_per_day=lambda: int(self.max_posts_per_day),
            get_last_post_date=lambda: self.last_post_date,
            set_last_post_date=lambda d: setattr(self, "last_post_date", d),
            get_strategy_arm_keys=lambda: [
                k
                for k in self.config.get("post_strategies", {}).keys()
                if k in self.post_strategy_registry
            ],
            get_successful_posts=lambda: self.memory.successful_posts,
            has_format_bandit=lambda: self.format_bandit is not None,
            pick_format_bandit=lambda arms, recent: self.format_bandit.pick_arm(
                list(arms), recent
            ),
            record_format_pick=lambda arm: self.format_bandit.record_pick(arm),
            get_format_bandit_learner=lambda: self.format_bandit,
            pick_ab_format=lambda: self.ab_engine.pick_format(),
            get_prompt_suffix=lambda fmt: self.ab_engine.get_prompt_suffix(fmt),
            log_pick=self._log_bandit_pick,
            set_current_ab_format=lambda fmt: setattr(
                self, "_current_ab_format", fmt
            ),
            set_current_ab_suffix=lambda s: setattr(self, "_current_ab_suffix", s),
            get_dry_run_format_label=lambda: getattr(
                self, "_last_ab_format", "unknown"
            ),
            get_trend_timeline_snippets=lambda: getattr(
                self, "_trend_timeline_snippets", []
            ),
            get_trend_rss_headlines=lambda: getattr(
                self, "_trend_rss_headlines", []
            ),
            get_topic_of_day=lambda texts: self.trend_radar.get_topic_of_day(texts),
            pick_strategy=lambda arms, recent: self.policy_learner.pick_arm(
                list(arms), recent
            ),
            record_strategy_pick=lambda key: self.policy_learner.record_pick(key),
            get_policy_learner=lambda: self.policy_learner,
            set_current_strategy_key=lambda key: setattr(
                self, "_current_strategy_key", key
            ),
            get_current_strategy_key=lambda: getattr(
                self, "_current_strategy_key", None
            ),
            resolve_strategy=_resolve_strategy,
            quality_pipeline=self.quality_pipeline,
            set_quality_gate_regen_mode=lambda on: setattr(
                self, "_quality_gate_regen_mode", bool(on)
            ),
            apply_quality_result=self._apply_quality_result_to_post,
            is_duplicate=self._is_duplicate_content,
            create_fallback=self._create_fallback_post_for_duplicate,
            evaluate_quality=self._evaluate_post_quality,
            enforce_text_limit=lambda post: self._enforce_bluesky_text_limit(
                post, max_graphemes=BLUESKY_MAX_GRAPHEMES
            ),
            dry_run=bool(self.dry_run),
            dry_run_log=lambda action, **kwargs: self.dry_run_log.log(
                action, **kwargs
            ),
            send_post=_send_post,
            mark_published=self._mark_content_as_published,
            bump_posts_created=lambda: self.session_stats.__setitem__(
                "posts_created",
                self.session_stats.get("posts_created", 0) + 1,
            ),
            generate_content_hash=self._generate_content_hash,
            append_successful_post=lambda data: self.memory.successful_posts.append(
                data
            ),
            append_viral_post=lambda data: self.memory.viral_posts.append(data),
            schedule_checks=self.content_service.schedule_post_performance_checks,
            refresh_followers_at_publish=self.refresh_followers_count,
            record_ab_impression=lambda fmt: self.ab_engine.record_impression(fmt),
            bump_errors=lambda: self.session_stats.__setitem__(
                "errors", self.session_stats.get("errors", 0) + 1
            ),
        )

    def _build_bot_cycle_ports(self) -> CallableBotCyclePorts:
        """Composition-root wiring: bot attrs → BotCyclePorts (CYCLE-001)."""
        return CallableBotCyclePorts(
            _update_heartbeat=self._update_heartbeat,
            _reset_consecutive_errors=lambda: setattr(self, "_consecutive_errors", 0),
            _engagement_mode=lambda: self.config.get("engagement_mode", "open"),
            _smart_engagement=self.smart_engagement,
            _follow_strategy=self.follow_strategy,
            _post_interval_minutes=lambda: float(self.post_interval[0]),
            _is_posting_window=self._is_posting_window,
            _create_scheduled_post=self.create_scheduled_post,
            _update_posts_with_real_metrics=self.update_posts_with_real_metrics,
            _learn_from_memory=self.learn_from_memory,
            _trim_in_memory_caches=self._trim_in_memory_caches,
            _sync_duplicate_caches_to_memory=self._sync_duplicate_caches_to_memory,
            _save_memory=self.memory.save,
            _session_stats=lambda: self.session_stats,
            _daily_post_counts=lambda: (
                int(self.daily_post_count),
                int(self.max_posts_per_day),
            ),
            _cleanup_old_content_hashes=self._cleanup_old_content_hashes,
            _cleanup_old_commented_posts=self._cleanup_old_commented_posts,
            _compact_action_ledger=self.action_ledger.compact,
            _cleanup_log_budget=lambda: _cleanup_log_budget(
                log_dir, LOG_TOTAL_BUDGET_BYTES
            ),
            _rotate_rss=self._rotate_rss_for_cycle,
            _generate_and_save_daily_report=self._generate_and_save_daily_report,
            _analyze_post_diversity=self.analyze_post_diversity,
            _health_monitor=self.health_monitor,
            _emergency_recovery=self.emergency_recovery,
            _persist_session=self._persist_session,
        )

    def _build_content_ports(self) -> ContentPorts:
        """Composition-root wiring: bot attrs → ContentPorts (no service→bot)."""
        return ContentPorts(
            prompt=LivePromptContext(
                _get_ab_suffix=lambda: getattr(self, '_current_ab_suffix', '') or '',
                _get_quality_gate_regen_mode=lambda: bool(
                    getattr(self, '_quality_gate_regen_mode', False)
                ),
            ),
            scheduler=LiveBackgroundScheduler(
                _spawn=self._spawn_background,
                _delayed_performance_check=self.delayed_performance_check,
            ),
        )

    def _build_post_strategy_registry(self) -> PostStrategyRegistry:
        """Composition-root: hybrid registry for ``post_strategies`` config keys.

        Unextracted families stay as bound methods. News/RSS is overwritten with
        :attr:`quality_news_strategy` under stable key ``STRATEGY_NAME`` so
        learning / A/B weight names remain unchanged. Runtime dispatch uses
        ``registry.weighted_named_entries`` / ``resolve`` in
        ``create_scheduled_post``.
        """
        names = list(self.config.get("post_strategies", {}).keys())
        registry, registered, missing = build_bound_registry(self, names)

        # STRAT-003: prefer extracted QualityNewsStrategy over thin bound method.
        if STRATEGY_NAME in names:
            registry.register(
                STRATEGY_NAME, self.quality_news_strategy, overwrite=True
            )
            if STRATEGY_NAME not in registered:
                registered = list(registered) + [STRATEGY_NAME]
                missing = [n for n in missing if n != STRATEGY_NAME]

        # STRAT-005..010 + SOFT-002: dynamic / theme / poll / insight / viral / soft-fail.
        extracted_overwrites = (
            (PERSONAL_OPINION_STRATEGY_NAME, self.personal_opinion_strategy),
            (QUALITY_TIP_STRATEGY_NAME, self.quality_tip_strategy),
            (QUALITY_DISCUSSION_STRATEGY_NAME, self.quality_discussion_strategy),
            (AI_INSIGHT_STRATEGY_NAME, self.quality_ai_insight_strategy),
            (LIST_STRATEGY_NAME, self.quality_list_strategy),
            (POLL_STRATEGY_NAME, self.quality_poll_strategy),
            (PERSONAL_INSIGHT_STRATEGY_NAME, self.personal_insight_strategy),
            (PREDICTION_STRATEGY_NAME, self.prediction_strategy),
            (VIRAL_HOT_TAKE_STRATEGY_NAME, self.viral_hot_take_strategy),
            (TRENDING_COMMENTARY_STRATEGY_NAME, self.trending_commentary_strategy),
            (MOTIVATIONAL_STRATEGY_NAME, self.motivational_moment_strategy),
            (EMERGENCY_STRATEGY_NAME, self.emergency_unique_strategy),
        )
        for name, strategy in extracted_overwrites:
            # Soft-fail always registered for fallback resolve even if not weighted.
            if name not in names and name not in (
                MOTIVATIONAL_STRATEGY_NAME,
                EMERGENCY_STRATEGY_NAME,
            ):
                continue
            registry.register(name, strategy, overwrite=True)
            if name not in registered:
                registered = list(registered) + [name]
                missing = [n for n in missing if n != name]

        if missing:
            logger.warning(
                "PostStrategyRegistry: missing bound methods for config keys: %s",
                ", ".join(missing),
            )
        if names and not registered:
            logger.error(
                "PostStrategyRegistry: empty — 0/%d config keys resolved to callables",
                len(names),
            )
        else:
            logger.info(
                "PostStrategyRegistry: registered %d/%d strategies from post_strategies config",
                len(registered),
                len(names),
            )
        return registry

    def _safety_status(self) -> SafetyStatus:
        """Gather budget / circuit / follower / error signals for SafetyGovernor."""
        orch = getattr(self, "learning", None)
        if orch is None:
            return SafetyStatus(ok=True)

        circuit_open: dict[str, bool] = {}
        for key, attr in (("bluesky", "_cb_bluesky"), ("ai", "_cb_ai")):
            cb = getattr(self, attr, None)
            if cb is None:
                continue
            if hasattr(cb, "is_open"):
                circuit_open[key] = bool(cb.is_open)
            else:
                circuit_open[key] = getattr(cb, "state", "") == "open"

        budget_summary = None
        budget = getattr(self, "activity_budget", None)
        if budget is not None and hasattr(budget, "summary"):
            try:
                budget_summary = budget.summary()
            except Exception:
                budget_summary = None

        followers_delta_1h = None
        tracker = getattr(self, "follower_tracker", None)
        if tracker is not None and hasattr(tracker, "delta_1h"):
            try:
                followers_delta_1h = tracker.delta_1h()
            except Exception:
                followers_delta_1h = None

        return orch.safety_status(
            budget_summary=budget_summary,
            circuit_open=circuit_open or None,
            followers_delta_1h=followers_delta_1h,
            consecutive_errors=int(getattr(self, "_consecutive_errors", 0) or 0),
        )

    def _build_engagement_ports(self) -> EngagementPorts:
        """Composition-root wiring: bot attrs → EngagementPorts (no service→bot)."""
        budget = getattr(self, 'activity_budget', None)
        return EngagementPorts(
            client=self.bluesky_client,
            ledger=self.action_ledger,
            budget=budget if budget is not None else UnlimitedBudget(),
            dry_run=DryRunGate(
                enabled=bool(getattr(self, 'dry_run', False)),
                _logger=getattr(self, 'dry_run_log', None),
            ),
            stats=self.session_stats,
            identity=LiveEngagementIdentity(
                _liked_posts=lambda: self.liked_posts,
                _reposted_posts=lambda: self.reposted_posts,
                _followed_users=lambda: self.followed_users,
                _recent_repost_authors=lambda: self.recent_repost_authors,
            ),
            config=LiveEngagementConfig(_get_config=lambda: self.config),
            retry=self.retry_atproto,
        )

    def load_external_config(self, config_file='bot_config.json'):
        """Загружает внешнюю конфигурацию, чтобы ее можно было изменять."""
        self._config_path = config_file
        try:
            with open(config_file, 'r') as f:
                logger.info(f"⚙️ Загрузка конфигурации из {config_file}")
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"❌ Файл конфигурации {config_file} не найден! Используются значения по умолчанию.")
            # Возвращаем дефолтную структуру в случае отсутствия файла
            return {
                "post_strategies": {
                    "_create_quality_news_post": 0.4,  # Увеличиваем вес RSS-новостей
                    "_create_personal_opinion_post": 0.25,
                    "_create_quality_ai_insight": 0.2,
                    "_create_quality_tip_post": 0.1,
                    "_create_quality_discussion": 0.05
                },
                "image_generation_prompts": {},
                "learning_parameters": {},
                "engagement_settings": {
                    "repost_threshold": 0.9,  # ИЗМЕНЕНО: Очень высокий порог для репостов (было 0.75) - практически отключает репосты
                    "comment_threshold": 0.65,  # ИЗМЕНЕНО: Повышен порог для комментов (было 0.5)
                    "repost_probability": 0.02,  # ИЗМЕНЕНО: Минимальная вероятность репоста (было 0.15) - 2%
                    "comment_probability": 0.2,  # ИЗМЕНЕНО: Снижена вероятность комментария (было 0.35)
                    "max_reposts_per_cycle": 0,  # ИЗМЕНЕНО: ПОЛНОСТЬЮ ОТКЛЮЧЕНЫ репосты за цикл (было 1)
                    "max_comments_per_cycle": 2  # ИЗМЕНЕНО: Максимум 2 комментария за цикл (было 4)
                }
            }
    
    def _create_http_session(self) -> None:
        """Создает HTTP сессию с надежными таймаутами (делегирует в http_session)."""
        try:
            self.http_session = create_http_session()
        except Exception:
            self.http_session = None
            raise

    async def _ensure_http_session(self, *, force_recreate: bool = False) -> aiohttp.ClientSession:
        """Гарантирует живую shared ClientSession; при recreate — close, затем create."""

        def _create() -> aiohttp.ClientSession:
            self.http_session = None
            self._create_http_session()
            return self.http_session  # type: ignore[return-value]

        self.http_session = await ensure_http_session(
            self.http_session,
            force_recreate=force_recreate,
            create=_create,
        )
        self._inject_http_session_into_adapters()
        return self.http_session

    def _inject_http_session_into_adapters(self) -> None:
        """Push live shared ClientSession into AI / RSS / formatter consumers (bot owns lifecycle)."""
        ai = getattr(self, 'pollinations_ai', None)
        if ai is not None and hasattr(ai, 'set_http_session'):
            ai.set_http_session(self.http_session)
        rss = getattr(self, 'rss_manager', None)
        if rss is not None:
            rss.http_session = self.http_session
        formatter = getattr(self, 'formatter', None)
        if formatter is not None and hasattr(formatter, 'set_http_session'):
            formatter.set_http_session(self.http_session)
        rich = getattr(self, 'rich_creator', None)
        if rich is not None and hasattr(rich, 'set_http_session'):
            rich.set_http_session(self.http_session)
        tracker = getattr(self, "trending_tracker", None)
        if tracker is not None and hasattr(tracker, "set_fetch_json"):
            tracker.set_fetch_json(self._trends_fetch_json)

    async def _trends_fetch_json(self, url: str) -> Dict[str, Any]:
        """HTTP JSON for getTrends / getFeed public AppView fallback."""
        await self._ensure_http_session()
        assert self.http_session is not None
        async with self.http_session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data if isinstance(data, dict) else {}

    async def _http_get_text_with_retry(self, url: str, timeout: float = 15) -> tuple[int, str]:
        """Shared-session HTTP GET with ``retry_rss_http`` (RETRY-002 RSS path).

        Raises after policy exhaust on 429 / 5xx / network. Non-retryable 4xx
        returns ``(status, body)`` without retrying.
        """
        async def _once() -> tuple[int, str]:
            await self._ensure_http_session()
            assert self.http_session is not None
            try:
                async with self.http_session.get(url, timeout=timeout) as response:
                    body = await response.text()
                    if response.status == 429:
                        raise RuntimeError(f"HTTP 429 rate limit fetching {url}")
                    if response.status >= 500:
                        raise RuntimeError(f"HTTP {response.status} fetching {url}")
                    return response.status, body
            except asyncio.TimeoutError as e:
                raise TimeoutError(f"HTTP GET timed out for {url}") from e

        return await self.retry_rss_http.execute(_once)

    async def _atproto_execute(self, fn, *args, **kwargs):
        """ATProto read/write via ``retry_atproto`` (RETRY-003). Bounded; CLIENT no-retry."""
        return await self.retry_atproto.execute(fn, *args, **kwargs)

    async def _media_upload_execute(self, fn, *args, **kwargs):
        """Image download / ``upload_blob`` via ``retry_media_upload`` (RETRY-003)."""
        return await self.retry_media_upload.execute(fn, *args, **kwargs)

    def _is_posting_window(self) -> bool:
        """Check scheduling config (quiet_hours / active_windows).

        Returns True if no scheduling constraints are configured (backward compat).
        """
        sched = self.config.get('scheduling', {})
        tz_name = sched.get('timezone', 'UTC')
        quiet_hours = sched.get('quiet_hours', [])
        active_windows = sched.get('active_windows', [])

        # If nothing is configured, always allow
        if not quiet_hours and not active_windows:
            return True

        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            tz = None

        now = datetime.now(tz)
        current_hour = now.hour

        # quiet_hours: list of hours where posting is suppressed
        if quiet_hours and current_hour in quiet_hours:
            return False

        # active_windows: list of [start_hour, end_hour] ranges
        if active_windows:
            for window in active_windows:
                if not isinstance(window, (list, tuple)) or len(window) < 2:
                    continue
                start, end = int(window[0]), int(window[1])
                if start <= end:
                    if start <= current_hour < end:
                        return True
                else:
                    if current_hour >= start or current_hour < end:
                        return True
            return False

        return True

    def _update_heartbeat(self) -> None:
        """Обновляет файл heartbeat (HB-001 → HeartbeatMonitor)."""
        self.last_heartbeat = self.heartbeat_monitor.update()

    def _check_for_hanging(self) -> bool:
        """Проверяет зависание по heartbeat (HB-001 → HeartbeatMonitor)."""
        return self.heartbeat_monitor.is_stale()

    # Копируем все базовые методы из оригинального бота
    def clean_html(self, raw_html: str) -> str:
        """Удаляет HTML-теги (RSS-001 shared helper)."""
        return rss_clean_html(raw_html)
    
    def _generate_content_hash(self, text: str, url: str = None, image_url: str = None) -> str:
        """Генерирует хеш контента (STATE-001 → ContentPublishState)."""
        return self.content_publish_state.generate_content_hash(text, url, image_url)

    def _is_duplicate_content(self, text: str, url: str = None, image_url: str = None) -> bool:
        """Проверяет дубликат (STATE-001 → ContentPublishState)."""
        return self.content_publish_state.is_duplicate(text, url, image_url)

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Jaccard similarity (STATE-001 → ContentPublishState)."""
        return self.content_publish_state.calculate_text_similarity(text1, text2)

    def _mark_content_as_published(self, text: str, url: str = None, image_url: str = None) -> None:
        """Отмечает контент опубликованным (STATE-001 → ContentPublishState)."""
        self.content_publish_state.mark_published(text, url, image_url)

    def _cleanup_old_content_hashes(self) -> None:
        """Очищает хеши + retention списков (STATE-001 → ContentPublishState)."""
        self.content_publish_state.cleanup_old_hashes()

    def _cleanup_old_commented_posts(self) -> None:
        """Очищает старые записи о всех взаимодействиях (старше 7 дней)"""
        # Очищаем каждые 7 дней для предотвращения бесконечного роста
        old_commented_count = len(self.commented_posts)
        old_recent_count = len(self.recent_comments)
        old_liked_count = len(self.liked_posts)
        old_reposted_count = len(self.reposted_posts)
        old_followed_count = len(self.followed_users)
        
        # Очищаем полностью, так как посты старше недели уже не актуальны для проверки дубликатов
        self.commented_posts.clear()
        self.recent_comments = self.recent_comments[-10:]  # Оставляем только последние 10
        self.liked_posts.clear()
        self.reposted_posts.clear()
        
        # УЛУЧШЕНИЕ: Подписки ограничиваем до 1000 записей для предотвращения утечки памяти
        if len(self.followed_users) > 1000:
            # Преобразуем в список, оставляем последние 800 записей
            followed_list = list(self.followed_users)
            self.followed_users = set(followed_list[-800:])
            logger.info(f"🧹 Очищены старые подписки: {old_followed_count} -> {len(self.followed_users)}")
        
        logger.info(f"🧹 Очищены записи о взаимодействиях:")
        logger.info(f"   📝 Прокомментированные посты: {old_commented_count} -> {len(self.commented_posts)}")
        logger.info(f"   💬 Недавние комментарии: {old_recent_count} -> {len(self.recent_comments)}")
        logger.info(f"   ❤️ Лайкнутые посты: {old_liked_count} -> {len(self.liked_posts)}")
        logger.info(f"   🔄 Репостнутые посты: {old_reposted_count} -> {len(self.reposted_posts)}")
        logger.info(f"   👥 Подписки сохранены: {old_followed_count} записей")

    # Soft caps between weekly clearance (MED-001 cache bound).
    _CACHE_SET_MAX = 5000
    _CACHE_DICT_MAX = 500
    _CONTENT_CACHE_MAX = 200

    def _trim_set(self, values: set, limit: int) -> set:
        if len(values) <= limit:
            return values
        # Sets are unordered; keep an arbitrary tail after list conversion.
        return set(list(values)[-limit:])

    def _trim_dict(self, mapping: dict, limit: int) -> dict:
        if len(mapping) <= limit:
            return mapping
        keys = list(mapping.keys())[-limit:]
        return {k: mapping[k] for k in keys}

    def _trim_in_memory_caches(self) -> None:
        """Bound in-memory caches to prevent unbounded growth (MED-001)."""
        self.commented_posts = self._trim_set(self.commented_posts, self._CACHE_SET_MAX)
        self.liked_posts = self._trim_set(self.liked_posts, self._CACHE_SET_MAX)
        self.reposted_posts = self._trim_set(self.reposted_posts, self._CACHE_SET_MAX)
        self.followed_users = self._trim_set(self.followed_users, self._CACHE_SET_MAX)
        if len(self.recent_comments) > 50:
            self.recent_comments = self.recent_comments[-50:]
        if isinstance(self.hashtag_cache, dict):
            self.hashtag_cache = self._trim_dict(self.hashtag_cache, self._CACHE_DICT_MAX)
        if isinstance(self.user_cache, dict):
            self.user_cache = self._trim_dict(self.user_cache, self._CACHE_DICT_MAX)
        if isinstance(self.content_cache, list) and len(self.content_cache) > self._CONTENT_CACHE_MAX:
            self.content_cache = self.content_cache[-self._CONTENT_CACHE_MAX:]
        if len(getattr(self, '_trend_timeline_snippets', [])) > 100:
            self._trend_timeline_snippets = self._trend_timeline_snippets[-100:]
        if len(getattr(self, '_trend_rss_headlines', [])) > 50:
            self._trend_rss_headlines = self._trend_rss_headlines[-50:]

    def get_status(self) -> Dict:
        """Lightweight local health/status snapshot (no network I/O)."""
        http_ok = bool(
            self.http_session is not None and not getattr(self.http_session, 'closed', True)
        )
        return {
            'overall': 'ok',
            'daily_posts': getattr(self, 'daily_post_count', 0),
            'max_posts_per_day': getattr(self, 'max_posts_per_day', 0),
            'liked_cache': len(getattr(self, 'liked_posts', ())),
            'commented_cache': len(getattr(self, 'commented_posts', ())),
            'content_cache': len(getattr(self, 'content_cache', [])),
            'hashtag_cache': len(getattr(self, 'hashtag_cache', {})),
            'user_cache': len(getattr(self, 'user_cache', {})),
            'http_session_open': http_ok,
            'rss_feeds': len(getattr(self, 'rss_feeds', [])),
        }
    
    async def _create_fallback_post_for_duplicate(self) -> Optional[RichTextPost]:
        """Fallback when primary post is duplicate (SOFT-003)."""
        return await self.duplicate_fallback_helper.create()

    async def _create_motivational_moment_post(self) -> RichTextPost:
        """Motivational soft-fail (delegates to MotivationalMomentStrategy / SOFT-002)."""
        return await self.motivational_moment_strategy.create()

    async def _create_emergency_unique_post(self) -> RichTextPost:
        """Emergency unique soft-fail (delegates to EmergencyUniqueStrategy / SOFT-002)."""
        return await self.emergency_unique_strategy.create()

    async def authenticate(self, force_login: bool = False) -> bool:
        """Thin delegate → :class:`AuthService`."""
        return await self.auth_service.authenticate(force_login=force_login)

    def _persist_session(self) -> None:
        """Thin delegate → :meth:`AuthService.persist_session`."""
        self.auth_service.persist_session()

    # НОВЫЕ МЕТОДЫ ДЛЯ КРАСИВЫХ ПОСТОВ
    
    async def create_scheduled_post(self) -> None:
        """Thin delegate → :class:`ScheduledPostPublisher` (publish extract slice A)."""
        await self.publish_orchestrator.run()

    def _spawn_background(self, coro) -> None:
        """Register a background task; auto-discard on completion."""
        if len(self._background_tasks) >= 50:
            logger.warning("Background task limit (50) reached — skipping new task")
            return
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _weighted_choice(self, strategies: List[Tuple]):
        """Взвешенный выбор стратегии создания поста.

        Accepts ``(fn, weight)`` pairs (legacy) or ``(name, fn, weight)``
        triples. Named triples return ``(name, fn)`` so callers can persist
        the config key as ``strategy_key``.
        """
        if not strategies:
            raise ValueError("strategies must be non-empty")
        sample = strategies[0]
        if len(sample) >= 3:
            named = [(name, fn) for name, fn, _weight in strategies]
            weights = [weight for _name, _fn, weight in strategies]
            return random.choices(named, weights=weights)[0]
        functions, weights = zip(*strategies)
        return random.choices(functions, weights=weights)[0]
    
    @staticmethod
    def _split_graphemes(text: str) -> List[str]:
        """Группирует текст в приближённые grapheme clusters (делегирует в content_service)."""
        return split_graphemes(text)

    def _enforce_bluesky_text_limit(
        self, post: RichTextPost, max_graphemes: int = BLUESKY_MAX_GRAPHEMES
    ) -> RichTextPost:
        """Validate/sanitize outbound text and rebuild facets if changed.

        Raises OutboundContentError when text is empty after sanitize.
        Over-long text is safely truncated to max_graphemes.
        """
        old_text = post.text or ''
        old_len = len(split_graphemes(old_text))
        new_text = validate_outbound_text(old_text, max_graphemes=max_graphemes)
        if new_text == old_text:
            return post

        new_len = len(split_graphemes(new_text))
        if new_len < old_len:
            logger.warning(
                f"✂️ Текст обрезан до лимита Bluesky: {old_len} → {new_len} graphemes"
            )
        elif new_text != old_text:
            logger.info("🧹 Исходящий текст очищен от управляющих символов")

        post.text = new_text
        try:
            post.facets = self.formatter._extract_facets_sync(new_text)
        except Exception as e:
            logger.warning(f"Не удалось пересобрать facets после валидации: {e}")
            post.facets = []
        return post

    def _apply_quality_result_to_post(
        self, post: RichTextPost, result: QualityResult
    ) -> None:
        """Attach pipeline score fields onto the post object for memory / logging."""
        if not post:
            return
        post.quality_score = result.combined_score
        post.viral_score = result.viral_score
        post.viral_factors = list(result.factors or [])

    def _evaluate_post_quality(self, post: RichTextPost) -> bool:
        """Score-stage quality via QualityPipeline (gate skipped — fallback parity)."""
        if not post or not post.text:
            return False

        result = self.quality_pipeline.evaluate(
            post.text,
            QualityContext(run_gate=False),
        )
        self._apply_quality_result_to_post(post, result)

        details = result.details or {}
        min_viral = details.get(
            'min_viral_score', self.quality_pipeline.default_min_viral_score
        )
        min_combined = details.get(
            'min_combined_score', self.min_post_quality_score
        )
        required_triggers = details.get(
            'required_engagement_triggers',
            self.quality_pipeline.default_required_triggers,
        )

        logger.info("📊 Финальная оценка перед публикацией (вирусность + пороги):")
        logger.info(f"   🎯 Вирусный потенциал: {result.viral_score:.2f}/1.0")
        logger.info(f"   📈 Базовая оценка: {result.basic_score:.2f}/1.0")
        logger.info(f"   🔥 Итоговая оценка: {result.combined_score:.2f}/1.0")
        logger.info(
            f"   ✅ Факторы вирусности: "
            f"{', '.join(result.factors) if result.factors else 'Нет'}"
        )
        if result.recommendations:
            logger.info("   💡 Рекомендации:")
            for rec in result.recommendations[:3]:
                logger.info(f"     • {rec}")

        meets_viral = details.get(
            'meets_viral_threshold', result.viral_score >= min_viral
        )
        meets_combined = details.get(
            'meets_basic_threshold', result.combined_score >= min_combined
        )
        meets_triggers = details.get(
            'has_enough_triggers', len(result.factors) >= required_triggers
        )
        logger.info("   🎪 Проверки:")
        logger.info(
            f"     Вирусный порог ({min_viral}): {'✅' if meets_viral else '❌'}"
        )
        logger.info(
            f"     Базовый порог ({min_combined}): {'✅' if meets_combined else '❌'}"
        )
        logger.info(
            f"     Триггеры engagement ({required_triggers}): "
            f"{'✅' if meets_triggers else '❌'}"
        )

        if result.reason == 'missing_hashtags':
            logger.warning("⚠️ Пост не содержит обязательных хештегов")
            return False

        if not result.ok:
            logger.warning(
                f"⚠️ Финальная оценка: пороги не выполнены (viral: {result.viral_score:.2f}, "
                f"combined: {result.combined_score:.2f}, triggers: {len(result.factors)}, "
                f"reason={result.reason})"
            )
        return result.ok
    
    async def _create_quality_news_post(self) -> Optional[RichTextPost]:
        """Создает качественный новостной пост (делегирует в QualityNewsStrategy).

        Registry (STRAT-003) prefers ``self.quality_news_strategy`` under
        ``STRATEGY_NAME``; this method remains for direct / getattr callers.
        """
        return await self.quality_news_strategy.create()

    async def _create_personal_opinion_post(self) -> RichTextPost:
        """Личное мнение (делегирует в PersonalOpinionStrategy / STRAT-005)."""
        return await self.personal_opinion_strategy.create()
    
    async def _quality_theme_post(
        self,
        themes: List[str],
        *,
        build_prompt: Callable[[str], str],
        content_type: str,
        model_key: str,
        build_fallback: Callable[[str], Dict[str, str]],
        image_topic: Optional[Callable[[str], str]] = None,
    ) -> RichTextPost:
        """Shared theme strategy (delegates to ThemePostHelper / STRAT-004)."""
        return await self.theme_post_helper.create(
            themes,
            build_prompt=build_prompt,
            content_type=content_type,
            model_key=model_key,
            build_fallback=build_fallback,
            image_topic=image_topic,
        )

    async def _create_quality_ai_insight(self) -> RichTextPost:
        """Создает пост об AI (делегирует в QualityAiInsightStrategy / STRAT-006).

        Registry prefers ``self.quality_ai_insight_strategy`` under
        ``AI_INSIGHT_STRATEGY_NAME``; this method remains for direct callers.
        """
        return await self.quality_ai_insight_strategy.create()
    
    async def _create_quality_tip_post(self) -> RichTextPost:
        """Совет (делегирует в QualityTipStrategy / STRAT-005)."""
        return await self.quality_tip_strategy.create()
    
    async def _create_quality_list_post(self) -> RichTextPost:
        """Создает пост-список (делегирует в QualityListStrategy / STRAT-006).

        Registry prefers ``self.quality_list_strategy`` under
        ``LIST_STRATEGY_NAME``; this method remains for direct callers.
        """
        return await self.quality_list_strategy.create()
    
    async def _create_quality_poll_post(self) -> RichTextPost:
        """Создает пост-опрос (делегирует в QualityPollStrategy).

        Registry (STRAT-007) prefers ``self.quality_poll_strategy`` under
        ``POLL_STRATEGY_NAME``; this method remains for direct / getattr callers.
        """
        return await self.quality_poll_strategy.create()
    
    async def _create_quality_discussion(self) -> RichTextPost:
        """Дискуссия (делегирует в QualityDiscussionStrategy / STRAT-005)."""
        return await self.quality_discussion_strategy.create()
    
    # НОВЫЕ МЕТОДЫ ДЛЯ ВИРУСНОГО КОНТЕНТА
    
    async def _create_viral_hot_take(self) -> RichTextPost:
        """Viral hot take (delegates to ViralHotTakeStrategy / STRAT-010)."""
        return await self.viral_hot_take_strategy.create()

    async def _create_trending_commentary(self) -> RichTextPost:
        """Trending commentary (delegates to TrendingCommentaryStrategy / STRAT-010)."""
        return await self.trending_commentary_strategy.create()
    
    async def _create_personal_insight(self) -> RichTextPost:
        """Personal insight post (delegates to PersonalInsightStrategy / STRAT-008)."""
        return await self.personal_insight_strategy.create()

    async def _create_prediction_post(self) -> RichTextPost:
        """Bold prediction post (delegates to PredictionStrategy / STRAT-008)."""
        return await self.prediction_strategy.create()
    
    async def create_manual_thread(self, topic: str) -> None:
        """Создание thread только по специальному запросу (НЕ автоматически)"""
        logger.info(f"📝 РУЧНОЕ создание thread на тему: {topic}")
        
        prompt = f"""
        Create a detailed analysis on "{topic}" for a social media thread.

        Structure:
        - Intro hook (50-80 characters)
        - 3-4 key points (100-150 characters each)
        - Closing question for the audience (80-120 characters)

        Requirements:
        - Each part should work as a standalone post
        - Use emojis for structure
        - Add relevant hashtags
        - Write entirely in English
        - Total length: 600-800 characters
        """
        
        long_content = await self.pollinations_ai.generate_content(prompt, model_key='powerful')
        
        if long_content:
            # Разбиваем на части и форматируем как thread
            parts = self.formatter.split_long_text(long_content, max_bytes=250)
            thread_posts = self.formatter.format_thread(parts)
            
            logger.info(f"📋 Готов thread из {len(thread_posts)} частей. Требуется подтверждение для публикации.")
            return thread_posts
        
        return None
    
    async def generate_smart_comment(self, post_text: str) -> str:
        """Генерация умного комментария с помощью Pollinations.AI"""
        
        # Сначала пробуем Pollinations.AI
        try:
            comment = await self.pollinations_ai.generate_comment(
                post_text=post_text,
                comment_style=random.choice(['supportive', 'question', 'addition'])
            )
            
            if comment and not comment.startswith("❌"):
                logger.debug(f"✅ Комментарий от Pollinations.AI: {comment}")
                return comment
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка генерации комментария Pollinations: {e}")
        
        # Fallback на OpenAI
        if self.ai_client:
            try:
                response = await self.ai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a friendly social media user. Write short positive comments in English with emojis. Max 80 characters."},
                        {"role": "user", "content": f"Comment on this post: {post_text[:200]}"}
                    ],
                    max_tokens=50,
                    temperature=0.8
                )
                comment = response.choices[0].message.content.strip()
                logger.debug(f"✅ Комментарий от OpenAI: {comment}")
                return comment
                
            except Exception as e:
                logger.warning(f"⚠️ OpenAI комментарий недоступен: {e}")
        
        # Локальный fallback
        return self._generate_fallback_comment(post_text)
    
    def _generate_fallback_comment(self, post_text: str) -> str:
        """УЛУЧШЕННАЯ локальная генерация разнообразных комментариев"""
        current_time = datetime.now().strftime("%H:%M")
        current_minute = datetime.now().minute
        
        # РАСШИРЕННЫЙ набор шаблонов комментариев
        supportive_variants = [
            f"Totally agree! 🎯 ({current_time})",
            f"Great point! ✨ ({current_time})", 
            f"Love this perspective! 💫 ({current_time})",
            f"Spot on! 🎪 ({current_time})",
            f"Couldn't agree more! 🌟 ({current_time})",
            f"This resonates! 🔮 ({current_time})",
            f"Absolutely! 🚀 ({current_time})",
            f"Well said! 📝 ({current_time})"
        ]
        
        question_variants = [
            f"What's your take on this? 🤔 ({current_time})",
            f"How do you see it? 👀 ({current_time})",
            f"Interesting angle! More thoughts? 💭 ({current_time})",
            f"Got any examples? 📚 ({current_time})",
            f"What's been your experience? 🎭 ({current_time})",
            f"Any tips on this? 💡 ({current_time})"
        ]
        
        observational_variants = [
            f"Makes sense in today's context 🌍 ({current_time})",
            f"Timing couldn't be better ⏰ ({current_time})",
            f"This hits different 🎨 ({current_time})",
            f"Food for thought 🧠 ({current_time})",
            f"Worth bookmarking 📌 ({current_time})",
            f"Game changer vibes 🎮 ({current_time})"
        ]
        
        # Выбор варианта на основе содержания и времени
        post_lower = post_text.lower()
        
        # Ротация по минутам для дополнительного разнообразия  
        minute_mod = current_minute % 3
        
        if '?' in post_text or any(word in post_lower for word in ['how', 'what', 'why', 'when', 'where']):
            variants = question_variants
        elif minute_mod == 0:
            variants = supportive_variants
        elif minute_mod == 1:
            variants = observational_variants
        else:
            variants = question_variants
        
        selected = random.choice(variants)
        
        logger.info(f"💬 Fallback комментарий (тип: {minute_mod}, время: {current_time})")
        return selected
    
    def _is_comment_unique(self, comment: str) -> bool:
        """Проверяет уникальность комментария среди недавних"""
        if not comment:
            return False
        
        # Очищаем комментарий от временных меток для сравнения
        clean_comment = re.sub(r'\(\d{2}:\d{2}\)', '', comment).strip().lower()
        
        # Проверяем схожесть с недавними комментариями
        for recent in self.recent_comments:
            clean_recent = re.sub(r'\(\d{2}:\d{2}\)', '', recent).strip().lower()
            
            # Простая проверка схожести по словам
            comment_words = set(clean_comment.split())
            recent_words = set(clean_recent.split())
            
            if comment_words and recent_words:
                # Коэффициент Жаккара
                intersection = len(comment_words.intersection(recent_words))
                union = len(comment_words.union(recent_words))
                similarity = intersection / union if union > 0 else 0
                
                if similarity > 0.6:  # 60% схожести считается дубликатом
                    logger.info(f"🔄 Обнаружен похожий комментарий (схожесть: {similarity:.2f})")
                    return False
        
        return True
    
    def _track_recent_comment(self, comment: str) -> None:
        """Отслеживает недавние комментарии для проверки уникальности"""
        self.recent_comments.append(comment)
        
        # Храним только последние 20 комментариев
        if len(self.recent_comments) > 20:
            self.recent_comments = self.recent_comments[-20:]
        
        logger.debug(f"📝 Отслеживается {len(self.recent_comments)} недавних комментариев")
    
    # Копируем остальные методы из оригинального бота
    async def fetch_external_content(self) -> List[Dict]:
        """RSS headlines (RSS-001 → RssContentFetcher)."""
        return await self.rss_content_fetcher.fetch(list(self.rss_feeds))

    def _enhanced_image_extraction(self, entry) -> Optional[str]:
        """Image URL from RSS entry (RSS-001)."""
        from rss_content import enhanced_image_extraction
        return enhanced_image_extraction(entry)

    def _calculate_entry_priority(self, entry_data: Dict, source_url: str) -> float:
        """RSS entry priority (RSS-001)."""
        from rss_content import calculate_entry_priority
        return calculate_entry_priority(entry_data, source_url)

    def _deduplicate_rss_entries(self, entries: List[Dict]) -> List[Dict]:
        """RSS dedupe (RSS-001)."""
        from rss_content import deduplicate_rss_entries
        return deduplicate_rss_entries(entries)

    def _generate_fallback_content(self, prompt: str) -> str:
        """Генерирует резервный контент, если AI недоступен"""
        fallback_templates = {
            'morning': [
                "☀️ Good morning, BlueSky! New day — new opportunities! How are you planning to spend it? 🌅\n\n#goodmorning #motivation #positive",
                "🌄 Morning starts with positive thoughts ☕ What inspires you today?\n\n#morning #inspiration #thoughts",
                "☕ Have a great day everyone! What goals are you setting for today? 🎯\n\n#goals #plans #productivity"
            ],
            'motivation': [
                "💪 Every day is a chance to become better than yesterday! What are you doing for development?\n\n#motivation #selfdevelopment #growth",
                "🎯 Small steps lead to big goals ⭐ What's your next step?\n\n#goals #success #movement",
                "⭐ Believe in yourself and everything will definitely work out! Share your victories! 💫\n\n#faith #success #achievements"
            ],
            'technology': [
                "🤖 The world of technology is developing at an incredible pace! What impresses you the most?\n\n#technology #innovation #future",
                "💻 Programming is the art of creating the future 🎨 Learning something new?\n\n#programming #coding #learning",
                "🔬 Innovations change our world every day. What technologies seem most promising to you?\n\n#innovation #science #technology"
            ],
            'general': [
                "🤔 Interesting to know your opinion about this 💭 What do you think?\n\n#opinion #discussion #thoughts",
                "📚 There's always something to learn in this world 🌍 What have you learned recently?\n\n#learning #knowledge #development",
                "🌟 Share your thoughts in the comments! Discussions are always interesting 💬\n\n#communication #thoughts #discussions",
                "🔍 Curious how you feel about this? Your point of view is important! 🎭\n\n#opinion #views #discussion",
                "💡 Every idea can change the world ✨ What interesting ideas do you have?\n\n#ideas #creativity #innovation"
            ]
        }
        
        # Простая категоризация по ключевым словам в промпте
        prompt_lower = prompt.lower()
        if any(word in prompt_lower for word in ['morning', 'day', 'good']):
            category = 'morning'
        elif any(word in prompt_lower for word in ['motiv', 'goal', 'success', 'development']):
            category = 'motivation'
        elif any(word in prompt_lower for word in ['tech', 'code', 'program', 'ai', 'computer']):
            category = 'technology'
        else:
            category = 'general'
        
        selected_template = random.choice(fallback_templates[category])
        logger.info(f"🎲 Локальная генерация: категория '{category}'")
        return selected_template
    
    async def smart_engagement(self) -> None:
        """Умное взаимодействие (ENG-001 + trends feed likes)."""
        _sg = self._safety_status()
        if not _sg.can_engagement:
            logger.info(
                "🛡️ SafetyGovernor: engagement blocked — %s",
                ", ".join(_sg.reasons) or "unknown",
            )
            return
        cfg = SmartEngagementConfig.from_bot_config(
            self.config,
            max_interactions=self.max_interactions_per_cycle,
            compliant_no_comments=bool(BLUESKY_COMPLIANT_MODE and NO_AUTO_COMMENTS),
        )
        await self.smart_engagement_orchestrator.run(cfg)
        # Official «Актуальные» feeds — separate budget slice, does not filter RSS
        trends_cfg = getattr(self, "trending_tracker", None)
        if trends_cfg is not None:
            trends_cfg.configure(self.config.get("trends", {}))
        t_eng = TrendsEngagementConfig.from_bot_config(
            self.config,
            max_likes=max(1, min(3, int(self.max_interactions_per_cycle))),
        )
        orch = getattr(self, "trends_engagement_orchestrator", None)
        if orch is not None:
            await orch.run(t_eng)

    def calculate_relevance(self, text: str, post) -> float:
        """Компонентный score (REL-001 → relevance_scoring)."""
        return score_post_relevance(
            text,
            post,
            self.config.get("relevance_settings", {}),
        )

    async def reply_to_post(self, post, comment_text: str) -> None:
        """Ответ на пост с правильным форматированием и поддержкой упоминаний"""
        try:
            # Используем асинхронный форматировщик для поддержки упоминаний
            formatted_comment = await self.formatter.create_post_async(comment_text, auto_format=True)
            # Outbound validation at comment publish boundary
            formatted_comment = self._enforce_bluesky_text_limit(
                formatted_comment, max_graphemes=BLUESKY_MAX_GRAPHEMES
            )

            author_handle = getattr(post.post.author, 'handle', 'unknown') if hasattr(post.post, 'author') and post.post.author else 'unknown'
            logger.info(f"💬 Комментирование поста от {author_handle}")
            logger.info(f"    Комментарий: {formatted_comment.text}")
            
            await self._atproto_execute(
                self.bluesky_client.send_post,
                text=formatted_comment.text,
                facets=formatted_comment.facets,
                reply_to=models.AppBskyFeedPost.ReplyRef(
                    root=models.ComAtprotoRepoStrongRef.Main(
                        uri=post.post.uri,
                        cid=post.post.cid
                    ),
                    parent=models.ComAtprotoRepoStrongRef.Main(
                        uri=post.post.uri,
                        cid=post.post.cid
                    )
                ),
            )
            
            self.session_stats['comments_made'] += 1
            logger.info(f"✅ Комментарий опубликован!")
            # Comments stay out of successful_posts (noise for PolicyLearner credit)

        except OutboundContentError as e:
            logger.warning(f"⚠️ Комментарий отклонён на границе публикации: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка при комментировании: {e}")
    
    async def run_bot_cycle(self) -> None:
        """Основной цикл работы бота с улучшенной безопасностью"""
        if not await self.authenticate():
            return

        # Restart catch-up: credit missed 6h/24h checks (async metrics need auth)
        try:
            await self.catch_up_pending_credits()
        except Exception as e:
            logger.error(f"Ошибка startup catch-up credits: {e}")

        # PLRN-021: weekly LLM retro over learning_parameters (allowlisted)
        try:
            await self.maybe_run_llm_retro()
        except Exception as e:
            logger.error(f"Ошибка llm_retro: {e}")

        cycle_count = 0
        last_post_time = datetime.now() - timedelta(hours=2)  # Начинаем с большой паузы
        
        logger.info("🤖 Бот v2.1 запущен с контролем качества и безопасности!")
        
        while True:
            try:
                cycle_start = time.time()
                # CYCLE-001: one-tick orchestration (auth/sleep stay here)
                tick_result: TickResult = await self.bot_cycle_runner.tick(
                    cycle_count, last_post_time
                )
                last_post_time = tick_result.last_post_time
                if tick_result.stop:
                    break

                # Log activity budget status
                budget_info = self.activity_budget.summary()
                logger.info(f"💰 Budget: hourly {budget_info['hourly']}, daily {budget_info['daily']}")

                # Логируем статистику Pollinations.AI
                ai_stats = self.pollinations_ai.get_statistics()
                if ai_stats['requests_made'] > 0:
                    success_rate = (ai_stats['successful_requests'] / ai_stats['requests_made']) * 100
                    logger.info(f"🤖 Статистика AI:")
                    logger.info(f"   📈 Запросы: {ai_stats['successful_requests']}/{ai_stats['requests_made']} ({success_rate:.1f}%)")
                    logger.info(f"   🔧 Модели: {list(ai_stats['models_used'].keys())}")
                
                cycle_count += 1
                
                # Адаптивная пауза между циклами (оптимизировано для 100 постов/день)
                cycle_duration = time.time() - cycle_start
                base_sleep = random.uniform(3600, 5400)  # ИЗМЕНЕНО: 60-90 минут базовая пауза (было 14-16 минут)
                
                if cycle_duration < base_sleep:
                    sleep_time = base_sleep - cycle_duration
                    logger.info(f"⏸️ Пауза {sleep_time/60:.1f} минут до следующего цикла")
                    await asyncio.sleep(sleep_time)
                
                # Вычисляем время до следующего цикла
                next_run_minutes = random.uniform(60, 90)  # ИЗМЕНЕНО: Соответствует новому post_interval
                logger.info(f"⏸️ Пауза {next_run_minutes:.1f} минут до следующего цикла")
                
            except Exception as e:
                self.session_stats['errors'] += 1
                self._consecutive_errors = getattr(self, '_consecutive_errors', 0) + 1
                ec = classify_error(e)
                self._cb_bluesky.record_failure()

                if self._consecutive_errors >= 5:
                    logger.error(f"🔴 Circuit breaker (main loop): {self._consecutive_errors} ошибок подряд ({ec.value}). Завершение.")
                    break

                delay = backoff_seconds(ec, self._consecutive_errors)
                logger.warning(f"⚠️ {ec.value} error #{self._consecutive_errors}: {e}. Backoff {delay:.0f}s")
                await asyncio.sleep(delay)

                force = ec == ErrorClass.AUTH
                if not await self.authenticate(force_login=force):
                    logger.error("❌ Не удалось переподключиться. Завершение работы.")
                    break
        
    async def shutdown(self) -> None:
        """Корректное завершение работы бота"""
        logger.info("🛑 Завершение работы бота...")

        # Cancel all background tasks gracefully
        if self._background_tasks:
            logger.info(f"⏳ Отмена {len(self._background_tasks)} фоновых задач...")
            for task in list(self._background_tasks):
                task.cancel()
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
            logger.info("✅ Все фоновые задачи остановлены")

        try:
            sync_engagement_caches_to_memory(
                self.memory,
                commented_posts=getattr(self, "commented_posts", None),
                recent_comments=getattr(self, "recent_comments", None),
                liked_posts=getattr(self, "liked_posts", None),
                reposted_posts=getattr(self, "reposted_posts", None),
                followed_users=getattr(self, "followed_users", None),
                skip_missing=True,
            )
            self.memory.save()
            logger.info("💾 Финальное сохранение памяти (JSON, атомарная запись)")

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения памяти при завершении: {e}")
        
        # Detach AI adapter from shared session (does not close bot-owned session)
        try:
            if hasattr(self, 'pollinations_ai') and self.pollinations_ai:
                await self.pollinations_ai.close_session()
                logger.info("🔒 AI adapter detached from shared HTTP session")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка detach AI HTTP session: {e}")
        
        # Закрываем основную HTTP сессию (sole owner)
        if hasattr(self, 'http_session'):
            await close_http_session(self.http_session)
            self.http_session = None
        
        # Закрываем соединения (AsyncClient не имеет метода close)
        if self.bluesky_client:
            # Просто обнуляем клиент
            self.bluesky_client = None
        
        logger.info(f"📊 Финальная статистика: {self.session_stats}")
        logger.info("👋 Бот v2.1 завершил работу")

    # ДОБАВЛЯЕМ НЕДОСТАЮЩИЕ МЕТОДЫ ДЛЯ ПОЛНОЙ АВТОНОМНОСТИ
    
    async def analyze_post_performance(self, post_uri: str) -> Dict:
        """УЛУЧШЕННЫЙ анализ эффективности поста с детальным логированием"""
        try:
            # Получаем информацию о посте (RETRY-003)
            post_info = await self._atproto_execute(
                self.bluesky_client.get_post_thread, uri=post_uri
            )
            
            engagement = {
                'likes': post_info.thread.post.like_count or 0,
                'reposts': post_info.thread.post.repost_count or 0,
                'replies': post_info.thread.post.reply_count or 0,
                'engagement_rate': 0
            }
            
            total_engagement = sum([engagement['likes'], engagement['reposts'], engagement['replies']])
            engagement['engagement_rate'] = total_engagement
            
            logger.info(f"📊 Метрики поста {post_uri[-8:]}...")
            logger.info(f"   ❤️ Лайки: {engagement['likes']}")
            logger.info(f"   🔄 Репосты: {engagement['reposts']}")
            logger.info(f"   💬 Комментарии: {engagement['replies']}")
            logger.info(f"   📈 Общая вовлеченность: {engagement['engagement_rate']}")
            
            return engagement
        except Exception as e:
            # ИСПРАВЛЕНО: Проверяем тип ошибки для правильного логирования
            error_str = str(e)
            if "NotFound" in error_str or "Post not found" in error_str or "400" in error_str:
                logger.info(f"⚠️ Пост {post_uri[-8:]}... больше не существует (удален или недоступен)")
            elif "Response(success=False" in error_str and "400" in error_str:
                logger.info(f"⚠️ Пост {post_uri[-8:]}... недоступен (возможно удален)")
            else:
                logger.error(f"❌ Серьезная ошибка анализа поста {post_uri[-8:]}...: {error_str[:100]}")
            return {'likes': 0, 'reposts': 0, 'replies': 0, 'engagement_rate': 0}

    async def update_posts_with_real_metrics(self) -> None:
        """НОВОЕ: Обновляет посты реальными метриками для обучения"""
        logger.info("📊 Обновление постов реальными метриками...")
        
        # ИСПРАВЛЕНО: Берем только недавние посты (последние 10) для уменьшения нагрузки
        recent_posts = [p for p in self.memory.successful_posts[-10:] if p.get('uri')]
        
        if not recent_posts:
            logger.info("⚠️ Нет постов с URI для анализа метрик")
            return
        
        updated_count = 0
        skipped_count = 0
        
        for post in recent_posts:
            if not post.get('uri'):
                continue
                
            # НОВОЕ: Пропускаем посты старше 24 часов (они могли быть удалены)
            try:
                if 'timestamp' in post:
                    post_time = datetime.fromisoformat(post['timestamp']) if isinstance(post['timestamp'], str) else post['timestamp']
                    age_hours = (datetime.now() - post_time).total_seconds() / 3600
                    if age_hours > 24:
                        logger.info(f"⏳ Пропуск старого поста ({age_hours:.1f}ч): {post['uri'][-8:]}...")
                        skipped_count += 1
                        continue
            except Exception:
                pass  # Если не можем определить возраст, все равно пробуем
                
            try:
                # Получаем реальные метрики
                metrics = await self.analyze_post_performance(post['uri'])
                
                # Обновляем пост реальными данными только если метрики получены
                if metrics['engagement_rate'] > 0 or any(metrics.values()):
                    post['likes'] = metrics['likes']
                    post['reposts'] = metrics['reposts']
                    post['replies'] = metrics['replies']
                    post['final_engagement'] = metrics['engagement_rate']
                    post['metrics_updated'] = datetime.now().isoformat()
                    updated_count += 1
                else:
                    skipped_count += 1
                
                # Пауза между запросами
                await asyncio.sleep(1)
                
            except Exception as e:
                error_str = str(e)
                if "NotFound" not in error_str:
                    logger.warning(f"⚠️ Не удалось обновить метрики поста: {error_str[:80]}...")
                skipped_count += 1
                continue
        
        logger.info(f"✅ Обновлено метрик для {updated_count} постов, пропущено {skipped_count}")
        
        # Сохраняем обновленную память
        self.memory.save()
    
    async def refresh_followers_count(self) -> Optional[int]:
        """Fetch own followers_count, record snapshot, return count."""
        handle = (self.handle or "").strip()
        if not handle or not getattr(self, "bluesky_client", None):
            return None
        try:
            async def _inner():
                return await self.bluesky_client.app.bsky.actor.get_profile(
                    params={"actor": handle}
                )

            profile = await self._atproto_execute(_inner)
            count = getattr(profile, "followers_count", None)
            if count is None:
                return None
            count_i = int(count)
            tracker = getattr(self, "follower_tracker", None)
            if tracker is not None:
                tracker.record(count_i)
            return count_i
        except Exception as e:
            logger.warning(
                "⚠️ Failed to refresh followers count: %s",
                str(e)[:80],
            )
            return None

    def _followers_delta_for_post(
        self,
        post: dict,
        now_count: Optional[int] = None,
    ) -> Optional[float]:
        """Delta since ``followers_at_publish``; None if baseline missing."""
        base = post.get("followers_at_publish")
        if base is None:
            return None
        current = now_count
        if current is None:
            tracker = getattr(self, "follower_tracker", None)
            current = tracker.latest() if tracker is not None else None
        if current is None:
            return None
        try:
            return float(delta_between(base, current))
        except (TypeError, ValueError):
            return None

    async def catch_up_pending_credits(self) -> None:
        """Startup catch-up: fetch metrics + credit missed 6h/24h checks."""
        now = datetime.now(timezone.utc)
        scanned = 0
        credited_n = 0
        format_credited_n = 0
        any_credited = False
        _sg = self._safety_status()
        if not _sg.can_credit:
            logger.info(
                "🛡️ SafetyGovernor: credit blocked — %s",
                ", ".join(_sg.reasons) or "unknown",
            )

        followers_now = await self.refresh_followers_count()

        for post in self.memory.successful_posts:
            checks = eligible_catch_up_checks(post, now)
            fmt_checks = (
                eligible_format_catch_up_checks(post, now)
                if self.format_bandit is not None
                else []
            )
            if not checks and not fmt_checks:
                continue
            scanned += 1
            uri = post.get('uri')
            try:
                metrics = await self.analyze_post_performance(uri)
            except Exception as e:
                logger.warning(
                    "⚠️ Catch-up: не удалось получить метрики %s: %s",
                    str(uri)[-12:] if uri else '?',
                    str(e)[:80],
                )
                continue

            post['likes'] = metrics.get('likes')
            post['reposts'] = metrics.get('reposts')
            post['replies'] = metrics.get('replies')
            if 'engagement_rate' in metrics:
                post['engagement_rate'] = metrics.get('engagement_rate')

            followers_delta = self._followers_delta_for_post(
                post, now_count=followers_now
            )
            result = self.learning.credit_checks_for_post(
                post,
                now,
                can_credit=_sg.can_credit,
                can_sync_config=_sg.can_sync_config,
                followers_delta=followers_delta,
                config=self.config,
            )
            credited_n += int(result.get("strategy_credited", 0))
            format_credited_n += int(result.get("format_credited", 0))
            if result.get("strategy_credited") or result.get("format_credited"):
                any_credited = True

            await asyncio.sleep(0.5)

        if any_credited:
            self.memory.save()

        if scanned or credited_n or format_credited_n:
            logger.info(
                "🔄 Catch-up pending credits: scanned=%s credited=%s "
                "format_credited=%s",
                scanned,
                credited_n,
                format_credited_n,
            )

        await self.catch_up_engagement_credits()

    async def maybe_run_llm_retro(self) -> None:
        """Weekly LLM reflection: propose/apply allowlisted learning_parameters tweaks."""
        retro = getattr(self, "llm_retro", None)
        if not retro or not getattr(self, "_llm_retro_enabled", False):
            return
        interval = int(getattr(self, "_llm_retro_interval_days", 7) or 7)
        if not retro.should_run(interval_days=interval):
            return

        report: dict = {}
        decisions: list = []
        try:
            pl = getattr(self, "policy_learner", None)
            if pl is not None:
                report = pl.report()
            log = getattr(self, "decision_log", None)
            if log is not None:
                decisions = log.recent(50)
        except Exception as exc:
            logger.warning("llm_retro gather context failed: %s", exc)

        async def _generate_json(prompt: str) -> dict:
            ai = getattr(self, "pollinations_ai", None)
            if ai is None or not hasattr(ai, "generate_content"):
                return {}
            raw = await ai.generate_content(
                prompt,
                model_key="smart",
                json_output=True,
            )
            if not raw or not isinstance(raw, str):
                return {}
            text = raw.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if not match:
                    return {}
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return {}
            return data if isinstance(data, dict) else {}

        patch: dict = {}
        raw_for_report: Any = None
        try:
            patch = await retro.propose(_generate_json, report, decisions)
            raw_for_report = patch
        except Exception as exc:
            logger.warning("llm_retro propose failed: %s", exc)
            patch = {}

        applied = False
        if patch and not retro.dry_run:
            config_path = getattr(self, "_config_path", None) or "bot_config.json"
            try:
                applied = bool(retro.apply_patch(config_path, patch))
            except Exception as exc:
                logger.warning("llm_retro apply_patch failed: %s", exc)
                applied = False
            if applied:
                lp = self.config.setdefault("learning_parameters", {})
                if not isinstance(lp, dict):
                    lp = {}
                    self.config["learning_parameters"] = lp
                for key, value in patch.items():
                    lp[key] = value
                    if hasattr(self, "policy_learner") and isinstance(
                        getattr(self.policy_learner, "params", None), dict
                    ):
                        self.policy_learner.params[key] = value

        report_path = retro.write_suggestion_report(
            patch, raw=raw_for_report, applied=applied
        )
        retro.mark_ran()
        logger.info(
            "🧠 LLM retro: patch_keys=%s applied=%s dry_run=%s report=%s",
            sorted(patch.keys()) if patch else [],
            applied,
            retro.dry_run,
            report_path,
        )

    async def catch_up_engagement_credits(self) -> None:
        """Startup catch-up for engagement_actions topic-arm credits (PLRN-011)."""
        eng = getattr(self, "engagement_learner", None)
        if not eng or not eng.enabled:
            return
        actions = getattr(self.memory, "engagement_actions", None) or []
        if not actions:
            return

        now = datetime.now(timezone.utc)
        any_credited = False
        scanned = 0
        credited_n = 0
        _sg = self._safety_status()
        if not _sg.can_credit:
            logger.info(
                "🛡️ SafetyGovernor: credit blocked — %s",
                ", ".join(_sg.reasons) or "unknown",
            )

        for action in actions:
            checks = eligible_engagement_catch_up_checks(action, now)
            if not checks:
                continue
            scanned += 1
            uri = action.get("uri")
            try:
                metrics = await self.analyze_post_performance(uri)
            except Exception as e:
                logger.warning(
                    "⚠️ Engagement catch-up metrics %s: %s",
                    str(uri)[-12:] if uri else "?",
                    str(e)[:80],
                )
                continue

            likes = metrics.get("likes", 0)
            reposts = metrics.get("reposts", 0)
            replies = metrics.get("replies", 0)
            n = self.learning.credit_checks_for_action(
                action,
                now,
                likes,
                replies,
                reposts,
                can_credit=_sg.can_credit,
            )
            if n:
                any_credited = True
                credited_n += n
            await asyncio.sleep(0.5)

        if any_credited:
            self.memory.save()

        if scanned or credited_n:
            logger.info(
                "🔄 Engagement catch-up: scanned=%s credited=%s",
                scanned,
                credited_n,
            )

    async def delayed_engagement_credit_check(
        self, post_uri: str, delay: int
    ) -> None:
        """Delayed 6h/24h credit for a liked foreign post (topic arm)."""
        await asyncio.sleep(delay)
        eng = getattr(self, "engagement_learner", None)
        if not eng or not eng.enabled:
            return
        if delay <= 21600:
            check_id = "6h"
        else:
            check_id = "24h"

        try:
            performance = await self.analyze_post_performance(post_uri)
        except Exception as e:
            logger.error("Engagement delayed metrics failed: %s", e)
            return

        likes = performance.get("likes", 0)
        reposts = performance.get("reposts", 0)
        replies = performance.get("replies", 0)
        actions = getattr(self.memory, "engagement_actions", None) or []
        any_ok = False
        _sg = self._safety_status()
        blocked_logged = False
        for action in actions:
            if action.get("uri") != post_uri:
                continue
            if check_id in (action.get("rewarded_checks") or []):
                continue
            if not _sg.can_credit:
                if not blocked_logged:
                    logger.info(
                        "🛡️ SafetyGovernor: credit blocked — %s",
                        ", ".join(_sg.reasons) or "unknown",
                    )
                    blocked_logged = True
                continue
            n = self.learning.apply_engagement_credits(
                action,
                [check_id],
                likes,
                replies,
                reposts,
                can_credit=_sg.can_credit,
            )
            if n:
                any_ok = True
        if any_ok:
            try:
                self.memory.save()
            except Exception as e:
                logger.warning("engagement credit memory save: %s", e)

    async def delayed_performance_check(self, post_uri: str, delay: int) -> None:
        """Отложенная проверка: метрики; 6h/24h → PolicyLearner credit + config sync."""
        await asyncio.sleep(delay)

        try:
            performance = await self.analyze_post_performance(post_uri)
            er = performance.get('engagement_rate', 0)
            if delay <= 3600:
                check_id = '1h'
            elif delay <= 21600:
                check_id = '6h'
            else:
                check_id = '24h'

            for post in self.memory.successful_posts:
                if post.get('uri') != post_uri:
                    continue

                post['engagement_rate'] = er
                post['final_stats'] = performance
                post['likes'] = performance.get('likes')
                post['reposts'] = performance.get('reposts')
                post['replies'] = performance.get('replies')

                # A/B ER tracking
                ab_fmt = post.get('ab_format')
                if ab_fmt:
                    if check_id == '1h':
                        self.ab_engine.record_er(ab_fmt, er_1h=er)
                    elif check_id == '6h':
                        self.ab_engine.record_er(ab_fmt, er_6h=er)
                    else:
                        self.ab_engine.record_er(ab_fmt, er_24h=er)
                    self.memory.ab_results = self.ab_engine.results
                    logger.info(
                        f"🔬 A/B ER записан: format={ab_fmt}, er={er:.3f} "
                        f"(check={check_id})"
                    )

                # Audience memory: topic_outcomes (telemetry only)
                topic = post.get('type', 'general')
                if topic not in self.memory.topic_outcomes:
                    self.memory.topic_outcomes[topic] = {'total_er': 0.0, 'count': 0}
                self.memory.topic_outcomes[topic]['total_er'] += er
                self.memory.topic_outcomes[topic]['count'] += 1

                if er > 10:
                    logger.info(f"🎯 Успешный пост! Вовлеченность: {er}")

                # Dual-credit on 6h/24h (idempotent via rewarded_checks)
                if check_id in ('6h', '24h'):
                    strategy_key = post.get('strategy_key')
                    _sg = self._safety_status()
                    want_strategy = (
                        bool(strategy_key)
                        and post.get('type') != 'comment'
                        and check_id not in post.get('rewarded_checks', [])
                    )
                    want_format = (
                        self.format_bandit is not None
                        and bool(ab_fmt)
                        and post.get('type') != 'comment'
                        and check_id
                        not in post.get('format_rewarded_checks', [])
                    )
                    if (want_strategy or want_format) and not _sg.can_credit:
                        logger.info(
                            "🛡️ SafetyGovernor: credit blocked — %s",
                            ", ".join(_sg.reasons) or "unknown",
                        )

                    followers_delta = None
                    if want_strategy and _sg.can_credit:
                        followers_now = await self.refresh_followers_count()
                        followers_delta = self._followers_delta_for_post(
                            post, now_count=followers_now
                        )

                    result = self.learning.apply_post_credits(
                        post,
                        [check_id] if want_strategy else [],
                        [check_id] if want_format else [],
                        can_credit=_sg.can_credit,
                        can_sync_config=_sg.can_sync_config,
                        followers_delta=followers_delta,
                        config=self.config,
                    )
                    if (
                        result.get("strategy_credited")
                        or result.get("format_credited")
                    ):
                        self.memory.save()
                break

        except Exception as e:
            logger.error(f"Ошибка анализа производительности: {e}")

    async def maintain_rate_limits(self) -> None:
        """Управление rate limits"""
        # Отслеживаем количество операций
        operations_per_minute = 50
        operation_delay = 60 / operations_per_minute
        
        await asyncio.sleep(operation_delay)
    
    def should_follow_user(self, actor) -> bool:
        """Follow heuristic (FOL-001 → follow_strategy)."""
        return follow_should_follow_user(actor)

    def update_user_relationship(self, user_did: str, action: str, score: float) -> None:
        """Обновляет отношения с пользователем"""
        if user_did not in self.memory.user_relationships:
            self.memory.user_relationships[user_did] = {
                'interactions': 0,
                'score': 0.0,
                'last_interaction': datetime.now(),
                'actions': []
            }
        
        # ЗАЩИТА ОТ СТАРЫХ ЗАПИСЕЙ: добавляем недостающие поля
        user_rel = self.memory.user_relationships[user_did]
        if 'score' not in user_rel:
            user_rel['score'] = 0.0
        if 'interactions' not in user_rel:
            user_rel['interactions'] = 0
        if 'actions' not in user_rel:
            user_rel['actions'] = []
        
        user_rel['interactions'] += 1
        user_rel['score'] += score
        user_rel['last_interaction'] = datetime.now()
        user_rel['actions'].append({
            'action': action,
            'timestamp': datetime.now(),
            'score': score
        })
    
    async def follow_strategy(self) -> None:
        """Follow orchestration (FOL-001 → FollowStrategyOrchestrator)."""
        await self.follow_strategy_orchestrator.run()

    async def _follow_from_suggestions(self) -> int:
        """Suggestions follow source (FOL-001)."""
        return await self.follow_strategy_orchestrator.from_suggestions()

    async def _follow_from_timeline(self) -> int:
        """Timeline follow source (FOL-001)."""
        return await self.follow_strategy_orchestrator.from_timeline()

    def learn_from_memory(self) -> None:
        """PolicyLearner tick: soft-decay + occasional report (no content_performance)."""
        try:
            pl = self.policy_learner
            pl.maybe_decay()
            if pl.cycle_count % 10 == 0:
                report_path = pl.write_report()
                snap = pl.report()
                logger.info(
                    "📊 PolicyLearner cycle=%s credit_mass=%.2f report=%s",
                    snap.get('cycle_count'),
                    float(snap.get('total_credit_mass') or 0.0),
                    report_path,
                )
                # Periodic followers snapshot (PLRN-020); fire-and-forget if loop running
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.refresh_followers_count())
                except RuntimeError:
                    pass
            pl.save()
        except Exception as e:
            logger.error(f"Ошибка PolicyLearner tick: {e}")
        try:
            fb = getattr(self, "format_bandit", None)
            if fb is not None:
                fb.maybe_decay()
                fb.save()
        except Exception as e:
            logger.error(f"Ошибка FormatBandit tick: {e}")
        try:
            eng = getattr(self, "engagement_learner", None)
            if eng and eng.enabled:
                eng.maybe_decay()
                eng.save()
        except Exception as e:
            logger.error(f"Ошибка EngagementLearner tick: {e}")

    async def upload_image_to_bluesky(self, image_url: str) -> Optional[Dict]:
        """Thin delegate → :class:`MediaService`."""
        return await self.media_service.upload_image_to_bluesky(image_url)

    async def create_post_with_image(
        self, text: str, image_url: str, alt_text: str = "Изображение к посту"
    ) -> Optional[RichTextPost]:
        """Thin delegate → :class:`MediaService` (strategy CallableImageUpload compat)."""
        return await self.media_service.create_post_with_image(
            text, image_url, alt_text=alt_text
        )

    async def create_post_with_link_preview(
        self,
        text: str,
        url: str,
        title: str,
        description: str,
        image_url: str = None,
    ) -> Optional[RichTextPost]:
        """Thin delegate → :class:`MediaService`."""
        return await self.media_service.create_post_with_link_preview(
            text, url, title, description, image_url=image_url
        )

    async def create_image_prompt_from_text(self, text: str) -> str:
        """Создает качественный промпт для генерации изображения из текста поста"""
        
        prompt = f"""
        Extract the core visual essence from the following text and create a concise, descriptive, artistic prompt in English for an image generation AI (like DALL-E 3).
        Focus on concepts, objects, and mood. Avoid text in the image. The prompt should be short and powerful.

        Text: "{text}"

        Desired Style: Digital art, vibrant colors, slightly abstract, emotional.

        Example:
        Text: "Friday code is a special art. Either brilliant or catastrophic 🎭"
        Prompt: "Digital art of a split screen, one side showing a glowing, elegant line of code, the other side showing chaotic, messy spaghetti code, vibrant colors, dramatic contrast."

        Create the English prompt now:
        """
        # Используем мощную модель для творческой задачи
        image_prompt = await self.pollinations_ai.generate_content(
            prompt,
            model_key='powerful' 
        )

        if image_prompt and not image_prompt.startswith("❌"):
            # Очищаем промпт от лишнего текста
            cleaned_prompt = image_prompt.replace("Prompt:", "").replace("\"", "").strip()
            logger.info(f"🎨 Создан промпт для изображения: {cleaned_prompt}")
            return cleaned_prompt
            
        logger.warning("⚠️ Не удалось создать промпт для изображения. Используем fallback.")
        return "Abstract digital art, vibrant colors, lines and shapes, expressive" # Fallback промпт

    async def upload_image_data_to_bluesky(self, image_data: bytes) -> Optional[Dict]:
        """Thin delegate → :class:`MediaService` (CallableImageUpload compat)."""
        return await self.media_service.upload_image_data_to_bluesky(image_data)

    async def generate_structured_post_content(self, prompt: str, model_key: str = 'creative') -> Optional[Dict[str, str]]:
        """Генерирует структурированный пост (текст + хештеги) и возвращает dict.

        Автоматически добавляет:
        - A/B format suffix для текущего цикла генерации
        - Усиленный промпт при повторной генерации после Quality Gate
        """
        prompt = self.content_service.build_structured_prompt(prompt)

        def _parse_and_normalize(raw: str) -> Optional[Dict[str, str]]:
            data = None
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Be tolerant to wrappers like markdown fences or leading text.
                m = re.search(r"\{[\s\S]*\}", raw)
                if m:
                    data = json.loads(m.group(0))
                else:
                    return None

            if not (isinstance(data, dict) and 'post_text' in data and 'hashtags' in data):
                return None

            post_text = str(data.get('post_text', '')).strip()
            hashtags = str(data.get('hashtags', '')).strip()
            if not post_text:
                return None

            tags = []
            for token in re.split(r"[,\s]+", hashtags.replace("\n", " ").strip()):
                t = token.strip()
                if not t:
                    continue
                if not t.startswith('#'):
                    t = f"#{t}"
                t = re.sub(r"[^#A-Za-z0-9_]", "", t)
                if len(t) > 1:
                    tags.append(t)
            tags = list(dict.fromkeys(tags))[:4]
            if len(tags) < 2:
                tags = ['#tech', '#insight']
            return {'post_text': post_text, 'hashtags': ' '.join(tags)}

        try:
            raw_response = await self.pollinations_ai.generate_content(prompt, model_key=model_key, json_output=True)
            if raw_response:
                normalized = _parse_and_normalize(raw_response)
                if normalized:
                    logger.info("✅ AI сгенерировал структурированный пост (текст + хештеги)")
                    return normalized

            # One lightweight retry with a stricter, faster model when JSON is malformed.
            if model_key != 'fast':
                retry_prompt = prompt + "\n\nReturn strict JSON only. No prose outside JSON."
                retry_raw = await self.pollinations_ai.generate_content(retry_prompt, model_key='fast', json_output=True)
                if retry_raw:
                    normalized = _parse_and_normalize(retry_raw)
                    if normalized:
                        logger.info("✅ AI сгенерировал структурированный пост (ретрай fast-модель)")
                        return normalized
        except json.JSONDecodeError:
            logger.error("❌ Ошибка декодирования JSON от AI. Ответ не был в формате JSON.")
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации структурированного контента: {e}")

        return None

    async def _create_post_with_image_generation(
        self,
        content_creation_func,
        image_prompt_text: str,
        content_type: str,
        fallback_func=None
    ) -> RichTextPost:
        """Create post with image (delegates to ImagePostHelper / STRAT-004)."""
        return await self.image_post_helper.create(
            content_creation_func,
            image_prompt_text,
            content_type,
            fallback_func,
        )


    async def test_rss_feeds_diagnostics(self) -> Dict[str, any]:
        """Диагностика работы RSS-фидов для выявления проблем"""
        logger.info("🔧 Запуск диагностики RSS-фидов...")
        
        diagnostics = {
            'total_feeds': len(self.rss_feeds),
            'working_feeds': 0,
            'failed_feeds': 0,
            'total_entries': 0,
            'feeds_status': [],
            'recommendations': []
        }
        
        for i, feed_url in enumerate(self.rss_feeds[:10]):  # Тестируем первые 10
            source_name = feed_url.split('//')[-1].split('/')[0]
            feed_status = {
                'url': feed_url,
                'name': source_name,
                'status': 'unknown',
                'entries_count': 0,
                'response_time': 0,
                'error': None
            }
            
            try:
                try:
                    feed_url = validate_outbound_url(feed_url)
                    feed_status['url'] = feed_url
                except UnsafeURLError as e:
                    feed_status['status'] = 'unsafe_url'
                    feed_status['error'] = str(e)[:100]
                    diagnostics['failed_feeds'] += 1
                    diagnostics['feeds_status'].append(feed_status)
                    logger.warning(f"   ⚠️ {source_name}: unsafe URL ({e})")
                    continue

                logger.info(f"📡 Тестирование {i+1}/10: {source_name}")
                
                start_time = datetime.now()
                timeout = 15
                
                # Используем единую HTTP сессию бота для диагностики
                await self._ensure_http_session()

                async with self.http_session.get(feed_url, timeout=timeout) as response:
                        response_time = (datetime.now() - start_time).total_seconds()
                        feed_status['response_time'] = response_time
                        
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)
                            
                            entries_count = len(feed.entries)
                            feed_status['entries_count'] = entries_count
                            feed_status['status'] = 'working'
                            
                            diagnostics['working_feeds'] += 1
                            diagnostics['total_entries'] += entries_count
                            
                            logger.info(f"   ✅ {source_name}: {entries_count} записей за {response_time:.1f}с")
                            
                        else:
                            feed_status['status'] = 'http_error'
                            feed_status['error'] = f"HTTP {response.status}"
                            diagnostics['failed_feeds'] += 1
                            logger.warning(f"   ❌ {source_name}: HTTP {response.status}")
                            
            except asyncio.TimeoutError:
                feed_status['status'] = 'timeout'
                feed_status['error'] = f"Timeout ({timeout}s)"
                diagnostics['failed_feeds'] += 1
                logger.warning(f"   ⏰ {source_name}: таймаут")
                
            except Exception as e:
                feed_status['status'] = 'error'
                feed_status['error'] = str(e)[:100]
                diagnostics['failed_feeds'] += 1
                logger.warning(f"   ❌ {source_name}: {str(e)[:50]}...")
                
            diagnostics['feeds_status'].append(feed_status)
            await asyncio.sleep(0.5)  # Пауза между запросами
        
        # Анализ и рекомендации
        success_rate = (diagnostics['working_feeds'] / len(diagnostics['feeds_status'])) * 100
        
        if success_rate < 50:
            diagnostics['recommendations'].append("Критически низкий процент рабочих RSS-фидов")
        elif success_rate < 70:
            diagnostics['recommendations'].append("Следует заменить неработающие RSS-фиды")
        
        if diagnostics['total_entries'] < 50:
            diagnostics['recommendations'].append("Мало записей из RSS - увеличить количество источников")
        
        # Финальный отчет
        logger.info(f"📊 Диагностика RSS завершена:")
        logger.info(f"   🌐 Всего фидов протестировано: {len(diagnostics['feeds_status'])}")
        logger.info(f"   ✅ Рабочих: {diagnostics['working_feeds']}")
        logger.info(f"   ❌ Неработающих: {diagnostics['failed_feeds']}")
        logger.info(f"   📰 Всего записей получено: {diagnostics['total_entries']}")
        logger.info(f"   📈 Процент успеха: {success_rate:.1f}%")
        
        if diagnostics['recommendations']:
            logger.info(f"💡 Рекомендации:")
            for rec in diagnostics['recommendations']:
                logger.info(f"   - {rec}")
        
        return diagnostics

    async def analyze_post_diversity(self) -> Dict[str, any]:
        """Анализирует разнообразие созданных постов для выявления паттернов"""
        logger.info("📊 Запуск анализа разнообразия постов...")
        
        analysis = {
            'total_posts': len(self.memory.successful_posts),
            'posts_with_questions': 0,
            'posts_with_statements': 0,
            'posts_with_observations': 0,
            'posts_with_emojis': 0,
            'question_patterns': [],
            'statement_patterns': [],
            'diversity_score': 0.0,
            'recommendations': []
        }
        
        if not self.memory.successful_posts:
            logger.warning("⚠️ Нет постов для анализа")
            return analysis
        
        # Анализируем последние 50 постов (или все если меньше)
        recent_posts = self.memory.successful_posts[-50:]
        
        for post in recent_posts:
            text = post.get('text', '')
            if not text:
                continue
                
            # Проверяем наличие вопросов
            if '?' in text:
                analysis['posts_with_questions'] += 1
                # Извлекаем вопросительные части
                questions = [q.strip() for q in text.split('?') if q.strip()]
                analysis['question_patterns'].extend(questions[-1:])  # Берем последний вопрос
            else:
                # Это утверждение или наблюдение
                if any(word in text.lower() for word in ['noticed', 'observed', 'watching', 'seeing', 'interesting']):
                    analysis['posts_with_observations'] += 1
                else:
                    analysis['posts_with_statements'] += 1
                    
                # Извлекаем паттерны утверждений (последнее предложение)
                sentences = text.split('.')
                if len(sentences) > 1:
                    analysis['statement_patterns'].append(sentences[-2].strip() if sentences[-1].strip() == '' else sentences[-1].strip())
                
            # Проверяем эмодзи
            emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002700-\U000027BF]', text))
            if emoji_count > 0:
                analysis['posts_with_emojis'] += 1
        
        total_analyzed = len(recent_posts)
        
        # Вычисляем разнообразие
        question_ratio = analysis['posts_with_questions'] / total_analyzed if total_analyzed > 0 else 0
        statement_ratio = analysis['posts_with_statements'] / total_analyzed if total_analyzed > 0 else 0
        observation_ratio = analysis['posts_with_observations'] / total_analyzed if total_analyzed > 0 else 0
        emoji_ratio = analysis['posts_with_emojis'] / total_analyzed if total_analyzed > 0 else 0
        
        # Идеальное разнообразие: 30% вопросы, 50% утверждения, 20% наблюдения
        ideal_question_ratio = 0.3
        ideal_statement_ratio = 0.5
        ideal_observation_ratio = 0.2
        
        # Вычисляем отклонение от идеального распределения
        question_deviation = abs(question_ratio - ideal_question_ratio)
        statement_deviation = abs(statement_ratio - ideal_statement_ratio)
        observation_deviation = abs(observation_ratio - ideal_observation_ratio)
        
        # Счет разнообразия (0-1, где 1 = идеальное разнообразие)
        diversity_score = 1.0 - (question_deviation + statement_deviation + observation_deviation) / 3
        analysis['diversity_score'] = max(0.0, diversity_score)
        
        # Формируем рекомендации
        if question_ratio > 0.6:
            analysis['recommendations'].append("🔥 КРИТИЧНО: Слишком много вопросов! Нужно больше утверждений и наблюдений")
        elif question_ratio > 0.4:
            analysis['recommendations'].append("⚠️ Много вопросов. Рекомендуется снизить долю до 30%")
        elif question_ratio < 0.1:
            analysis['recommendations'].append("💡 Слишком мало вопросов. Можно добавить немного интерактивности")
            
        if statement_ratio < 0.3:
            analysis['recommendations'].append("📝 Недостаточно четких утверждений. Нужно больше уверенности в постах")
            
        if emoji_ratio < 0.3:
            analysis['recommendations'].append("😊 Мало эмодзи. Можно добавить больше эмоциональности")
        elif emoji_ratio > 0.8:
            analysis['recommendations'].append("😅 Слишком много эмодзи. Можно сделать часть постов более серьезными")
        
        # Логируем результаты
        logger.info(f"📊 Анализ разнообразия завершен:")
        logger.info(f"   📈 Всего постов проанализировано: {total_analyzed}")
        logger.info(f"   ❓ Посты с вопросами: {analysis['posts_with_questions']} ({question_ratio:.1%})")
        logger.info(f"   💬 Посты с утверждениями: {analysis['posts_with_statements']} ({statement_ratio:.1%})")
        logger.info(f"   👁️ Посты с наблюдениями: {analysis['posts_with_observations']} ({observation_ratio:.1%})")
        logger.info(f"   😊 Посты с эмодзи: {analysis['posts_with_emojis']} ({emoji_ratio:.1%})")
        logger.info(f"   🎯 Оценка разнообразия: {analysis['diversity_score']:.2f}/1.0")
        
        if analysis['recommendations']:
            logger.info("💡 Рекомендации:")
            for rec in analysis['recommendations']:
                logger.info(f"   - {rec}")
        
        # Примеры частых паттернов
        if len(analysis['question_patterns']) > 0:
            frequent_questions = Counter(analysis['question_patterns']).most_common(3)
            logger.info("❓ Частые вопросительные паттерны:")
            for pattern, count in frequent_questions:
                logger.info(f"   - '{pattern[:50]}...' ({count} раз)")
                
        if len(analysis['statement_patterns']) > 0:
            frequent_statements = Counter(analysis['statement_patterns']).most_common(3)
            logger.info("💬 Частые паттерны утверждений:")
            for pattern, count in frequent_statements:
                logger.info(f"   - '{pattern[:50]}...' ({count} раз)")
        
        return analysis
    
    async def health_monitor(self) -> Dict[str, Any]:
        """Thin delegate → :class:`HealthService`."""
        return await self.health_service.health_monitor()

    async def emergency_recovery(self) -> bool:
        """Thin delegate → :class:`HealthService`."""
        return await self.health_service.emergency_recovery()

async def main():
    load_dotenv(override=False)

    # Fail-fast: require real Bluesky creds from env (no interactive prompt).
    # Empty / whitespace / placeholder values must not reach bot construction.
    handle = (os.getenv('BLUESKY_HANDLE') or '').strip()
    password = (os.getenv('BLUESKY_PASSWORD') or '').strip()

    creds_missing = not handle or not password
    creds_placeholder = ('your-' in handle) or ('your-' in password)
    if creds_missing or creds_placeholder:
        logger.error("❌ Необходимо настроить учетные данные!")
        logger.info("Установите переменные окружения:")
        logger.info("  BLUESKY_HANDLE - ваш handle в Bluesky")
        logger.info("  BLUESKY_PASSWORD - пароль приложения")
        logger.info("  OPENROUTER_API_KEY - ключ OpenRouter (предпочтительно)")
        logger.info("  OPENAI_API_KEY - ключ API OpenAI (опциональный backup)")
        sys.exit(1)
    
    instance_lock = SingleInstanceLock(
        path=os.path.join(log_dir, 'bot.lock'),
        stale_seconds=600,
    )
    try:
        instance_lock.acquire()
    except RuntimeError as e:
        logger.error(f"❌ {e}")
        sys.exit(1)

    try:
        bot = AutonomousBlueskyBotV2()
        try:
            await bot.run_bot_cycle()
        except KeyboardInterrupt:
            logger.info("⌨️ Получен сигнал остановки")
        finally:
            await bot.shutdown()
    finally:
        instance_lock.release()


if __name__ == "__main__":
    asyncio.run(main()) 