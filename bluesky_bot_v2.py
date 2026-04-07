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
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Set, Tuple
import aiohttp
import feedparser
from atproto import AsyncClient, models
from dynamic_content_system import BlueSkyTrendingTracker, DynamicContentGenerator
import openai
from openai import AsyncOpenAI
from dataclasses import dataclass, asdict, field
import re
import time
import html
import hashlib
from dotenv import load_dotenv
from bot_learning_module import BotLearningModule

# Новые импорты для форматирования
from bluesky_post_formatter import BlueskyPostFormatter, PostTemplates, RichTextPost
from bluesky_rich_posts import BlueskyRichPostCreator, PostFactory, ImageData, LinkCard

# Добавляем импорт нашего адаптера
from pollinations_adapter import PollinationsAI

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
    CircuitBreaker, RetryPolicy, ErrorClass, classify_error, backoff_seconds,
)
from log_sanitizer import SanitizingFilter
from engagement_service import EngagementService
from content_service import ContentService

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
        
        # Получаем креденциалы из переменных окружения
        self.handle = os.getenv('BLUESKY_HANDLE')
        self.password = os.getenv('BLUESKY_PASSWORD')
        
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
        
        # AI clients - Pollinations.AI priority with English language
        self.pollinations_ai = PollinationsAI(default_model='creative', language='en')
        self.ai_client = None  # OpenAI as backup
        
        # Инициализация OpenAI только как fallback
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key and openai_key != 'your-openai-key':
            try:
                self.ai_client = AsyncOpenAI(api_key=openai_key)
                logger.info("📱 OpenAI клиент инициализирован как резервный")
            except Exception as e:
                logger.warning(f"⚠️ OpenAI недоступен (будет использоваться только Pollinations): {e}")
        else:
            logger.info("🚀 Работаем только с Pollinations.AI (OpenAI ключ не найден)")
        
        # Инициализация форматировщиков с передачей клиента для резолва DID
        self.formatter = BlueskyPostFormatter(client=self.bluesky_client)
        self.rich_creator = BlueskyRichPostCreator(self.bluesky_client)
        
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
        self.languages = ['en', 'ru']  # English first priority
        
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
        
        # НОВОЕ: Защита от повторных действий (с восстановлением из памяти)
        self.commented_posts = set(getattr(self.memory, 'commented_posts_cache', set()))
        self.recent_comments = getattr(self.memory, 'recent_comments_cache', [])
        self.liked_posts = set(getattr(self.memory, 'liked_posts_cache', set()))
        self.reposted_posts = set(getattr(self.memory, 'reposted_posts_cache', set()))
        self.followed_users = set(getattr(self.memory, 'followed_users_cache', set()))
        
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

        # Инициализация модуля обучения
        self.learning_module = BotLearningModule(self.memory, 'bot_config.json')
        
        # Инициализация системы трендов и динамической генерации контента
        self.trending_tracker = BlueSkyTrendingTracker(self.bluesky_client)
        self.dynamic_generator = DynamicContentGenerator(self.trending_tracker)
        
        # НОВОЕ: Инициализация улучшенных AI компонентов
        self.content_analyzer = ContentQualityAnalyzer()
        self.engagement_optimizer = EngagementOptimizer()

        # Action ledger for idempotency
        self.action_ledger = ActionLedger()
        self.engagement_service = EngagementService(self)
        self.content_service = ContentService(self)

        # Activity budget (ATProto write-point caps)
        budget_cfg = self.config.get('activity_budget', {})
        self.activity_budget = ActivityBudget(
            hourly_limit=budget_cfg.get('hourly_points', 4500),
            daily_limit=budget_cfg.get('daily_points', 30000),
            action_costs=budget_cfg.get('action_costs'),
        )

        # Per-subsystem circuit breakers
        self._cb_bluesky = CircuitBreaker('bluesky_api', failure_threshold=5, recovery_timeout=300)
        self._cb_ai = CircuitBreaker('ai_generation', failure_threshold=3, recovery_timeout=180)
        self._cb_rss = CircuitBreaker('rss_fetch', failure_threshold=4, recovery_timeout=120)

        # Growth Engine
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() in ('true', '1', 'yes')
        self.dry_run_log = DryRunAction() if self.dry_run else None
        # A/B suffix for current generation cycle
        self._current_ab_format = 'format_a'
        self._current_ab_suffix = ''
        self._quality_gate_regen_mode = False
        # Circuit breaker (main loop level)
        self._consecutive_errors = 0
        # Trend Radar signal caches
        self._trend_timeline_snippets: list = []
        self._trend_rss_headlines: list = []
        # Async task registry
        self._background_tasks: set = set()
        self.quality_gate = QualityGate(self.config)
        self.ab_engine = ABEngine(self.memory.ab_results)
        rel_groups = self.config.get('relevance_settings', {}).get('topic_groups', {})
        self.trend_radar = TrendRadar(rel_groups)
        self.repost_policy = RepostPolicyFilter(self.config)
        self.rss_manager = RSSSourceManager(self.config, self.http_session)
        self.recent_repost_authors: List[str] = []
        if self.dry_run:
            logger.info("🧪 DRY-RUN режим: никакие действия не будут выполнены")

        # Система мониторинга активности (heartbeat)
        self.last_heartbeat = datetime.now()
        self.heartbeat_file = 'bot_heartbeat.txt'
    
    def load_external_config(self, config_file='bot_config.json'):
        """Загружает внешнюю конфигурацию, чтобы ее можно было изменять."""
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
        """Создает HTTP сессию с надежными таймаутами"""
        timeout = aiohttp.ClientTimeout(
            total=60,      # Общий таймаут запроса
            connect=10,    # Таймаут соединения 
            sock_read=30   # Таймаут чтения данных
        )
        
        self.http_session = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(
                limit=20,           # Максимум 20 одновременных соединений
                limit_per_host=5,   # Максимум 5 на хост
                ttl_dns_cache=300,  # Кэш DNS на 5 минут
                use_dns_cache=True,
                keepalive_timeout=30
            )
        )
        logger.info("🌐 HTTP сессия создана с защитными таймаутами")
    
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
        """Обновляет файл heartbeat для мониторинга активности"""
        try:
            self.last_heartbeat = datetime.now()
            with open(self.heartbeat_file, 'w') as f:
                f.write(f"{self.last_heartbeat.isoformat()}\n")
                f.write(f"PID: {os.getpid()}\n")
                f.write(f"Status: active\n")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось обновить heartbeat: {e}")
    
    def _check_for_hanging(self) -> bool:
        """Проверяет не завис ли бот на основе heartbeat файла"""
        try:
            if not os.path.exists(self.heartbeat_file):
                return False
                
            with open(self.heartbeat_file, 'r') as f:
                lines = f.readlines()
                if not lines:
                    return False
                    
                last_heartbeat_str = lines[0].strip()
                last_heartbeat = datetime.fromisoformat(last_heartbeat_str)
                
                # Если heartbeat старше 15 минут - возможное зависание
                time_diff = (datetime.now() - last_heartbeat).total_seconds()
                if time_diff > 900:  # 15 минут
                    logger.warning(f"⚠️ Потенциальное зависание: последний heartbeat {time_diff/60:.1f} минут назад")
                    return True
                    
                return False
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки зависания: {e}")
            return False
    
    # Копируем все базовые методы из оригинального бота
    def clean_html(self, raw_html: str) -> str:
        """Удаляет HTML-теги из строки и декодирует HTML-сущности"""
        if not raw_html:
            return ""
        text = html.unescape(raw_html)
        clean_text = re.sub(r'<[^>]+>', '', text)
        clean_text = re.sub(r'submitted by /u/[\w-]+', '', clean_text)
        clean_text = re.sub(r'\[link\]|\[comments\]', '', clean_text)
        return clean_text.strip()
    
    def _generate_content_hash(self, text: str, url: str = None, image_url: str = None) -> str:
        """Генерирует хеш для контента чтобы избежать дубликатов"""
        # Создаем строку из основных элементов контента
        content_parts = [text.lower().strip()]
        if url:
            content_parts.append(url)
        if image_url:
            content_parts.append(image_url)
        
        content_string = "|".join(content_parts)
        return hashlib.md5(content_string.encode('utf-8')).hexdigest()
    
    def _is_duplicate_content(self, text: str, url: str = None, image_url: str = None) -> bool:
        """Проверяет, является ли контент дубликатом уже опубликованного"""
        content_hash = self._generate_content_hash(text, url, image_url)
        
        # Проверяем хеш контента
        if content_hash in self.memory.published_content_hashes:
            logger.info(f"🔄 Найден дубликат по хешу контента: {content_hash[:8]}...")
            return True
        
        # Проверяем URL отдельно (для новостей)
        if url and url in self.memory.published_urls:
            logger.info(f"🔄 Найден дубликат по URL: {url[:50]}...")
            return True
        
        # Проверяем схожесть текста с недавними постами (последние 20)
        recent_posts = self.memory.successful_posts[-20:] if self.memory.successful_posts else []
        for post in recent_posts:
            if 'text' in post:
                similarity = self._calculate_text_similarity(text, post['text'])
                if similarity > 0.8:  # 80% схожести
                    logger.info(f"🔄 Найден дубликат по схожести текста: {similarity:.2f}")
                    return True
        
        return False
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Простая оценка схожести текстов"""
        # Убираем хештеги и эмодзи для сравнения
        clean_text1 = re.sub(r'[#@][\w]+|[^\w\s]', '', text1.lower()).strip()
        clean_text2 = re.sub(r'[#@][\w]+|[^\w\s]', '', text2.lower()).strip()
        
        if not clean_text1 or not clean_text2:
            return 0.0
        
        # Разбиваем на слова
        words1 = set(clean_text1.split())
        words2 = set(clean_text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        # Коэффициент Жаккара (пересечение / объединение)
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _mark_content_as_published(self, text: str, url: str = None, image_url: str = None) -> None:
        """Отмечает контент как опубликованный"""
        content_hash = self._generate_content_hash(text, url, image_url)
        self.memory.published_content_hashes.add(content_hash)
        
        if url:
            self.memory.published_urls.add(url)
        
        # Ограничиваем размер множеств (храним последние 500 записей)
        if len(self.memory.published_content_hashes) > 500:
            # Преобразуем в список, удаляем первые 100, преобразуем обратно
            hashes_list = list(self.memory.published_content_hashes)
            self.memory.published_content_hashes = set(hashes_list[-400:])
        
        if len(self.memory.published_urls) > 500:
            urls_list = list(self.memory.published_urls)
            self.memory.published_urls = set(urls_list[-400:])
        
        logger.debug(f"📝 Контент отмечен как опубликованный: {content_hash[:8]}...")
    
    def _cleanup_old_content_hashes(self) -> None:
        """Очищает старые хеши контента и применяет retention к спискам памяти."""
        cutoff_date = datetime.now() - timedelta(days=30)

        recent_hashes = set()
        recent_urls = set()

        for post in self.memory.successful_posts:
            if post.get('timestamp'):
                try:
                    post_date = datetime.fromisoformat(post['timestamp']) if isinstance(post['timestamp'], str) else post['timestamp']
                    if post_date > cutoff_date:
                        if 'content_hash' in post:
                            recent_hashes.add(post['content_hash'])
                        if 'url' in post:
                            recent_urls.add(post['url'])
                except Exception:
                    pass

        old_hash_count = len(self.memory.published_content_hashes)
        old_url_count = len(self.memory.published_urls)
        self.memory.published_content_hashes = recent_hashes
        self.memory.published_urls = recent_urls
        logger.info(f"🧹 Хеши: {old_hash_count}->{len(recent_hashes)}, URLs: {old_url_count}->{len(recent_urls)}")

        # Retention: trim long-lived lists
        retention_limits = {
            'successful_posts': 500,
            'failed_posts': 200,
            'repost_performance': 200,
            'viral_posts': 100,
            'pattern_blacklist': 50,
        }
        for attr, limit in retention_limits.items():
            lst = getattr(self.memory, attr, None)
            if lst is not None and isinstance(lst, list) and len(lst) > limit:
                old_len = len(lst)
                setattr(self.memory, attr, lst[-limit:])
                logger.info(f"🧹 Retention {attr}: {old_len}->{limit}")
    
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
    
    async def _create_fallback_post_for_duplicate(self) -> Optional[RichTextPost]:
        """Создает альтернативный пост когда основной оказался дубликатом"""
        logger.info("🎭 Создание fallback поста для замены дубликата...")
        
        # Приоритетный список альтернативных стратегий (избегаем новости)
        fallback_strategies = [
            (self._create_personal_opinion_post, "личное мнение"),
            (self._create_quality_ai_insight, "AI инсайт"),
            (self._create_quality_tip_post, "совет из опыта"),
            (self._create_quality_discussion, "дискуссия"),
            (self._create_motivational_moment_post, "мотивационный момент")
        ]
        
        # Пробуем каждую стратегию до получения уникального контента
        for strategy_func, strategy_name in fallback_strategies:
            try:
                logger.info(f"🔄 Пробуем стратегию: {strategy_name}")
                post = await strategy_func()
                
                if post:
                    # Проверяем уникальность
                    url = getattr(post, 'url', None) if hasattr(post, 'url') else None
                    image_url = getattr(post, 'image_url', None) if hasattr(post, 'image_url') else None
                    
                    if not self._is_duplicate_content(post.text, url, image_url):
                        logger.info(f"✅ Успешно создан fallback пост: {strategy_name}")
                        return post
                    else:
                        logger.info(f"🔄 Fallback стратегия '{strategy_name}' тоже дубликат, пробуем следующую")
                        
            except Exception as e:
                logger.warning(f"⚠️ Ошибка в fallback стратегии '{strategy_name}': {e}")
                continue
        
        # Если все стратегии не сработали, создаем экстренный пост
        logger.warning("⚠️ Все fallback стратегии не сработали, создаем экстренный пост")
        return await self._create_emergency_unique_post()
    
    async def _create_motivational_moment_post(self) -> RichTextPost:
        """Создает мотивационный пост с динамическими хештегами и изображением"""
        motivation_themes = [
            "преодоление трудностей", 
            "достижение целей",
            "личностный рост",
            "начинания и проекты",
            "прогресс и развитие"
        ]
        selected_theme = random.choice(motivation_themes)

        async def content_creator():
            ai_prompt = f"""
            Create an inspiring, non-cliche motivational post about "{selected_theme}".
            Provide the output in JSON format with "post_text" (in English, 150-200 characters, fresh and engaging) and "hashtags" (in English, 3 relevant tags).

            Example for "achieving goals":
            {{
              "post_text": "Цель не в том, чтобы никогда не падать, а в том, чтобы каждый раз находить новый способ подняться. Какой ваш следующий подъем? 🚀",
              "hashtags": "#мотивация #цели #рост #упорство"
            }}
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='creative')

        async def fallback_creator():
            current_time = datetime.now().strftime("%H:%M")
            return {
                "post_text": f"💭 Thought of the day ({current_time}):\n\nWhat motivates you to move forward right now?",
                "hashtags": "#motivation #thoughts #development"
            }

        return await self._create_post_with_image_generation(
            content_creator,
            selected_theme,
            'motivational',
            fallback_creator
        )
    
    async def _create_emergency_unique_post(self) -> RichTextPost:
        """Создает экстренный пост с динамическими хештегами и изображением"""
        emergency_themes = [
            "момент рефлексии",
            "случайная мысль",
            "настроение дня",
            "простое наблюдение"
        ]
        selected_theme = random.choice(emergency_themes)

        async def content_creator():
            ai_prompt = f"""
            Create a short, spontaneous post about "{selected_theme}".
            Provide the output in JSON format with "post_text" (in English, 120-180 characters, simple and human-like) and "hashtags" (in English, 2-3 relevant tags).

            Example for "random thought":
            {{
              "post_text": "Иногда самые простые моменты приносят больше всего радости. Замечали? ✨",
              "hashtags": "#момент #жизнь #мысли"
            }}
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='fast')

        async def fallback_creator():
            timestamp = datetime.now().strftime('%d.%m %H:%M:%S')
            return {
                "post_text": f"💭 Random thought of the moment:\n\nWhat's on your mind right now? ({timestamp})",
                "hashtags": "#moment #thoughts"
            }

        return await self._create_post_with_image_generation(
            content_creator,
            selected_theme,
            'emergency',
            fallback_creator
        )

    async def authenticate(self, force_login: bool = False) -> bool:
        """Session-first auth: restore persisted session, fallback to login."""
        if not self.http_session:
            self.http_session = aiohttp.ClientSession()
            logger.info("🌐 HTTP сессия инициализирована")

        # --- Phase 1: try restoring a persisted session ---
        if not force_login:
            saved = self.session_store.load()
            if saved:
                try:
                    profile = await self.bluesky_client.login(session_string=saved)
                    self.authenticated = True
                    self._persist_session()
                    logger.info(f"✅ Сессия восстановлена для {getattr(profile, 'handle', self.handle)}")
                    return True
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось восстановить сессию: {e}. Переход к login.")
                    self.session_store.clear()

        # --- Phase 2: full login with retry ---
        max_retries = 3
        base_delay = 60

        for attempt in range(max_retries):
            try:
                await self.bluesky_client.login(self.handle, self.password)
                self.authenticated = True
                self._persist_session()
                logger.info(f"✅ Успешная авторизация: {self.handle}")
                return True
            except Exception as e:
                ec = classify_error(e)
                if ec == ErrorClass.RATE_LIMIT:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"⚠️ Rate limit. Попытка {attempt + 1}/{max_retries}, backoff {delay}s")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay)
                        continue
                    logger.error("❌ Достигнуто макс. кол-во попыток авторизации (rate limit)")
                    return False
                logger.error(f"❌ Ошибка авторизации ({ec.value}): {e}")
                return False
        return False

    def _persist_session(self) -> None:
        try:
            ss = self.bluesky_client.export_session_string()
            if ss:
                self.session_store.save(ss)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сохранить сессию: {e}")
    
    # НОВЫЕ МЕТОДЫ ДЛЯ КРАСИВЫХ ПОСТОВ
    
    async def create_scheduled_post(self) -> None:
        """ИСПРАВЛЕННОЕ создание запланированного поста с контролем качества и динамическими весами"""
        try:
            # Budget gate — check before any generation work
            if not self.activity_budget.can_spend('post'):
                logger.info("📊 Activity budget exhausted for posting — skipping cycle")
                return

            # Проверяем дневной лимит
            current_date = datetime.now().date()
            if current_date != self.last_post_date:
                self.daily_post_count = 0
                self.last_post_date = current_date
            
            if self.daily_post_count >= self.max_posts_per_day:
                logger.info(f"📊 Достигнут дневной лимит постов ({self.max_posts_per_day}). Пропускаем.")
                return
            
            # НИКОГДА НЕ СОЗДАЕМ THREAD АВТОМАТИЧЕСКИ
            logger.info("🎨 Создание качественного поста...")
            
            # Получаем стратегии и веса из ЗАГРУЖЕННОЙ конфигурации
            strategies_config = self.config.get('post_strategies', {})
            strategies = []
            for func_name, weight in strategies_config.items():
                if hasattr(self, func_name):
                    strategies.append((getattr(self, func_name), weight))
            
            if not strategies:
                logger.error("❌ Не найдено ни одной валидной стратегии в конфигурации!")
                return
            
            # A/B format selection — persist suffix so generators can read it
            ab_format = self.ab_engine.pick_format()
            self._current_ab_format = ab_format
            self._current_ab_suffix = self.ab_engine.get_prompt_suffix(ab_format)
            logger.info(f"🔬 A/B формат: {ab_format} | suffix len={len(self._current_ab_suffix)}")

            # Trend Radar: topic of the day from successful_posts + cached timeline + RSS headlines
            trend_topic = None
            try:
                trend_texts = [p.get('text', '')[:200] for p in self.memory.successful_posts[-50:]]
                # Add cached timeline snippets (populated in smart_engagement)
                trend_texts += getattr(self, '_trend_timeline_snippets', [])
                # Add RSS headlines from the last fetch (populated in fetch_external_content)
                trend_texts += getattr(self, '_trend_rss_headlines', [])
                trend_topic = self.trend_radar.get_topic_of_day(trend_texts)
                if trend_topic:
                    logger.info(f"📡 Trend Radar: тема дня = {trend_topic} (из {len(trend_texts)} текстов)")
            except Exception:
                pass

            # Audience memory: boost strategy weights for top-performing topics
            if trend_topic and self.memory.topic_outcomes:
                outcomes = self.memory.topic_outcomes
                if trend_topic in outcomes and outcomes[trend_topic].get('count', 0) > 0:
                    topic_er = outcomes[trend_topic]['total_er'] / outcomes[trend_topic]['count']
                    strategies = [
                        (fn, w * (1.3 if trend_topic in (fn.__name__ if callable(fn) else '') else 1.0))
                        for fn, w in strategies
                    ]
                    logger.info(f"🧠 Audience memory: буст для темы '{trend_topic}' (avg ER={topic_er:.2f})")

            # Взвешенный выбор стратегии
            strategy = self._weighted_choice(strategies)
            post = await strategy()

            # Quality Gate с авто-регенерацией (усиленный промпт при рестарте)
            regen_count = 0
            max_regen = self.quality_gate.max_regen
            recent_texts = [p.get('text', '') for p in self.memory.successful_posts[-20:]]
            while post and hasattr(post, 'text') and post.text:
                gate_ok, gate_reason = self.quality_gate.check(post.text, recent_texts)
                if gate_ok:
                    logger.info(f"✅ Quality Gate пройден (попытка {regen_count + 1})")
                    break
                regen_count += 1
                logger.warning(f"⚠️ Quality Gate не пройден: {gate_reason} (попытка {regen_count}/{max_regen})")
                if regen_count > max_regen:
                    post = None
                    break
                # Передаём флаг "нужен усиленный промпт" через self
                self._quality_gate_regen_mode = True
                strategy = self._weighted_choice(strategies)
                post = await strategy()
                self._quality_gate_regen_mode = False
            
            if post and self._evaluate_post_quality(post):
                # Проверяем на дубликаты еще раз перед публикацией
                url = getattr(post, 'url', None) if hasattr(post, 'url') else None
                image_url = getattr(post, 'image_url', None) if hasattr(post, 'image_url') else None
                
                if self._is_duplicate_content(post.text, url, image_url):
                    logger.warning("🔄 Обнаружен дубликат перед публикацией. Создаем альтернативный контент...")
                    # Создаем fallback пост вместо пропуска
                    fallback_post = await self._create_fallback_post_for_duplicate()
                    if fallback_post and self._evaluate_post_quality(fallback_post):
                        post = fallback_post
                        url = getattr(post, 'url', None) if hasattr(post, 'url') else None
                        image_url = getattr(post, 'image_url', None) if hasattr(post, 'image_url') else None
                        logger.info("✅ Создан альтернативный пост вместо дубликата")
                    else:
                        logger.warning("⚠️ Не удалось создать альтернативный пост. Пропускаем публикацию.")
                        return
                
                # Публикуем (или dry-run)
                if self.dry_run:
                    self.dry_run_log.log('send_post', text=post.text[:120], format=getattr(self, '_last_ab_format', 'unknown'))
                    return

                created = await self.bluesky_client.send_post(
                    text=post.text,
                    facets=post.facets if post.facets else None,
                    embed=post.embed if hasattr(post, 'embed') and post.embed else None,
                    langs=post.langs if hasattr(post, 'langs') and post.langs else ['en']
                )
                self.activity_budget.spend('post')
                
                self.ab_engine.record_impression(ab_format)
                self._mark_content_as_published(post.text, url, image_url)

                self.session_stats['posts_created'] += 1
                self.daily_post_count += 1
                logger.info(f"✅ Опубликован качественный пост #{self.daily_post_count}: {post.text[:80].replace(chr(10), ' ')}...")
                
                # УЛУЧШЕННОЕ сохранение для анализа с вирусными метриками
                content_hash = self._generate_content_hash(post.text, url, image_url)
                post_data = {
                    'text': post.text,
                    'uri': created.uri,
                    'created_at': datetime.now(),
                    'timestamp': datetime.now().isoformat(),
                    'type': getattr(post, 'content_type', 'general'),
                    'quality_score': getattr(post, 'quality_score', 0.8),
                    'content_hash': content_hash,
                    'url': url,
                    'image_url': image_url,
                    'ab_format': ab_format,
                    # Вирусные метрики
                    'viral_score': getattr(post, 'viral_score', 0.0),
                    'viral_factors': getattr(post, 'viral_factors', []),
                    'predicted_engagement': 0,
                    'actual_engagement': 0
                }
                
                self.memory.successful_posts.append(post_data)
                
                # НОВОЕ: Отслеживаем потенциально вирусные посты
                if getattr(post, 'viral_score', 0.0) >= 0.6:
                    self.memory.viral_posts.append({
                        'uri': created.uri,
                        'text': post.text[:100],
                        'viral_score': getattr(post, 'viral_score', 0.0),
                        'factors': getattr(post, 'viral_factors', []),
                        'timestamp': datetime.now().isoformat(),
                        'content_type': getattr(post, 'content_type', 'general')
                    })
                    logger.info(f"🔥 Пост добавлен в список потенциально вирусных (score: {getattr(post, 'viral_score', 0.0):.2f})")
                
                # Планируем отложенный анализ производительности (1h, 6h, 24h)
                self.content_service.schedule_post_performance_checks(created.uri)
                
            else:
                logger.warning("⚠️ Пост не прошел проверку качества. Пропускаем публикацию.")
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания поста: {e}")
            self.session_stats['errors'] += 1
    
    def _spawn_background(self, coro) -> None:
        """Register a background task; auto-discard on completion."""
        if len(self._background_tasks) >= 50:
            logger.warning("Background task limit (50) reached — skipping new task")
            return
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _weighted_choice(self, strategies: List[Tuple]) -> callable:
        """Взвешенный выбор стратегии создания поста"""
        functions, weights = zip(*strategies)
        return random.choices(functions, weights=weights)[0]
    
    def _evaluate_post_quality(self, post: RichTextPost) -> bool:
        """УЛУЧШЕННАЯ оценка качества поста с анализом вирусного потенциала"""
        if not post or not post.text:
            return False
        
        # НОВОЕ: Используем улучшенный анализатор качества
        analysis = self.content_analyzer.analyze_post_potential(post.text)
        viral_score = analysis['viral_score']
        factors = analysis['factors']
        recommendations = analysis['recommendations']
        
        # Получаем настройки вирусного контента из конфигурации
        viral_settings = self.config.get('viral_content_settings', {})
        min_viral_score = viral_settings.get('min_viral_score', 0.4)
        required_triggers = viral_settings.get('required_engagement_triggers', 2)
        
        # Базовая оценка (старая система)
        basic_score = 0.0
        text_length = len(post.text)
        
        # Длина поста (оптимальная 150-280 символов для вирусности)
        if 150 <= text_length <= 280:
            basic_score += 0.3
        elif 80 <= text_length <= 150:
            basic_score += 0.2
        else:
            basic_score += 0.1
        
        # Наличие эмодзи
        emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002700-\U000027BF]', post.text))
        if emoji_count > 0:
            basic_score += 0.2
        
        # Наличие хештегов
        hashtag_count = post.text.count('#')
        if hashtag_count > 0:
            basic_score += 0.2
        elif self.require_hashtags:
            logger.warning("⚠️ Пост не содержит обязательных хештегов")
            return False
        
        # Вопросы (критично для engagement)
        if '?' in post.text:
            basic_score += 0.3  # Увеличен вес для вопросов
        
        # Объединенная оценка: 60% вирусный потенциал + 40% базовая оценка
        combined_score = (viral_score * 0.6) + (basic_score * 0.4)
        
        post.quality_score = combined_score
        post.viral_score = viral_score
        post.viral_factors = factors
        
        # Детальное логирование
        logger.info(f"📊 АНАЛИЗ КАЧЕСТВА ПОСТА:")
        logger.info(f"   🎯 Вирусный потенциал: {viral_score:.2f}/1.0")
        logger.info(f"   📈 Базовая оценка: {basic_score:.2f}/1.0")
        logger.info(f"   🔥 Итоговая оценка: {combined_score:.2f}/1.0")
        logger.info(f"   ✅ Факторы вирусности: {', '.join(factors) if factors else 'Нет'}")
        
        if recommendations:
            logger.info(f"   💡 Рекомендации:")
            for rec in recommendations[:3]:  # Показываем только первые 3
                logger.info(f"     • {rec}")
        
        # Проверяем соответствие требованиям
        meets_viral_threshold = viral_score >= min_viral_score
        meets_basic_threshold = combined_score >= self.min_post_quality_score
        has_enough_triggers = len(factors) >= required_triggers
        
        logger.info(f"   🎪 Проверки:")
        logger.info(f"     Вирусный порог ({min_viral_score}): {'✅' if meets_viral_threshold else '❌'}")
        logger.info(f"     Базовый порог ({self.min_post_quality_score}): {'✅' if meets_basic_threshold else '❌'}")
        logger.info(f"     Триггеры engagement ({required_triggers}): {'✅' if has_enough_triggers else '❌'}")
        
        # Пост проходит если соответствует всем критериям
        passed = meets_viral_threshold and meets_basic_threshold and has_enough_triggers
        
        if not passed:
            logger.warning(f"⚠️ Пост не прошел проверку качества (viral: {viral_score:.2f}, combined: {combined_score:.2f}, triggers: {len(factors)})")
        
        return passed
    
    async def _create_quality_news_post(self) -> Optional[RichTextPost]:
        """Создает качественный новостной пост с изображением"""
        try:
            # ПРИНУДИТЕЛЬНО получаем свежие новости из RSS
            logger.info("🌐 Активация RSS-фидов для новостного поста...")
            news_content = await self.fetch_external_content()
            
            if not news_content:
                logger.warning("⚠️ RSS-фиды не вернули новости, проверяем источники...")
                # Логируем состояние RSS источников
                logger.info(f"📋 Доступно RSS источников: {len(self.rss_feeds)}")
                for i, feed_url in enumerate(self.rss_feeds[:5]):
                    source_name = feed_url.split('//')[-1].split('/')[0]
                    logger.info(f"   {i+1}. {source_name}")
                return await self._create_personal_opinion_post()
            
            # Выбираем самую интересную новость, которая еще не была опубликована
            selected_news = None
            for news in news_content[:10]:  # Проверяем топ-10 для большего выбора
                if len(news.get('title', '')) > 20 and news.get('description'):
                    # Проверяем на дубликаты
                    url = news.get('url', '')
                    image_url = news.get('image_url', '')
                    
                    if not self._is_duplicate_content("", url, image_url):
                        selected_news = news
                        logger.info(f"✅ Выбрана уникальная новость: {news['title'][:50]}...")
                        break
                    else:
                        logger.info(f"🔄 Пропускаем дубликат новости: {news['title'][:50]}...")
            
            if not selected_news:
                logger.warning("⚠️ Все новости уже были опубликованы или не подходят")
                logger.info("🔄 Переключаемся на альтернативный контент вместо новостей")
                return await self._create_personal_opinion_post()
            
            # Создаем персональный комментарий к новости
            personal_takes = [
                "Interesting turn! 🤔",
                "Didn't expect this development",
                "This changes a lot in the industry",
                "Wow, what news! 🔥",
                "Curious times...",
                "Worth taking a closer look",
                "Classic! Just as I thought 😏"
            ]
            
            personal_comment = random.choice(personal_takes)
            
            # Генерируем человечный пост с динамическими хештегами
            prompt = f"""
            Create a personal social media post about this news: "{selected_news['title']}"
            Start with the personal comment: "{personal_comment}"
            
            Provide the output in JSON format with "post_text" (in English, 150-200 chars, retell the news briefly in your own words, add a natural ending - it can be a question, observation, emoji, or statement) and "hashtags" (in English, 2-3 relevant tags).

            Examples:
            {{
              "post_text": "Interesting turn! 🤔 OpenAI just released a new model with revolutionary capabilities. This could change everything.",
              "hashtags": "#news #AI #technology"
            }}
            {{
              "post_text": "Classic! 🙄 Another tech CEO promises to revolutionize everything. We'll see...",
              "hashtags": "#tech #startup #news"
            }}
            {{
              "post_text": "Wow! New research shows AI can predict weather patterns 10x better than before 🌩️",
              "hashtags": "#science #AI #weather"
            }}
            """
            
            structured_content = await self.generate_structured_post_content(prompt, model_key='creative')
            
            # Обрабатываем структурированный ответ
            if structured_content:
                post_text = structured_content.get('post_text', '')
                hashtags = structured_content.get('hashtags', '#новости #технологии')
                
                # Объединяем текст и хештеги
                final_content = f"{post_text}\n\n{hashtags}"
                
                post = self.formatter.create_post(final_content, content_type='news')
                
                # Создаем пост с карточкой ссылки и изображением
                if selected_news.get('image_url'):
                    try:
                        # Используем новый метод для создания поста с изображением
                        enhanced_post = await self.create_post_with_link_preview(
                            final_content,
                            selected_news.get('url', ''),
                            selected_news['title'],
                            selected_news.get('description', ''),
                            selected_news['image_url']
                        )
                        if enhanced_post:
                            logger.info("✅ Создан пост с изображением и карточкой ссылки")
                            return enhanced_post
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось создать пост с изображением: {e}")
                
                # Fallback - добавляем URL и image_url к обычному посту
                post.url = selected_news.get('url', '')
                post.image_url = selected_news.get('image_url', '')
                return post
            
            # Fallback - создаем простой человечный пост
            return await self._create_personal_opinion_post()
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания новостного поста: {e}")
            return await self._create_personal_opinion_post()
    
    async def _create_personal_opinion_post(self) -> RichTextPost:
        """Создает пост с личным мнением используя динамическую систему"""
        try:
            # Генерируем динамический контент
            dynamic_content = await self.dynamic_generator.generate_dynamic_content()
            
            async def content_creator():
                return {
                    "post_text": dynamic_content["post_text"],
                    "hashtags": dynamic_content["hashtags"]
                }

            async def fallback_creator():
                fallback = self.dynamic_generator._generate_fallback_content()
                return {
                    "post_text": fallback["post_text"], 
                    "hashtags": fallback["hashtags"]
                }

            return await self._create_post_with_image_generation(
                content_creator,
                dynamic_content.get("topic", "personal thoughts"),
                dynamic_content.get("content_type", "personal"),
                fallback_creator
            )
            
        except Exception as e:
            logger.error(f"❌ Error in dynamic personal opinion post: {e}")
            return await self._create_emergency_unique_post()
    
    async def _create_quality_ai_insight(self) -> RichTextPost:
        """Создает пост об AI с динамическими хештегами и изображением"""
        ai_aspects = [
            "использование AI в повседневной работе",
            "изменения в подходах к программированию",
            "взаимодействие человека и машины",
            "эволюция творческих процессов",
            "влияние на профессиональные навыки"
        ]
        selected_aspect = random.choice(ai_aspects)
        
        async def content_creator():
            ai_prompt = f"""
            Create a thoughtful social media post about "{selected_aspect}".
            Provide the output in JSON format with two keys: "post_text" (in English, 180-220 characters, personal and engaging - can end with a question, statement, observation, or emoji) and "hashtags" (in English, 3-4 relevant tags, starting with #).

            Examples:
            {{
              "post_text": "AI assistants are changing how I approach coding. I'm definitely becoming more efficient, not sure about creativity yet 🤔",
              "hashtags": "#AI #coding #futureofwork #thoughts"
            }}
            {{
              "post_text": "Been using AI for brainstorming lately. It's like having a tireless creative partner that never judges your weird ideas ✨",
              "hashtags": "#AI #creativity #productivity #tools"
            }}
            {{
              "post_text": "The human-AI collaboration feels so natural now. We're not replacing humans, we're augmenting them. That's the real revolution.",
              "hashtags": "#AI #future #collaboration #tech"
            }}
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='powerful')

        async def fallback_creator():
            current_time = datetime.now().strftime("%H:%M")
            fallback_options = [
                {
                    "post_text": f"🤖 AI thoughts ({current_time}):\n\nArtificial intelligence is reshaping our work. The possibilities are endless! ✨",
                    "hashtags": "#AI #future #technology"
                },
                {
                    "post_text": f"💭 Tech reflection ({current_time}):\n\nEvery tool we use shapes how we think. AI is no exception.",
                    "hashtags": "#AI #productivity #mindset"
                },
                {
                    "post_text": f"🔬 Daily observation ({current_time}):\n\nWatching AI evolve is like witnessing the birth of a new species.",
                    "hashtags": "#AI #evolution #technology"
                }
            ]
            return random.choice(fallback_options)

        return await self._create_post_with_image_generation(
            content_creator,
            selected_aspect,
            'ai',
            fallback_creator
        )
    
    async def _create_quality_tip_post(self) -> RichTextPost:
        """Создает пост-совет используя динамическую систему"""
        try:
            # Генерируем контент с фокусом на советы
            dynamic_content = await self.dynamic_generator.generate_dynamic_content("tip_sharing")
            
            async def content_creator():
                return {
                    "post_text": dynamic_content["post_text"],
                    "hashtags": dynamic_content["hashtags"]
                }

            async def fallback_creator():
                fallback = self.dynamic_generator._generate_fallback_content()
                return {
                    "post_text": fallback["post_text"],
                    "hashtags": fallback["hashtags"]
                }

            return await self._create_post_with_image_generation(
                content_creator,
                dynamic_content.get("topic", "useful tips"),
                dynamic_content.get("content_type", "tip"),
                fallback_creator
            )
            
        except Exception as e:
            logger.error(f"❌ Error in dynamic tip post: {e}")
            return await self._create_emergency_unique_post()
    
    async def _create_quality_list_post(self) -> RichTextPost:
        """ОТРЕФАКТОРЕНО: Создает пост-список используя единый паттерн с изображением"""
        list_themes = [
            "полезные инструменты для разработчиков",
            "тренды в программировании", 
            "книги для IT-специалистов",
            "лайфхаки продуктивности",
            "ресурсы для изучения технологий",
            "ошибки начинающих программистов",
            "принципы хорошего кода",
            "навыки для карьерного роста",
            "языки программирования для изучения",
            "инструменты командной работы"
        ]
        selected_theme = random.choice(list_themes)
        
        async def content_creator():
            ai_prompt = f"""
            Create a social media post based on the list idea: "{selected_theme}".
            Provide the output in JSON format. The "post_text" (in English, max 280 chars) should have a title, a short numbered list, and a natural ending (statement, emoji, question, or observation). The "hashtags" (in English) should be 3-4 relevant tags.

            Examples for "useful dev tools":
            {{
              "post_text": "🔥 TOP-3 tools for code\\n\\n1️⃣ VS Code - best editor\\n2️⃣ Git - version control\\n3️⃣ Postman - API testing\\n\\nGame changers for productivity! 🚀",
              "hashtags": "#tools #development #useful #coding"
            }}
            {{
              "post_text": "📚 Must-read books for developers:\\n\\n1️⃣ Clean Code\\n2️⃣ Design Patterns\\n3️⃣ Pragmatic Programmer\\n\\nClassics never get old ✨",
              "hashtags": "#books #learning #development #career"
            }}
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='creative')

        async def fallback_creator():
            current_time = datetime.now().strftime("%H:%M")
            fallback_options = [
                {
                    "post_text": f"📋 Daily developer routine ({current_time}):\\n\\n1. Write code\\n2. Drink coffee\\n3. Debug\\n4. Repeat\\n\\nThe eternal cycle! ☕",
                    "hashtags": "#list #productivity #dev #coding"
                },
                {
                    "post_text": f"🔧 Essential tools ({current_time}):\\n\\n1. Good IDE\\n2. Version control\\n3. Stack Overflow\\n\\nBasics that never fail 💪",
                    "hashtags": "#tools #development #basics #tech"
                },
                {
                    "post_text": f"💡 Simple truths ({current_time}):\\n\\n1. Code works mysteriously\\n2. Bugs appear from nowhere\\n3. Coffee fixes everything\\n\\nSoftware development reality 😅",
                    "hashtags": "#humor #coding #life #truth"
                }
            ]
            return random.choice(fallback_options)

        return await self._create_post_with_image_generation(
            content_creator,
            selected_theme,
            'list',
            fallback_creator
        )
    
    async def _create_quality_poll_post(self) -> RichTextPost:
        """Создает пост-опрос с динамическими хештегами и изображением"""
        poll_topics = [
            ("tabs vs spaces", ["Табы", "Пробелы"]),
            ("light vs dark theme", ["Светлая тема", "Темная тема"]),
            ("framework choice: React vs Vue", ["React", "Vue"]),
            ("preferred OS: Windows vs Linux", ["Windows", "Linux"])
        ]
        selected_topic, poll_options = random.choice(poll_topics)

        async def content_creator():
            ai_prompt = f"""
            Create a poll post about "{selected_topic}".
            Provide the output in JSON format. "post_text" (in English, ~150 chars) should introduce the poll. "hashtags" should be 3-4 relevant tags. The poll options will be added separately.

            Example for "tabs vs spaces":
            {{
              "post_text": "Вечный бой, который не утихает... Что выбираете вы для форматирования кода? Голосуйте! 💻",
              "hashtags": "#холивар #код #программирование #опрос"
            }}
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='creative')
        
        # Для опросов fallback не так важен, т.к. основной контент - сам опрос.
        # Но создадим его для консистентности.
        async def fallback_creator():
            return {
                "post_text": "Время для вашего мнения! Что вы думаете по этому поводу?",
                "hashtags": "#опрос #мнение #IT"
            }

        # Эта обертка не поддерживает опросы, поэтому логика будет немного другой.
        structured_content = await content_creator()
        if not structured_content:
            structured_content = await fallback_creator()

        post_text = structured_content.get('post_text', '')
        hashtags = structured_content.get('hashtags', '')
        final_post_text = f"{post_text}\n\n{hashtags}".strip()

        logger.info(f"📊 Создание опроса на тему: {selected_topic}")
        # Используем formatter напрямую для создания опроса
        return self.formatter.create_poll(
            question=final_post_text,
            options=poll_options,
            duration_hours=24,
            content_type='poll'
        )
    
    async def _create_quality_discussion(self) -> RichTextPost:
        """Создает пост для дискуссии используя динамическую систему"""
        try:
            # Генерируем контент с фокусом на вопросы и наблюдения
            import random
            content_type = "question_starter" if random.random() < 0.3 else "observation"  # Снижаем долю вопросов с 60% до 30%
            dynamic_content = await self.dynamic_generator.generate_dynamic_content(content_type)
            
            async def content_creator():
                return {
                    "post_text": dynamic_content["post_text"],
                    "hashtags": dynamic_content["hashtags"]
                }

            async def fallback_creator():
                fallback = self.dynamic_generator._generate_fallback_content()
                return {
                    "post_text": fallback["post_text"],
                    "hashtags": fallback["hashtags"]
                }

            return await self._create_post_with_image_generation(
                content_creator,
                dynamic_content.get("topic", "discussion topic"),
                dynamic_content.get("content_type", "discussion"),
                fallback_creator
            )
            
        except Exception as e:
            logger.error(f"❌ Error in dynamic discussion post: {e}")
            return await self._create_emergency_unique_post()
    
    # НОВЫЕ МЕТОДЫ ДЛЯ ВИРУСНОГО КОНТЕНТА
    
    async def _create_viral_hot_take(self) -> RichTextPost:
        """Создает вирусное горячее мнение с высоким engagement потенциалом"""
        hot_take_topics = [
            "AI replacing developers is overhyped",
            "Remote work is killing innovation", 
            "Most startups fail because of ego, not market",
            "College degrees are becoming irrelevant in tech",
            "Open source is not sustainable long-term",
            "Crypto is just gambling with extra steps",
            "Social media algorithms are destroying creativity",
            "The metaverse was a $100B mistake"
        ]
        
        selected_topic = random.choice(hot_take_topics)
        
        async def content_creator():
            viral_prompts = self.engagement_optimizer.generate_viral_post_prompts()
            ai_prompt = f"""
            Create a controversial but thoughtful hot take about: "{selected_topic}"
            
            Requirements:
            - Be provocative but not offensive
            - Include surprising statistics or facts
            - Add personal experience or industry insight
            - End with a question to encourage debate
            - Use emotional language strategically
            - 180-250 characters max
            - Include 3-4 relevant hashtags
            
            Format as JSON: {{"post_text": "...", "hashtags": "..."}}
            
            Example style: "Unpopular opinion: {selected_topic}. After 10 years in the industry, I've seen this pattern destroy more companies than market crashes. Here's why... What's your take? 🔥"
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='powerful')

        async def fallback_creator():
            return {
                "post_text": f"🔥 Hot take: {selected_topic}. Change my mind! What's your experience?",
                "hashtags": "#hottake #controversial #tech #opinion"
            }

        return await self._create_post_with_image_generation(
            content_creator,
            f"controversial opinion about {selected_topic}",
            'viral_hot_take',
            fallback_creator
        )
    
    async def _create_trending_commentary(self) -> RichTextPost:
        """Создает комментарий к актуальным трендам с уникальным углом"""
        trending_themes = [
            "latest AI breakthrough", "tech layoffs", "startup funding news",
            "new programming language", "security breach", "platform changes",
            "industry controversy", "major acquisition", "economic changes",
            "regulatory changes in tech"
        ]
        
        selected_theme = random.choice(trending_themes)
        
        async def content_creator():
            ai_prompt = f"""
            Create a trending commentary post about: "{selected_theme}"
            
            Requirements:
            - Provide unique insider perspective nobody else is discussing
            - Connect to broader implications
            - Include surprising context or background
            - Make bold prediction about consequences
            - Ask provocative question
            - 200-280 characters
            - Use urgent, newsy language
            
            Format as JSON: {{"post_text": "...", "hashtags": "..."}}
            
            Style: "Everyone's talking about {selected_theme}, but here's what they're missing... [unique insight] This will change everything. Mark my words. What do you think happens next? 👀"
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='powerful')

        async def fallback_creator():
            return {
                "post_text": f"📰 Breaking: {selected_theme} is trending. Here's my take on what this really means for the industry... Thoughts?",
                "hashtags": "#breaking #tech #analysis #trends"
            }

        return await self._create_post_with_image_generation(
            content_creator,
            f"trending news commentary about {selected_theme}",
            'trending_commentary',
            fallback_creator
        )
    
    async def _create_personal_insight(self) -> RichTextPost:
        """Создает пост с личным инсайтом или опытом"""
        insight_areas = [
            "biggest career mistake", "counterintuitive business lesson",
            "overlooked skill for success", "industry secret nobody talks about",
            "expensive lesson learned", "myth everyone believes",
            "pattern in successful people", "red flag in startups",
            "undervalued technology", "overrated trend"
        ]
        
        selected_area = random.choice(insight_areas)
        
        async def content_creator():
            ai_prompt = f"""
            Create a personal insight post about: "{selected_area}"
            
            Requirements:
            - Share authentic personal experience or observation
            - Include specific example or story
            - Provide actionable takeaway
            - Use vulnerable, honest tone
            - End with relatable question
            - 220-280 characters
            - Feel authentic and human
            
            Format as JSON: {{"post_text": "...", "hashtags": "..."}}
            
            Style: "After [X years/experience], I learned that {selected_area} is... [personal story/insight]. Wish someone told me this earlier. Anyone else experienced this? 💭"
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='creative')

        async def fallback_creator():
            return {
                "post_text": f"💭 Personal insight: {selected_area} taught me more about business than any book. Here's what I learned... What's your experience?",
                "hashtags": "#insight #experience #lessons #personal"
            }

        return await self._create_post_with_image_generation(
            content_creator,
            f"personal insight about {selected_area}",
            'personal_insight',
            fallback_creator
        )
    
    async def _create_prediction_post(self) -> RichTextPost:
        """Создает пост с смелым прогнозом"""
        prediction_areas = [
            "AI development in 2025", "remote work evolution",
            "crypto market direction", "tech industry consolidation",
            "programming languages future", "startup ecosystem changes",
            "social media platform wars", "economic tech impact",
            "cybersecurity threats", "developer tools evolution"
        ]
        
        selected_area = random.choice(prediction_areas)
        
        async def content_creator():
            ai_prompt = f"""
            Create a bold prediction post about: "{selected_area}"
            
            Requirements:
            - Make specific, bold prediction
            - Provide reasoning and evidence
            - Set timeline (6 months, 1 year, 2 years)
            - Include potential consequences
            - Ask for counter-arguments
            - 250-280 characters
            - Use confident, analytical tone
            
            Format as JSON: {{"post_text": "...", "hashtags": "..."}}
            
            Style: "Prediction: By [timeline], {selected_area} will... [specific prediction]. Here's why: [reasoning]. This means [consequences]. Prove me wrong! 🔮"
            """
            return await self.generate_structured_post_content(ai_prompt, model_key='powerful')

        async def fallback_creator():
            return {
                "post_text": f"🔮 Bold prediction: {selected_area} will surprise everyone in 2025. Here's my reasoning... What do you think?",
                "hashtags": "#prediction #future #tech #analysis"
            }

        return await self._create_post_with_image_generation(
            content_creator,
            f"future prediction about {selected_area}",
            'prediction',
            fallback_creator
        )
    
    async def create_manual_thread(self, topic: str) -> None:
        """Создание thread только по специальному запросу (НЕ автоматически)"""
        logger.info(f"📝 РУЧНОЕ создание thread на тему: {topic}")
        
        prompt = f"""
        Создай подробный анализ на тему "{topic}" для thread в социальной сети.
        
        Структура:
        - Введение с хуком (50-80 символов)
        - 3-4 ключевых пункта (по 100-150 символов каждый)
        - Заключение с вопросом к аудитории (80-120 символов)
        
        Требования:
        - Каждая часть должна быть интересной отдельно
        - Используй эмодзи для структурирования
        - Добавь релевантные хештеги
        - In English
        - Общий объем: 600-800 символов
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
                        {"role": "system", "content": "Ты дружелюбный пользователь социальных сетей. Пиши короткие позитивные комментарии in English с эмодзи. Максимум 80 символов."},
                        {"role": "user", "content": f"Прокомментируй этот пост: {post_text[:200]}"}
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
        """УЛУЧШЕННОЕ получение контента из внешних источников с ротацией и аналитикой"""
        all_entries = []
        
        # Используем ПОЛНЫЙ список RSS источников с ротацией
        available_sources = self.rss_feeds.copy()
        random.shuffle(available_sources)  # Ротация для разнообразия
        
        sources_used = 0
        max_sources = 6  # Увеличиваем количество источников
        target_entries = 15  # Целевое количество записей
        
        logger.info(f"🌐 Начинаем получение RSS из {len(available_sources)} доступных источников...")
        
        for feed_url in available_sources:
            if sources_used >= max_sources or len(all_entries) >= target_entries:
                break
                
            try:
                # Адаптивный таймаут на основе истории
                timeout = 20 if 'cnn.com' in feed_url else 15
                
                start_time = datetime.now()
                
                # Используем единую HTTP сессию бота
                if not self.http_session:
                    self.http_session = aiohttp.ClientSession()
                
                async with self.http_session.get(feed_url, timeout=timeout) as response:
                    if response.status != 200:
                        logger.warning(f"⚠️ {feed_url}: HTTP {response.status}")
                        continue

                    content = await response.text()
                    feed = feedparser.parse(content)
                    
                    fetch_time = (datetime.now() - start_time).total_seconds()
                    
                    # Ограичиваем записи для разнообразия (было 3, стало 4)
                    entries_to_process = 4
                    source_entries = []
                    
                    for entry in feed.entries[:entries_to_process]:
                        entry_data = {
                            'title': self.clean_html(entry.title),
                            'url': entry.link,
                            'description': self.clean_html(entry.get('summary', '')[:250]),
                            'source': self.clean_html(feed.feed.title) if hasattr(feed.feed, 'title') else 'Unknown',
                            'published': entry.get('published', ''),
                            'fetch_time': fetch_time,
                            'source_url': feed_url,
                            'image_url': None,
                            'priority_score': 0
                        }
                        
                        # УЛУЧШЕННЫЙ поиск изображений
                        image_url = self._enhanced_image_extraction(entry)
                        entry_data['image_url'] = image_url
                        
                        # Расчет приоритета записи
                        entry_data['priority_score'] = self._calculate_entry_priority(entry_data, feed_url)
                        
                        # Фильтруем только качественные записи
                        if len(entry_data['title']) > 20 and entry_data['title'] != 'Unknown':
                            source_entries.append(entry_data)
                    
                    if source_entries:
                        all_entries.extend(source_entries)
                        sources_used += 1

                        source_name = feed.feed.title if hasattr(feed.feed, 'title') else feed_url.split('//')[-1].split('/')[0]
                        logger.info(f"✅ {source_name}: {len(source_entries)} записей за {fetch_time:.1f}с")
                        # RSS Source Intelligence: record success
                        try:
                            self.rss_manager.record_fetch(
                                feed_url,
                                success=True,
                                latency=fetch_time,
                                entries=len(source_entries),
                                duplicates=entries_to_process - len(source_entries),
                            )
                        except Exception:
                            pass
                    else:
                        try:
                            self.rss_manager.record_fetch(feed_url, success=False, latency=fetch_time)
                        except Exception:
                            pass

                    # Пауза между источниками для вежливости
                    await asyncio.sleep(0.3)

            except asyncio.TimeoutError:
                source_name = feed_url.split('//')[-1].split('/')[0]
                logger.warning(f"⏰ {source_name}: таймаут ({timeout}с)")
                try:
                    self.rss_manager.record_fetch(feed_url, success=False, latency=float(timeout))
                except Exception:
                    pass
                continue
            except Exception as e:
                source_name = feed_url.split('//')[-1].split('/')[0]
                logger.warning(f"❌ {source_name}: {str(e)[:80]}...")
                try:
                    self.rss_manager.record_fetch(feed_url, success=False, latency=0.0)
                except Exception:
                    pass
                continue
        
        # Удаляем дубликаты и сортируем по приоритету
        unique_entries = self._deduplicate_rss_entries(all_entries)
        prioritized_entries = sorted(unique_entries, key=lambda x: x.get('priority_score', 0), reverse=True)
        
        # Аналитика
        with_images = sum(1 for e in prioritized_entries if e.get('image_url'))
        avg_fetch_time = sum(e.get('fetch_time', 0) for e in prioritized_entries) / len(prioritized_entries) if prioritized_entries else 0
        
        logger.info(f"📊 RSS аналитика:")
        logger.info(f"   🌐 Обработано источников: {sources_used}/{len(available_sources)}")
        logger.info(f"   📰 Всего записей: {len(all_entries)} → уникальных: {len(unique_entries)}")
        logger.info(f"   🖼️ С изображениями: {with_images}/{len(prioritized_entries)}")
        logger.info(f"   ⚡ Среднее время загрузки: {avg_fetch_time:.1f}с")
        
        # Возвращаем топ записи
        final_entries = prioritized_entries[:10]
        logger.info(f"📋 Выбрано {len(final_entries)} лучших записей для использования")

        # Trend Radar feed: save RSS headlines for topic-of-day detection
        self._trend_rss_headlines = [e.get('title', '') for e in prioritized_entries[:30]]

        return final_entries
    
    def _enhanced_image_extraction(self, entry) -> Optional[str]:
        """Улучшенный поиск изображений в RSS записи"""
        # 1. Media thumbnail (наиболее надежный)
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            return entry.media_thumbnail[0].get('url')
        
        # 2. Enclosures
        if hasattr(entry, 'enclosures'):
            for enclosure in entry.enclosures:
                if enclosure.get('type', '').startswith('image/'):
                    return enclosure.get('href')
                                
        # 3. Media content
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('type', '').startswith('image/'):
                    return media.get('url')
        
        # 4. Поиск в content/summary с улучшенным regex
        content_fields = []
        if hasattr(entry, 'content'):
            content_fields.extend([c.get('value', '') for c in entry.content])
        if hasattr(entry, 'summary'):
            content_fields.append(entry.summary)
        
        for content in content_fields:
            # Ищем img теги (различные варианты кавычек)
            img_patterns = [
                r'<img[^>]+src=["\']([^"\']+)["\']',
                r'<img[^>]+src=([^>\s]+)',
                r'data-src=["\']([^"\']+)["\']'  # Lazy loading images
            ]
            
            for pattern in img_patterns:
                img_match = re.search(pattern, content)
                if img_match:
                    return img_match.group(1)
                                
        # 5. Links с типом изображения
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('image/'):
                    return link.get('href')
        
        return None
    
    def _calculate_entry_priority(self, entry_data: Dict, source_url: str) -> float:
        """Расчет приоритета записи для ранжирования"""
        score = 0.0
        
        # Базовый балл по источнику
        if 'venturebeat.com' in source_url or 'techcrunch.com' in source_url:
            score += 0.25  # AI и tech новости
        elif 'ycombinator.com' in source_url or 'reddit.com' in source_url:
            score += 0.2  # Сообщество разработчиков
        else:
            score += 0.15  # Остальные источники
        
        # Бонус за изображение
        if entry_data.get('image_url'):
            score += 0.2
        
        # Бонус за качество заголовка
        title_len = len(entry_data.get('title', ''))
        if 40 <= title_len <= 120:
            score += 0.15  # Оптимальная длина
        elif title_len > 120:
            score += 0.05  # Слишком длинный
        
        # Бонус за описание
        desc_len = len(entry_data.get('description', ''))
        if desc_len > 80:
            score += 0.1
        
        # Бонус за актуальность (если есть дата)
        if entry_data.get('published'):
            try:
                # Простая проверка на свежесть (в течение недели)
                import time
                published_time = time.mktime(time.strptime(entry_data['published'][:25], '%a, %d %b %Y %H:%M:%S'))
                age_hours = (time.time() - published_time) / 3600
                if age_hours < 24:
                    score += 0.1  # Свежие новости
                elif age_hours < 168:  # неделя
                    score += 0.05
            except:
                pass  # Игнорируем ошибки парсинга даты
        
        # Штраф за быструю загрузку (может быть проблемный источник)
        fetch_time = entry_data.get('fetch_time', 1)
        if fetch_time > 3:
            score *= 0.9  # Небольшой штраф за медленные источники
        
        return round(score, 3)
    
    def _deduplicate_rss_entries(self, entries: List[Dict]) -> List[Dict]:
        """Удаление дубликатов RSS записей по URL и схожести заголовков"""
        seen_urls = set()
        seen_titles = set()
        unique_entries = []
        
        for entry in entries:
            url = entry.get('url', '')
            title = entry.get('title', '').lower().strip()
            
            # Проверяем URL
            if url and url in seen_urls:
                logger.debug(f"🔄 Дубликат URL: {url[:50]}...")
                continue
            
            # Проверяем схожесть заголовков
            title_words = set(title.split())
            is_similar = False
            
            for seen_title in seen_titles:
                seen_words = set(seen_title.split())
                if title_words and seen_words:
                    # Коэффициент Жаккара для схожести
                    intersection = len(title_words.intersection(seen_words))
                    union = len(title_words.union(seen_words))
                    similarity = intersection / union if union > 0 else 0
                    
                    if similarity > 0.65:  # 65% схожести считается дубликатом
                        is_similar = True
                        logger.debug(f"🔄 Похожий заголовок: {title[:50]}... (схожесть: {similarity:.2f})")
                        break
            
            if not is_similar and title:
                unique_entries.append(entry)
                seen_urls.add(url)
                seen_titles.add(title)
        
        return unique_entries
    
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
        """УЛУЧШЕННОЕ умное взаимодействие с репостами и комментариями"""
        try:
            page_limit = int(self.config.get('engagement_settings', {}).get('timeline_page_limit', 100))
            max_pages = int(self.config.get('engagement_settings', {}).get('timeline_pages', 3))
            page_limit = max(20, min(page_limit, 100))
            max_pages = max(1, min(max_pages, 5))

            # Собираем несколько страниц ленты, чтобы анализировать больше кандидатов.
            feed_items = []
            cursor = None
            for _ in range(max_pages):
                timeline_page = await self.bluesky_client.get_timeline(limit=page_limit, cursor=cursor)
                page_feed = getattr(timeline_page, 'feed', []) or []
                feed_items.extend(page_feed)
                cursor = getattr(timeline_page, 'cursor', None)
                if not cursor or not page_feed:
                    break
            interactions = 0
            posts_analyzed = 0
            high_relevance_posts = 0
            reposts_made = 0
            comments_made = 0
            
            # Получаем настройки взаимодействия
            engagement_settings = self.config.get('engagement_settings', {})
            rel_settings = self.config.get('relevance_settings', {})
            static_repost_threshold = engagement_settings.get('repost_threshold', 0.40)
            comment_threshold = engagement_settings.get('comment_threshold', 0.65)
            repost_probability = engagement_settings.get('repost_probability', 0.30)
            comment_probability = engagement_settings.get('comment_probability', 0)
            max_reposts = engagement_settings.get('max_reposts_per_cycle', 2)
            max_comments = engagement_settings.get('max_comments_per_cycle', 0)
            like_threshold = rel_settings.get('like_threshold', 0.20)

            threshold_mode = engagement_settings.get('repost_threshold_mode', 'fixed')
            quantile_p = engagement_settings.get('repost_quantile', 0.85)
            min_threshold = engagement_settings.get('repost_min_threshold', 0.35)
            fallback_min_posts = engagement_settings.get('repost_fallback_min_posts', 30)

            logger.info(f"📰 Получено {len(feed_items)} постов для анализа (страниц: {max_pages}, limit/page: {page_limit})")

            # --- Фаза 1: score по всем постам + собираем сигналы для Trend Radar ---
            scored_posts = []
            trend_snippets = []
            my_did = getattr(self.bluesky_client.me, 'did', None) if hasattr(self.bluesky_client, 'me') and self.bluesky_client.me else None
            for post in feed_items:
                if not hasattr(post.post.record, 'text'):
                    continue
                author_did = getattr(post.post.author, 'did', None)
                if not author_did or (my_did and author_did == my_did):
                    continue
                text = post.post.record.text
                trend_snippets.append(text[:200])
                score = self.calculate_relevance(text.lower(), post)
                scored_posts.append((post, text, author_did, score))
            # Cache snippets for Trend Radar
            self._trend_timeline_snippets = trend_snippets[:100]
            posts_analyzed = len(scored_posts)

            # --- Фаза 2: динамический порог ---
            all_scores = [s for _, _, _, s in scored_posts]
            if threshold_mode == 'dynamic_quantile' and len(all_scores) >= fallback_min_posts:
                sorted_scores = sorted(all_scores)
                idx = int(len(sorted_scores) * quantile_p)
                idx = min(idx, len(sorted_scores) - 1)
                repost_threshold = max(min_threshold, sorted_scores[idx])
                logger.info(f"🎲 Динамический порог репоста: P{int(quantile_p*100)}={sorted_scores[idx]:.2f} -> threshold={repost_threshold:.2f} (min={min_threshold})")
            else:
                repost_threshold = static_repost_threshold
                logger.info(f"🎯 Фиксированный порог репоста: {repost_threshold:.2f} (постов {len(all_scores)} < {fallback_min_posts} или mode=fixed)")

            if max_reposts == 0:
                logger.info("🚫 Репосты ПОЛНОСТЬЮ ОТКЛЮЧЕНЫ (max_reposts=0)")

            score_dist = {'0.0-0.1': 0, '0.1-0.2': 0, '0.2-0.3': 0, '0.3-0.4': 0, '0.4-0.5': 0, '0.5+': 0}
            for s in all_scores:
                if s < 0.1: score_dist['0.0-0.1'] += 1
                elif s < 0.2: score_dist['0.1-0.2'] += 1
                elif s < 0.3: score_dist['0.2-0.3'] += 1
                elif s < 0.3: score_dist['0.3-0.4'] += 1
                elif s < 0.4: score_dist['0.3-0.4'] += 1
                elif s < 0.5: score_dist['0.4-0.5'] += 1
                else: score_dist['0.5+'] += 1
            logger.info(f"📊 Распределение score: {score_dist}")

            # --- Фаза 3: действия по отсортированным постам ---
            scored_posts.sort(key=lambda x: x[3], reverse=True)

            for post, text, author_did, relevance_score in scored_posts:
                if interactions >= self.max_interactions_per_cycle:
                    break

                author_handle = getattr(post.post.author, 'handle', 'unknown')
                logger.info(f"🔍 @{author_handle}: score={relevance_score:.2f} | {text[:80]}{'...' if len(text) > 80 else ''}")

                if relevance_score < like_threshold:
                    continue

                high_relevance_posts += 1

                try:
                    liked = await self.engagement_service.like(
                        uri=post.post.uri,
                        cid=post.post.cid,
                        score=relevance_score,
                        author_did=author_did,
                        author_handle=author_handle,
                    )
                    if liked:
                        interactions += 1
                        logger.info("❤️ Лайк поставлен!")
                        await asyncio.sleep(random.uniform(3, 7))

                    if (relevance_score >= repost_threshold and
                            reposts_made < max_reposts and
                            random.random() < repost_probability and
                            post.post.uri not in self.reposted_posts):
                        post_created = None
                        try:
                            raw_ts = getattr(post.post.record, 'created_at', None)
                            if raw_ts:
                                post_created = datetime.fromisoformat(str(raw_ts).replace('Z', '+00:00')).replace(tzinfo=None)
                        except Exception:
                            pass
                        policy_ok, policy_reason = self.repost_policy.check(
                            text, author_did, post_created, self.recent_repost_authors)
                        if policy_ok:
                            reposted = await self.engagement_service.repost(
                                uri=post.post.uri,
                                cid=post.post.cid,
                                score=relevance_score,
                                author_did=author_did,
                            )
                            if reposted:
                                reposts_made += 1
                                logger.info(f"🔄 Репост выполнен! (score={relevance_score:.2f}, #{reposts_made}/{max_reposts})")
                                await asyncio.sleep(random.uniform(5, 10))
                        else:
                            logger.info(f"🛡️ Репост заблокирован policy: {policy_reason}")

                    if author_did:
                        self.update_user_relationship(author_did, 'engagement', relevance_score)

                except Exception as e:
                    logger.error(f"Ошибка взаимодействия: {e}")

                await asyncio.sleep(random.uniform(5, 12))
            
            # РАСШИРЕННАЯ статистика
            logger.info(f"📊 Итого проанализировано: {posts_analyzed} постов")
            logger.info(f"🎯 Высокая релевантность: {high_relevance_posts} постов")
            logger.info(f"❤️ Лайков поставлено: {self.session_stats['likes_given']}")
            logger.info(f"🔄 Репостов сделано: {reposts_made}")
            if BLUESKY_COMPLIANT_MODE and NO_AUTO_COMMENTS:
                logger.info(f"💬 Комментарии: ОТКЛЮЧЕНЫ (BlueSky compliance)")
            else:
                logger.info(f"💬 Комментариев отправлено: {comments_made}")
            
            # Детальная статистика эффективности
            if posts_analyzed > 0:
                relevance_rate = (high_relevance_posts / posts_analyzed) * 100
                engagement_rate = (interactions / posts_analyzed) * 100 if interactions > 0 else 0
                repost_rate = (reposts_made / posts_analyzed) * 100 if reposts_made > 0 else 0
                comment_rate = (comments_made / posts_analyzed) * 100 if comments_made > 0 else 0
                
                logger.info(f"📈 Показатели эффективности:")
                logger.info(f"   📊 Процент релевантных постов: {relevance_rate:.1f}%")
                logger.info(f"   ❤️ Процент лайков: {engagement_rate:.1f}%")
                logger.info(f"   🔄 Процент репостов: {repost_rate:.1f}%")
                logger.info(f"   💬 Процент комментариев: {comment_rate:.1f}%")
                logger.info(f"   🎯 Конверсия релевантности: {(interactions/high_relevance_posts*100):.1f}%" if high_relevance_posts > 0 else "   🎯 Конверсия релевантности: 0%")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка умного взаимодействия: {e}")
            self.session_stats['errors'] += 1
    
    def calculate_relevance(self, text: str, post) -> float:
        """Компонентный расчёт релевантности поста (topical + structure + engagement)."""
        import math

        rel = self.config.get('relevance_settings', {})
        topic_groups = rel.get('topic_groups', {})
        topical_max = rel.get('topical_max', 0.45)
        kw_per_match = rel.get('keyword_per_match', 0.05)
        hashtag_bonus_val = rel.get('hashtag_bonus', 0.08)
        question_bonus_val = rel.get('question_bonus', 0.07)
        length_range = rel.get('optimal_length_range', [80, 300])
        length_bonus_val = rel.get('length_bonus', 0.05)
        eng_log_base = rel.get('engagement_log_base', 10)
        eng_max = rel.get('engagement_max', 0.25)

        text_lower = text.lower()
        tokens = set(re.findall(r'\b[a-zA-Z\u0400-\u04FF]{2,}\b', text_lower))

        # --- Topical score (token match by groups) ---
        topical = 0.0
        matched_groups = {}
        for group_name, group_data in topic_groups.items():
            kws = group_data.get('keywords', [])
            weight = group_data.get('weight', kw_per_match)
            hits = []
            for kw in kws:
                kw_parts = kw.lower().split()
                if len(kw_parts) == 1:
                    if kw_parts[0] in tokens:
                        hits.append(kw)
                else:
                    if kw.lower() in text_lower:
                        hits.append(kw)
            if hits:
                matched_groups[group_name] = hits
                topical += weight * len(hits)
        topical = min(topical, topical_max)

        # --- Structure score ---
        structure = 0.0
        hashtag_count = text.count('#')
        if hashtag_count > 0:
            structure += hashtag_bonus_val
        if '?' in text:
            structure += question_bonus_val
        text_len = len(text)
        if len(length_range) >= 2 and length_range[0] <= text_len <= length_range[1]:
            structure += length_bonus_val

        # --- Engagement score (log curve) ---
        likes = getattr(post.post, 'like_count', 0) or 0
        reposts_count = getattr(post.post, 'repost_count', 0) or 0
        raw_engagement = likes + reposts_count * 2
        if raw_engagement > 0 and eng_log_base > 1:
            eng_score = min(math.log(1 + raw_engagement, eng_log_base) / math.log(1000, eng_log_base), 1.0) * eng_max
        else:
            eng_score = 0.0

        final = min(topical + structure + eng_score, 1.0)

        # --- Compact log ---
        groups_str = ', '.join(f"{g}({len(h)})" for g, h in matched_groups.items()) if matched_groups else '-'
        logger.info(
            f"      📊 score={final:.2f}  topical={topical:.2f}[{groups_str}]  "
            f"struct={structure:.2f}  engage={eng_score:.2f}({likes}L+{reposts_count}R={raw_engagement})"
        )

        return final
    
    async def reply_to_post(self, post, comment_text: str) -> None:
        """Ответ на пост с правильным форматированием и поддержкой упоминаний"""
        try:
            # Используем асинхронный форматировщик для поддержки упоминаний
            formatted_comment = await self.formatter.create_post_async(comment_text, auto_format=True)
            
            author_handle = getattr(post.post.author, 'handle', 'unknown') if hasattr(post.post, 'author') and post.post.author else 'unknown'
            logger.info(f"💬 Комментирование поста от {author_handle}")
            logger.info(f"    Комментарий: {formatted_comment.text}")
            
            await self.bluesky_client.send_post(
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
                )
            )
            
            self.session_stats['comments_made'] += 1
            logger.info(f"✅ Комментарий опубликован!")
            
            # Сохраняем в память для анализа
            self.memory.successful_posts.append({
                'text': formatted_comment.text,
                'type': 'comment',
                'parent_post': post.post.uri,
                'timestamp': datetime.now().isoformat(),
                'relevance_score': 0.5  # Фиксированный балл для комментариев
            })
            
        except Exception as e:
            logger.error(f"❌ Ошибка при комментировании: {e}")
    
    async def run_bot_cycle(self) -> None:
        """Основной цикл работы бота с улучшенной безопасностью"""
        if not await self.authenticate():
            return
        
        cycle_count = 0
        last_post_time = datetime.now() - timedelta(hours=2)  # Начинаем с большой паузы
        
        logger.info("🤖 Бот v2.1 запущен с контролем качества и безопасности!")
        
        while True:
            try:
                cycle_start = time.time()
                # Обновляем heartbeat в начале каждого цикла
                self._update_heartbeat()
                self._consecutive_errors = 0  # Сброс circuit breaker при успешном старте цикла
                logger.info(f"🔄 Цикл {cycle_count + 1} - {datetime.now()}")
                
                # Engagement mode gate (orchestration-layer)
                engagement_mode = self.config.get('engagement_mode', 'open')
                run_engagement = engagement_mode != 'mention_only'

                if run_engagement:
                    await self.smart_engagement()
                    if cycle_count % 5 == 0:
                        await self.follow_strategy()
                else:
                    logger.info("🔇 Engagement пропущен (mode=mention_only)")
                
                # Генерация контента с контролем времени + smart scheduler
                time_since_last_post = datetime.now() - last_post_time
                min_interval = timedelta(minutes=self.post_interval[0])

                in_posting_window = self._is_posting_window()
                
                if time_since_last_post >= min_interval and in_posting_window:
                    await self.create_scheduled_post()
                    last_post_time = datetime.now()
                elif not in_posting_window:
                    logger.info("🌙 Quiet hours / вне active window — постинг отложен")
                else:
                    remaining = min_interval - time_since_last_post
                    logger.info(f"⏳ До следующего поста осталось: {remaining}")
                
                # Обучение на основе взаимодействий и реальных метрик
                if cycle_count % 10 == 0:
                    # Сначала обновляем реальные метрики постов
                    await self.update_posts_with_real_metrics()
                    # Затем запускаем обучение с реальными данными
                    self.learn_from_memory()
                
                # Сохранение памяти и очистка старых данных
                if cycle_count % 20 == 0:
                    # НОВОЕ: Сохраняем множества защиты от дубликатов в память
                    self.memory.commented_posts_cache = self.commented_posts
                    self.memory.recent_comments_cache = self.recent_comments[-20:]  # Последние 20
                    self.memory.liked_posts_cache = self.liked_posts
                    self.memory.reposted_posts_cache = self.reposted_posts
                    self.memory.followed_users_cache = self.followed_users
                    
                    self.memory.last_update = datetime.now()
                    self.memory.save()
                    logger.info("💾 Память сохранена (включая кэши защиты от дубликатов)")
                    logger.info(f"📊 Статистика сессии: {self.session_stats}")
                    logger.info(f"📊 Постов за день: {self.daily_post_count}/{self.max_posts_per_day}")
                
                # Периодическая очистка старых данных (раз в день)
                if cycle_count % 144 == 0 and cycle_count > 0:
                    self._cleanup_old_content_hashes()
                    self._cleanup_old_commented_posts()
                    self.action_ledger.compact()
                    removed_files, removed_bytes = _cleanup_log_budget(log_dir, LOG_TOTAL_BUDGET_BYTES)
                    if removed_files:
                        logger.warning(
                            f"🧹 Очистка логов по бюджету: удалено {removed_files} файлов, "
                            f"освобождено {removed_bytes / (1024 * 1024):.1f} MB"
                        )
                
                # RSS rotation + daily report
                if cycle_count % 50 == 0 and cycle_count > 0:
                    logger.info("🔧 RSS rotation...")
                    self.rss_manager.rotate()
                    self.rss_feeds = self.rss_manager.get_active_urls()
                    logger.info(f"📡 Active RSS: {len(self.rss_feeds)}, probation: {len(self.rss_manager.get_probation_urls())}")

                if cycle_count % 144 == 0 and cycle_count > 0:
                    report = generate_daily_report(self.session_stats, self.memory, self.config)
                    save_daily_report(report)
                    self.memory.ab_results = self.ab_engine.results
                    if self.dry_run and self.dry_run_log:
                        self.dry_run_log.save()
                
                # Анализ разнообразия постов каждые 30 циклов (примерно раз в 5-6 часов)
                if cycle_count % 30 == 0 and cycle_count > 0:
                    logger.info("📊 Запуск анализа разнообразия постов...")
                    await self.analyze_post_diversity()
                
                # Мониторинг здоровья бота каждые 20 циклов (примерно раз в 3-4 часа)
                if cycle_count % 20 == 0 and cycle_count > 0:
                    health_status = await self.health_monitor()
                    if health_status['overall_health'] == 'critical':
                        logger.warning("🚨 Критическое состояние здоровья! Запуск экстренного восстановления...")
                        recovery_success = await self.emergency_recovery()
                        if not recovery_success:
                            logger.error("❌ Экстренное восстановление не удалось")
                            break
                
                # Refresh persisted session periodically (every 10 cycles ~ every 10-15h)
                if cycle_count % 10 == 0 and cycle_count > 0:
                    self._persist_session()

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
        
        # В конце цикла запускаем обучение
        try:
            self.learning_module.analyze_performance_and_learn()
            # Перезагружаем конфиг после возможного обучения
            self.config = self.learning_module.load_config()
            logger.info("✅ Конфигурация перезагружена после цикла обучения.")
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле самообучения: {e}")
    
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
            if hasattr(self, 'commented_posts'):
                self.memory.commented_posts_cache = self.commented_posts
            if hasattr(self, 'recent_comments'):
                self.memory.recent_comments_cache = self.recent_comments[-20:]
            if hasattr(self, 'liked_posts'):
                self.memory.liked_posts_cache = self.liked_posts
            if hasattr(self, 'reposted_posts'):
                self.memory.reposted_posts_cache = self.reposted_posts
            if hasattr(self, 'followed_users'):
                self.memory.followed_users_cache = self.followed_users

            self.memory.last_update = datetime.now()
            self.memory.save()
            logger.info("💾 Финальное сохранение памяти (JSON, атомарная запись)")

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения памяти при завершении: {e}")
        
        # НОВОЕ: Закрываем aiohttp сессию в PollinationsAI
        try:
            if hasattr(self, 'pollinations_ai') and self.pollinations_ai:
                await self.pollinations_ai.close_session()
                logger.info("🔒 Pollinations.AI сессия закрыта")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка закрытия Pollinations сессии: {e}")
        
        # Закрываем основную HTTP сессию
        if hasattr(self, 'http_session') and self.http_session:
            await self.http_session.close()
            logger.info("🔒 Основная HTTP сессия закрыта")
        
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
            # Получаем информацию о посте
            post_info = await self.bluesky_client.get_post_thread(uri=post_uri)
            
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
    
    async def delayed_performance_check(self, post_uri: str, delay: int) -> None:
        """Отложенная проверка эффективности поста + A/B ER tracking + audience memory."""
        await asyncio.sleep(delay)

        try:
            performance = await self.analyze_post_performance(post_uri)
            er = performance.get('engagement_rate', 0)

            for post in self.memory.successful_posts:
                if post.get('uri') == post_uri:
                    post['engagement_rate'] = er
                    post['final_stats'] = performance

                    # A/B ER tracking
                    ab_fmt = post.get('ab_format')
                    if ab_fmt:
                        if delay <= 3600:
                            self.ab_engine.record_er(ab_fmt, er_1h=er)
                        elif delay <= 21600:
                            self.ab_engine.record_er(ab_fmt, er_6h=er)
                        else:
                            self.ab_engine.record_er(ab_fmt, er_24h=er)
                        self.memory.ab_results = self.ab_engine.results
                        logger.info(f"🔬 A/B ER записан: format={ab_fmt}, er={er:.3f} (delay={delay//3600}h)")

                    # Audience memory: topic_outcomes
                    topic = post.get('type', 'general')
                    if topic not in self.memory.topic_outcomes:
                        self.memory.topic_outcomes[topic] = {'total_er': 0.0, 'count': 0}
                    self.memory.topic_outcomes[topic]['total_er'] += er
                    self.memory.topic_outcomes[topic]['count'] += 1

                    if er > 10:
                        logger.info(f"🎯 Успешный пост! Вовлеченность: {er}")

                    # Auto-update post_strategies weights on 24h check
                    if delay > 21600 and self.memory.topic_outcomes:
                        self._update_strategy_weights_from_memory()
                    break

        except Exception as e:
            logger.error(f"Ошибка анализа производительности: {e}")

    def _update_strategy_weights_from_memory(self) -> None:
        """Корректирует веса post_strategies по topic_outcomes (±10% от текущего, не выходя за [0.05,0.5])."""
        try:
            outcomes = self.memory.topic_outcomes
            if not outcomes:
                return
            avg_all = sum(v['total_er'] / max(v['count'], 1) for v in outcomes.values()) / len(outcomes)
            strategies_config = self.config.get('post_strategies', {})
            changed = False
            for fname, weight in list(strategies_config.items()):
                topic_key = fname.lstrip('_create_').replace('quality_', '').replace('_post', '').replace('_', ' ').strip()
                best_match = max(outcomes.keys(), key=lambda k: len(set(k.split()) & set(topic_key.split())), default=None)
                if not best_match:
                    continue
                er_topic = outcomes[best_match]['total_er'] / max(outcomes[best_match]['count'], 1)
                delta = 0.1 if er_topic > avg_all else -0.1
                new_weight = round(max(0.05, min(0.50, weight * (1 + delta))), 3)
                if new_weight != weight:
                    strategies_config[fname] = new_weight
                    changed = True
            if changed:
                self.config['post_strategies'] = strategies_config
                logger.info(f"🔄 post_strategies обновлены по A/B данным: {strategies_config}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка обновления весов стратегий: {e}")
    
    async def maintain_rate_limits(self) -> None:
        """Управление rate limits"""
        # Отслеживаем количество операций
        operations_per_minute = 50
        operation_delay = 60 / operations_per_minute
        
        await asyncio.sleep(operation_delay)
    
    def should_follow_user(self, actor) -> bool:
        """Определение, стоит ли подписаться на пользователя"""
        try:
            description = (actor.description or "").lower()
            
            # Расширенные ключевые слова для подписки (на основе анализа популярных тем)
            target_keywords = [
                # Творчество
                'художник', 'artist', 'дизайнер', 'designer', 'фотограф', 'photographer',
                'музыкант', 'musician', 'писатель', 'writer', 'автор', 'author',
                
                # Технологии
                'программист', 'developer', 'разработчик', 'ai', 'ии', 'программирование', 
                'технологии', 'python', 'javascript', 'tech', 'стартап', 'startup',
                'инновации', 'наука', 'исследования', 'research',
                
                # Образование и культура
                'учитель', 'teacher', 'преподаватель', 'философ', 'philosopher',
                'культура', 'culture', 'образование', 'education', 'блогер', 'blogger',
                
                # Хобби и интересы
                'путешественник', 'traveler', 'повар', 'chef', 'спортсмен', 'athlete',
                'природа', 'nature', 'экология', 'ecology', 'животные', 'animals',
                
                # Профессии
                'журналист', 'journalist', 'психолог', 'psychologist', 'врач', 'doctor',
                'бизнес', 'business', 'предприниматель', 'entrepreneur'
            ]
            
            found_keywords = [keyword for keyword in target_keywords if keyword in description]
            keyword_score = len(found_keywords)
            
            # Проверяем активность
            followers_count = getattr(actor, 'followers_count', 0)
            following_count = getattr(actor, 'follows_count', 0)
            posts_count = getattr(actor, 'posts_count', 0)
            
            logger.info(f"    🔍 Анализ критериев:")
            logger.info(f"      Найденные ключевые слова: {found_keywords} (score: {keyword_score})")
            
            # Смягченные фильтры качества
            if followers_count > 100000:  # Слишком популярные
                logger.info(f"      ❌ Слишком популярный пользователь ({followers_count} подписчиков)")
                return False
            if following_count > followers_count * 5 and followers_count > 0:  # Смягчен с *3 до *5
                logger.info(f"      ❌ Подозрительное соотношение подписок ({following_count} vs {followers_count})")
                return False
            if posts_count < 3:  # Понижено с 10 до 3 постов
                logger.info(f"      ❌ Низкая активность ({posts_count} постов)")
                return False
            
            # Дополнительные критерии для новых пользователей
            if posts_count == 0 and followers_count == 0 and following_count == 0:
                logger.info(f"      ❌ Совершенно новый аккаунт без активности")
                return False
            
            # Решение на основе ключевых слов (понижен порог с 2 до 1)
            result = keyword_score >= 1
            logger.info(f"      {'✅' if result else '❌'} Итоговое решение: {keyword_score} ключевых слов >= 1")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка анализа пользователя: {e}")
            return False
    
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
        """Стратегия подписок для роста аудитории"""
        try:
            # Пробуем два источника: рекомендации + авторы популярных постов
            strategies = [
                self._follow_from_suggestions,
                self._follow_from_timeline
            ]
            
            for strategy in strategies:
                followed = await strategy()
                if followed > 0:
                    break  # Если одна стратегия сработала, переходим к следующему циклу
                        
        except Exception as e:
            logger.error(f"❌ Ошибка стратегии подписок: {e}")
    
    async def _follow_from_suggestions(self) -> int:
        """Подписки на основе рекомендаций BlueSky"""
        try:
            suggestions = await self.bluesky_client.app.bsky.actor.get_suggestions(params={'limit': 30})
            logger.info(f"👥 Получено {len(suggestions.actors)} рекомендаций пользователей")
            
            followed = 0
            max_follows = 1  # ИЗМЕНЕНО: Максимум 1 подписка за стратегию (было 3)
            users_analyzed = 0
            
            for actor in suggestions.actors:
                if followed >= max_follows:
                    break
                
                users_analyzed += 1
                
                try:
                    # Получаем полный профиль пользователя для доступа к статистике
                    full_profile = await self.bluesky_client.app.bsky.actor.get_profile(params={'actor': actor.did})
                    profile = full_profile
                    
                    # Теперь у нас есть доступ к статистике
                    description = (profile.description or "").lower()
                    followers = profile.followers_count if hasattr(profile, 'followers_count') else 0
                    following = profile.follows_count if hasattr(profile, 'follows_count') else 0
                    posts = profile.posts_count if hasattr(profile, 'posts_count') else 0
                    
                    logger.info(f"🔍 Анализ #{users_analyzed}: @{profile.handle}")
                    logger.info(f"    Описание: {profile.description[:100] if profile.description else 'Нет описания'}")
                    logger.info(f"    Подписчики: {followers}, Подписки: {following}, Посты: {posts}")
                    
                    # Проверяем, подходит ли пользователь с обновленным профилем
                    should_follow = self.should_follow_user(profile)
                    logger.info(f"    Решение: {'✅ Подписаться' if should_follow else '❌ Пропустить'}")
                    
                    if should_follow and profile.did not in self.followed_users:
                        try:
                            followed_ok = await self.engagement_service.follow(
                                did=profile.did,
                                handle=profile.handle,
                                source='suggestions',
                            )
                            if followed_ok:
                                logger.info(f"➕ Подписка на @{profile.handle} выполнена!")
                                followed += 1

                            try:
                                self.update_user_relationship(profile.did, 'follow', 5)
                            except Exception as rel_error:
                                logger.warning(f"⚠️ Ошибка обновления отношений для @{profile.handle}: {rel_error}")

                            await asyncio.sleep(random.uniform(3, 7))

                        except Exception as e:
                            logger.error(f"Ошибка подписки на @{profile.handle}: {e}")
                    elif profile.did in self.followed_users:
                        logger.info(f"👥 Уже подписаны на @{profile.handle}, пропускаем")
                            
                except Exception as e:
                    logger.error(f"Ошибка получения профиля @{actor.handle}: {e}")
                    continue
            
            logger.info(f"📊 Стратегия рекомендаций:")
            logger.info(f"    Проанализировано: {users_analyzed} пользователей")
            logger.info(f"    Подписок сделано: {followed}")
            
            return followed
                        
        except Exception as e:
            logger.error(f"❌ Ошибка стратегии рекомендаций: {e}")
            return 0
    
    async def _follow_from_timeline(self) -> int:
        """Подписки на авторов популярных постов из ленты"""
        try:
            timeline = await self.bluesky_client.get_timeline(limit=30)
            logger.info(f"📰 Анализ авторов популярных постов из ленты")
            
            followed = 0
            max_follows = 1  # ИЗМЕНЕНО: Максимум 1 подписка из ленты (было 2)
            analyzed_authors = set()
            
            # Сортируем посты по популярности
            popular_posts = sorted(timeline.feed, 
                                 key=lambda x: (x.post.like_count or 0) + (x.post.repost_count or 0) * 2, 
                                 reverse=True)[:20]
            
            for post in popular_posts:
                if followed >= max_follows:
                    break
                    
                author = post.post.author
                
                # Пропускаем уже проанализированных и себя (с защитой от AttributeError)
                my_did = getattr(self.bluesky_client.me, 'did', None) if hasattr(self.bluesky_client, 'me') and self.bluesky_client.me else None
                if author.did in analyzed_authors or (my_did and author.did == my_did):
                    continue
                    
                analyzed_authors.add(author.did)
                
                try:
                    # Получаем полный профиль автора для доступа к статистике
                    full_profile = await self.bluesky_client.app.bsky.actor.get_profile(params={'actor': author.did})
                    
                    # Теперь у нас есть доступ к полной статистике
                    description = full_profile.description or ""
                    followers = full_profile.followers_count if hasattr(full_profile, 'followers_count') else 0
                    following = full_profile.follows_count if hasattr(full_profile, 'follows_count') else 0
                    posts_count = full_profile.posts_count if hasattr(full_profile, 'posts_count') else 0
                    post_engagement = (post.post.like_count or 0) + (post.post.repost_count or 0) * 2
                    
                    logger.info(f"🔍 Автор популярного поста: @{full_profile.handle}")
                    logger.info(f"    Вовлеченность поста: {post_engagement}")
                    logger.info(f"    Подписчики: {followers}, Посты: {posts_count}")
                    
                    # Более мягкие критерии для авторов популярных постов + защита от дубликатов
                    if (followers > 10 and followers < 50000 and posts_count > 5 and
                        post_engagement > 50 and
                        full_profile.did not in self.followed_users):

                        try:
                            followed_ok = await self.engagement_service.follow(
                                did=full_profile.did,
                                handle=full_profile.handle,
                                source='timeline',
                            )
                            if followed_ok:
                                logger.info(f"➕ Подписка на автора популярного поста @{full_profile.handle}!")
                                followed += 1

                            try:
                                self.update_user_relationship(full_profile.did, 'follow', 7)
                            except Exception as rel_error:
                                logger.warning(f"⚠️ Ошибка обновления отношений для @{full_profile.handle}: {rel_error}")

                            await asyncio.sleep(random.uniform(4, 8))
                            
                        except Exception as e:
                            logger.error(f"Ошибка подписки на @{full_profile.handle}: {e}")
                    elif full_profile.did in self.followed_users:
                        logger.info(f"👥 Уже подписаны на автора @{full_profile.handle}, пропускаем")
                            
                except Exception as e:
                    logger.error(f"Ошибка получения профиля автора @{author.handle}: {e}")
                    continue
            
            logger.info(f"📊 Стратегия популярных авторов:")
            logger.info(f"    Подписок сделано: {followed}")
            
            return followed
            
        except Exception as e:
            logger.error(f"❌ Ошибка стратегии популярных авторов: {e}")
            return 0
    
    def learn_from_memory(self) -> None:
        """Обучение на основе накопленной памяти"""
        try:
            # Анализируем успешные посты
            if len(self.memory.successful_posts) > 10:
                # Находим паттерны успешного контента
                successful_types = [post.get('type', 'general') for post in self.memory.successful_posts]
                type_counter = Counter(successful_types)
                
                # Обновляем весы типов контента
                total_posts = len(self.memory.successful_posts)
                for content_type, count in type_counter.items():
                    success_rate = count / total_posts
                    self.memory.content_performance[content_type] = success_rate
                
                logger.info(f"📈 Обновлены весы контента: {dict(type_counter.most_common(3))}")
            
            # Анализируем паттерны взаимодействий
            if self.memory.user_relationships:
                # Безопасное получение оценок с проверкой наличия ключа
                total_score = 0
                valid_relationships = 0
                
                for rel in self.memory.user_relationships.values():
                    if isinstance(rel, dict):
                        # БЕЗОПАСНО получаем score с fallback на 0.0
                        score_value = rel.get('score', 0.0)
                        total_score += score_value
                        valid_relationships += 1
                
                if valid_relationships > 0:
                    avg_score = total_score / valid_relationships
                    self.memory.interaction_patterns['avg_relationship_score'] = avg_score
                    logger.info(f"🤝 Средний балл отношений: {avg_score:.2f}")
            
        except Exception as e:
            logger.error(f"Ошибка обучения: {e}")

    async def upload_image_to_bluesky(self, image_url: str) -> Optional[Dict]:
        """Загружает изображение в BlueSky и возвращает blob"""
        try:
            logger.info(f"📸 Загружаю изображение: {image_url}")
            
            # Скачиваем изображение используя единую сессию бота
            if not self.http_session:
                self.http_session = aiohttp.ClientSession()
            
            async with self.http_session.get(image_url, timeout=30) as response:
                    if response.status != 200:
                        logger.warning(f"⚠️ Не удалось скачать изображение: HTTP {response.status}")
                        return None
                    
                    # Проверяем размер (максимум 1MB для BlueSky)
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > 1000000:
                        logger.warning(f"⚠️ Изображение слишком большое: {content_length} bytes")
                        return None
                    
                    image_data = await response.read()
                    
                    # Проверяем тип файла
                    content_type = response.headers.get('content-type', '')
                    if not content_type.startswith('image/'):
                        logger.warning(f"⚠️ Неверный тип файла: {content_type}")
                        return None
            
            # Загружаем через BlueSky API
            blob_response = await self.bluesky_client.upload_blob(image_data)
            
            logger.info(f"✅ Изображение загружено: {blob_response.blob}")
            return blob_response.blob
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки изображения: {e}")
            return None

    async def create_post_with_image(self, text: str, image_url: str, alt_text: str = "Изображение к посту") -> Optional[RichTextPost]:
        """Создает пост с изображением"""
        try:
            # Загружаем изображение
            blob = await self.upload_image_to_bluesky(image_url)
            if not blob:
                # Если не удалось загрузить изображение, создаем пост без него
                logger.warning("⚠️ Создаю пост без изображения")
                return self.formatter.create_post(text, content_type='news')
            
            # Создаем пост с изображением
            post = self.formatter.create_post(text, content_type='news')
            
            # Добавляем embed с изображением
            post.embed = {
                "$type": "app.bsky.embed.images",
                "images": [{
                    "alt": alt_text,
                    "image": blob
                }]
            }
            
            logger.info("✅ Пост с изображением создан")
            return post
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания поста с изображением: {e}")
            # Fallback - пост без изображения
            return self.formatter.create_post(text, content_type='news')

    async def create_post_with_link_preview(self, text: str, url: str, title: str, description: str, image_url: str = None) -> Optional[RichTextPost]:
        """Создает пост с карточкой ссылки и изображением"""
        try:
            post = self.formatter.create_post(text, content_type='news')
            
            # СОХРАНЯЕМ URL И IMAGE_URL В ПОСТЕ ДЛЯ ПРОВЕРКИ ДУБЛИКАТОВ
            post.url = url
            post.image_url = image_url
            
            # Создаем базовую карточку ссылки
            external_data = {
                "uri": url,
                "title": title[:300],  # BlueSky лимит
                "description": description[:1000]  # BlueSky лимит
            }
            
            # Если есть изображение, пытаемся его загрузить
            if image_url:
                blob = await self.upload_image_to_bluesky(image_url)
                if blob:
                    external_data["thumb"] = blob
                    logger.info("✅ Добавлено изображение к карточке ссылки")
            
            # Добавляем карточку к посту
            post.embed = {
                "$type": "app.bsky.embed.external",
                "external": external_data
            }
            
            return post
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания поста с карточкой: {e}")
            # Fallback - простой пост
            return self.formatter.create_post(text, content_type='news')



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
        """Загрузка изображения в BlueSky из байтов"""
        if not image_data:
            logger.warning("⚠️ Попытка загрузить пустые данные изображения.")
            return None
        try:
            response = await self.bluesky_client.upload_blob(image_data)
            logger.info("✅ Изображение успешно загружено в BlueSky")
            return response.blob
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных изображения в BlueSky: {e}")
            self.session_stats['errors'] += 1
            return None

    async def generate_structured_post_content(self, prompt: str, model_key: str = 'creative') -> Optional[Dict[str, str]]:
        """Генерирует структурированный пост (текст + хештеги) и возвращает dict.

        Автоматически добавляет:
        - A/B format suffix для текущего цикла генерации
        - Усиленный промпт при повторной генерации после Quality Gate
        """
        prompt = self.content_service.build_structured_prompt(prompt)

        try:
            raw_response = await self.pollinations_ai.generate_content(prompt, model_key=model_key, json_output=True)
            if raw_response:
                data = None
                try:
                    data = json.loads(raw_response)
                except json.JSONDecodeError:
                    # Be tolerant to wrappers like markdown fences or leading text.
                    m = re.search(r"\{[\s\S]*\}", raw_response)
                    if m:
                        data = json.loads(m.group(0))
                    else:
                        raise

                if isinstance(data, dict) and 'post_text' in data and 'hashtags' in data:
                    post_text = str(data.get('post_text', '')).strip()
                    hashtags = str(data.get('hashtags', '')).strip()

                    if not post_text:
                        return None

                    # Normalize hashtags so they remain parseable and consistent.
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
                    # Keep only 2-4 tags to reduce spamminess.
                    tags = list(dict.fromkeys(tags))[:4]
                    if len(tags) < 2:
                        tags = ['#tech', '#insight']

                    normalized = {
                        'post_text': post_text,
                        'hashtags': ' '.join(tags)
                    }
                    logger.info("✅ AI сгенерировал структурированный пост (текст + хештеги)")
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
        """
        Обертка для создания поста с генерацией изображения.
        Теперь работает со структурированным контентом (текст + хештеги).
        """
        structured_content = await content_creation_func()

        if not structured_content:
            logger.warning(f"⚠️ Функция создания контента для '{content_type}' вернула пустой результат.")
            if fallback_func:
                fallback_content = await fallback_func()
                if isinstance(fallback_content, dict):
                    post_text = fallback_content.get('post_text', '')
                    hashtags = fallback_content.get('hashtags', '')
                    final_post_text = f"{post_text}\n\n{hashtags}".strip()
                    return self.formatter.create_post(final_post_text, content_type=content_type)
                if isinstance(fallback_content, str):
                    return self.formatter.create_post(fallback_content, content_type=content_type)
                return fallback_content
            return None
        
        post_text = structured_content.get('post_text', '')
        hashtags = structured_content.get('hashtags', '')
        final_post_text = f"{post_text}\n\n{hashtags}".strip()

        # ... (логика генерации изображения и публикации остается прежней)
        # ... (но использует `final_post_text` вместо `post_text_content`)
        
        image_prompt = await self.create_image_prompt_from_text(image_prompt_text)
        image_data = await self.pollinations_ai.generate_image_data(image_prompt)

        if image_data:
            logger.info(f"✅ Изображение для поста типа '{content_type}' сгенерировано.")
            image_blob = await self.upload_image_data_to_bluesky(image_data)
            if image_blob:
                alt_text = f"Арт-иллюстрация на тему: {image_prompt_text[:80]}..."
                return self.formatter.create_post(
                    final_post_text, 
                    content_type=content_type, 
                    image_blob=image_blob, 
                    image_alt_text=alt_text
                )

        logger.warning(f"⚠️ Не удалось сгенерировать изображение для '{content_type}', публикуем только текст.")
        return self.formatter.create_post(final_post_text, content_type=content_type)


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
                logger.info(f"📡 Тестирование {i+1}/10: {source_name}")
                
                start_time = datetime.now()
                timeout = 15
                
                # Используем единую HTTP сессию бота для диагностики
                if not self.http_session:
                    self.http_session = aiohttp.ClientSession()
                
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
    
    async def health_monitor(self) -> Dict[str, any]:
        """Мониторинг здоровья бота и автоматическое восстановление"""
        logger.info("🏥 Запуск мониторинга здоровья бота...")
        
        health_status = {
            'overall_health': 'healthy',
            'last_activity': None,
            'network_status': 'unknown',
            'memory_usage': 0,
            'api_connectivity': {},
            'recommendations': [],
            'auto_recovery_actions': []
        }
        
        try:
            # 1. Проверка сетевого подключения
            network_checks = await self._check_network_connectivity()
            health_status['api_connectivity'] = network_checks
            health_status['network_status'] = 'healthy' if network_checks.get('bluesky_api', False) else 'degraded'
            
            # 2. Проверка использования памяти
            try:
                import psutil
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                health_status['memory_usage'] = memory_mb
            except ImportError:
                health_status['memory_usage'] = 0
                logger.warning("⚠️ psutil не установлен, мониторинг памяти недоступен")
            
            # 3. Проверка последней активности
            last_activity = await self._check_last_activity()
            health_status['last_activity'] = last_activity
            
            # 4. Анализ потенциальных проблем
            issues = await self._analyze_potential_issues(health_status)
            
            # 5. Автоматическое восстановление если нужно
            recovery_actions = await self._perform_auto_recovery(issues)
            health_status['auto_recovery_actions'] = recovery_actions
            
            # 6. Общая оценка здоровья
            if len(issues) == 0:
                health_status['overall_health'] = 'healthy'
            elif len(issues) <= 2:
                health_status['overall_health'] = 'warning'
            else:
                health_status['overall_health'] = 'critical'
                
            logger.info(f"🏥 Мониторинг завершен: {health_status['overall_health']}")
            for action in recovery_actions:
                logger.info(f"🔧 Восстановление: {action}")
                
            return health_status
            
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга здоровья: {e}")
            health_status['overall_health'] = 'error'
            return health_status
    
    async def _check_network_connectivity(self) -> Dict[str, bool]:
        """Проверка доступности внешних API"""
        connectivity = {
            'bluesky_api': False,
            'pollinations_ai': False,
            'openai_api': False,
            'general_internet': False
        }
        
        # Проверяем каждый сервис с таймаутом
        async def check_endpoint(url: str, timeout: int = 10) -> bool:
            try:
                if not self.http_session:
                    return False
                async with self.http_session.get(url, timeout=timeout) as response:
                    return response.status < 500
            except Exception as e:
                logger.debug(f"Сетевая проверка {url}: {e}")
                return False
        
        try:
            # Быстрые проверки параллельно
            tasks = [
                check_endpoint('https://rooter.us-west.host.bsky.network/'),
                check_endpoint('https://text.pollinations.ai/'),
                check_endpoint('https://api.openai.com/'),
                check_endpoint('https://httpbin.org/get')  # Общий интернет
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            connectivity['bluesky_api'] = results[0] if isinstance(results[0], bool) else False
            connectivity['pollinations_ai'] = results[1] if isinstance(results[1], bool) else False
            connectivity['openai_api'] = results[2] if isinstance(results[2], bool) else False
            connectivity['general_internet'] = results[3] if isinstance(results[3], bool) else False
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки сети: {e}")
            
        return connectivity
    
    async def _check_last_activity(self) -> Dict[str, any]:
        """Проверка последней активности бота"""
        try:
            now = datetime.now()
            activity = {
                'last_post_hours_ago': None,
                'last_engagement_hours_ago': None,
                'cycles_without_posts': 0,
                'stuck_in_cycle': False
            }
            
            # Проверяем последний пост
            if self.memory.successful_posts:
                last_post_time = max(post.get('timestamp', now) for post in self.memory.successful_posts[-10:])
                if isinstance(last_post_time, str):
                    last_post_time = datetime.fromisoformat(last_post_time.replace('Z', '+00:00'))
                activity['last_post_hours_ago'] = (now - last_post_time).total_seconds() / 3600
            
            # Проверяем активность взаимодействий
            if hasattr(self, 'session_stats'):
                if self.session_stats.get('likes_given', 0) > 0:
                    activity['last_engagement_hours_ago'] = 0  # Недавно ставили лайки
                else:
                    activity['last_engagement_hours_ago'] = 2  # Примерная оценка
            
            # Определяем застревание в цикле
            if activity['last_post_hours_ago'] and activity['last_post_hours_ago'] > 6:
                activity['stuck_in_cycle'] = True
                
            return activity
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки активности: {e}")
            return {}
    
    async def _analyze_potential_issues(self, health_status: Dict) -> List[str]:
        """Анализ потенциальных проблем"""
        issues = []
        
        # Проверка сетевых проблем
        if not health_status['api_connectivity'].get('bluesky_api', False):
            issues.append('bluesky_api_unavailable')
        
        if not health_status['api_connectivity'].get('general_internet', False):
            issues.append('internet_connectivity_issue')
        
        # Проверка использования памяти
        if health_status['memory_usage'] > 400:  # Более 400MB
            issues.append('high_memory_usage')
        
        # Проверка активности
        activity = health_status.get('last_activity', {})
        if activity.get('stuck_in_cycle', False):
            issues.append('stuck_in_posting_cycle')
        
        if activity.get('last_post_hours_ago', 0) > 8:  # Нет постов 8+ часов
            issues.append('no_posts_long_time')
        
        return issues
    
    async def _perform_auto_recovery(self, issues: List[str]) -> List[str]:
        """Автоматические действия по восстановлению"""
        recovery_actions = []
        
        try:
            # Очистка памяти при высоком использовании
            if 'high_memory_usage' in issues:
                self._cleanup_old_content_hashes()
                self._cleanup_old_commented_posts()
                recovery_actions.append('memory_cleanup_performed')
            
            # Принудительное создание поста если долго не было
            if 'no_posts_long_time' in issues:
                try:
                    emergency_post = await self._create_emergency_unique_post()
                    if emergency_post:
                        recovery_actions.append('emergency_post_created')
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось создать экстренный пост: {e}")
            
            # Сброс состояния при зависании
            if 'stuck_in_posting_cycle' in issues:
                recovery_actions.append('cycle_state_reset')
            
            # Переинициализация HTTP сессии при сетевых проблемах
            if 'bluesky_api_unavailable' in issues or 'internet_connectivity_issue' in issues:
                try:
                    if self.http_session:
                        await self.http_session.close()
                    self.http_session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=30)
                    )
                    recovery_actions.append('http_session_reinitialized')
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось переинициализировать HTTP сессию: {e}")
        
        except Exception as e:
            logger.error(f"❌ Ошибка автовосстановления: {e}")
            recovery_actions.append(f'recovery_error: {str(e)}')
        
        return recovery_actions
    
    async def emergency_recovery(self) -> bool:
        """Экстренное восстановление бота при критических проблемах"""
        logger.warning("🚨 ЭКСТРЕННОЕ ВОССТАНОВЛЕНИЕ АКТИВИРОВАНО")
        
        try:
            # 1. Сохраняем текущее состояние
            self.memory.save()
            logger.info("💾 Состояние сохранено")
            
            # 2. Очищаем все кэши и временные данные
            self._cleanup_old_content_hashes()
            self._cleanup_old_commented_posts()
            logger.info("🧹 Кэши очищены")
            
            # 3. Переинициализируем HTTP сессию
            if self.http_session:
                await self.http_session.close()
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            logger.info("🔄 HTTP сессия переинициализирована")
            
            # 4. Проверяем аутентификацию
            auth_success = await self.authenticate()
            if not auth_success:
                logger.error("❌ Не удалось восстановить аутентификацию")
                return False
            
            logger.info("✅ Экстренное восстановление завершено успешно")
            return True
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка экстренного восстановления: {e}")
            return False

async def main():
    load_dotenv(override=False)

    config = {
        'handle': os.getenv('BLUESKY_HANDLE', 'your-bot.bsky.social'),
        'password': os.getenv('BLUESKY_PASSWORD', 'your-app-password'),
        'openai_api_key': os.getenv('OPENAI_API_KEY', 'your-openai-key')
    }
    
    if 'your-' in config['handle'] or 'your-' in config['password']:
        logger.error("❌ Необходимо настроить учетные данные!")
        logger.info("Установите переменные окружения:")
        logger.info("  BLUESKY_HANDLE - ваш handle в Bluesky")
        logger.info("  BLUESKY_PASSWORD - пароль приложения")
        logger.info("  OPENAI_API_KEY - ключ API OpenAI")
        return
    
    instance_lock = SingleInstanceLock(
        path=os.path.join(log_dir, 'bot.lock'),
        stale_seconds=600,
    )
    try:
        instance_lock.acquire()
    except RuntimeError as e:
        logger.error(f"❌ {e}")
        return

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