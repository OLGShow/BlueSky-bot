#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автономный бот для BlueSky v2.1 с качественным оформлением постов
ИСПРАВЛЕНА ПРОБЛЕМА МАССОВОЙ ПУБЛИКАЦИИ И УЛУЧШЕНО КАЧЕСТВО КОНТЕНТА
"""

# Копируем весь код из bluesky_bot.py и добавляем импорты для форматирования
import asyncio
import random
import json
import os
import logging
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
import pickle
import re
import time
import html
import hashlib
from bot_learning_module import BotLearningModule

# Новые импорты для форматирования
from bluesky_post_formatter import BlueskyPostFormatter, PostTemplates, RichTextPost
from bluesky_rich_posts import BlueskyRichPostCreator, PostFactory, ImageData, LinkCard

# Добавляем импорт нашего адаптера
from pollinations_adapter import PollinationsAI

# Настройка логирования с абсолютным путем
import sys

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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True  # Принудительно переконфигурировать логирование
)
logger = logging.getLogger(__name__)

# Логируем путь к файлу для отладки
logger.info(f"📝 Логирование настроено. Файл лога: {log_file_path}")
logger.info(f"📂 Рабочая директория: {os.getcwd()}")
logger.info(f"🐍 Python путь: {sys.executable}")

# В начало файла добавляю новый безопасный режим
# БЕЗОПАСНЫЙ РЕЖИМ - МИНИМАЛЬНАЯ АВТОМАТИЗАЦИЯ
SAFE_MODE = True  # Включить для соблюдения правил Bluesky
MAX_DAILY_ACTIONS = 5  # Максимум 5 действий в день
HUMAN_LIKE_DELAYS = (3600, 7200)  # 1-2 часа между действиями

# НОВОЕ: Соблюдение правил BlueSky - NO UNSOLICITED ENGAGEMENT
BLUESKY_COMPLIANT_MODE = True  # Отключает автоматические комментарии и упоминания
NO_AUTO_COMMENTS = True  # Никаких автоматических комментариев (нарушение правил)
NO_AUTO_MENTIONS = True  # Никаких автоматических упоминаний (нарушение правил)
ONLY_LIKES_AND_REPOSTS = True  # Только лайки, репосты, подписки и собственные посты

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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True  # Принудительно переконфигурировать логирование
)
logger = logging.getLogger(__name__)

# Логируем путь к файлу для отладки
logger.info(f"📝 Логирование настроено. Файл лога: {log_file_path}")
logger.info(f"📂 Рабочая директория: {os.getcwd()}")
logger.info(f"🐍 Python путь: {sys.executable}")

# Используем тот же класс BotMemory из оригинального файла
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
    
    def save(self, filename: str = 'bot_memory.pkl'):
        """Сохранение памяти в файл"""
        with open(filename, 'wb') as f:
            pickle.dump(self, f)
    
    @classmethod
    def load(cls, filename: str = 'bot_memory.pkl'):
        """Загрузка памяти из файла с обратной совместимостью"""
        if os.path.exists(filename):
            try:
                with open(filename, 'rb') as f:
                    memory = pickle.load(f)
                    
                # Проверяем наличие новых полей и добавляем их если отсутствуют
                if not hasattr(memory, 'published_content_hashes'):
                    memory.published_content_hashes = set()
                    logger.info("🔧 Добавлено поле published_content_hashes для совместимости")
                    
                if not hasattr(memory, 'published_urls'):
                    memory.published_urls = set()
                    logger.info("🔧 Добавлено поле published_urls для совместимости")
                    
                return memory
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки памяти: {e}, создаем новую")
                pass
        
        return cls(
            successful_posts=[],
            failed_posts=[],
            interaction_patterns={},
            trending_topics={},
            user_relationships={},
            content_performance={},
            last_update=datetime.now(),
            published_content_hashes=set(),
            published_urls=set()
        )

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
        
        # Единая HTTP сессия для всех операций
        self.http_session = None
        
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
        
        # УЛУЧШЕННЫЕ НАСТРОЙКИ ДЛЯ 100 ПОСТОВ/ДЕНЬ (безопасно в пределах лимитов BlueSky)
        self.post_interval = (60, 90)  # ИЗМЕНЕНО: Интервал 60-90 минут между постами (более человечно)
        self.max_posts_per_day = 10  # ИЗМЕНЕНО: Максимум 10 постов в день (как обычный пользователь)
        self.max_interactions_per_cycle = 5  # ИЗМЕНЕНО: Максимум 5 взаимодействий за цикл (более естественно)
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

        # Инициализация модуля обучения
        self.learning_module = BotLearningModule(self.memory, 'bot_config.json')
        
        # Инициализация системы трендов и динамической генерации контента
        self.trending_tracker = BlueSkyTrendingTracker(self.bluesky_client)
        self.dynamic_generator = DynamicContentGenerator(self.trending_tracker)
    
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
                    "repost_threshold": 0.75,  # ИЗМЕНЕНО: Повышен порог для репостов (было 0.65)
                    "comment_threshold": 0.65,  # ИЗМЕНЕНО: Повышен порог для комментов (было 0.5)
                    "repost_probability": 0.15,  # ИЗМЕНЕНО: Снижена вероятность репоста (было 0.4)
                    "comment_probability": 0.2,  # ИЗМЕНЕНО: Снижена вероятность комментария (было 0.35)
                    "max_reposts_per_cycle": 1,  # ИЗМЕНЕНО: Максимум 1 репост за цикл (было 3)
                    "max_comments_per_cycle": 2  # ИЗМЕНЕНО: Максимум 2 комментария за цикл (было 4)
                }
            }
    
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
        """Очищает старые хеши контента (запускается периодически)"""
        # Очищаем хеши старше 30 дней на основе successful_posts
        cutoff_date = datetime.now() - timedelta(days=30)
        
        # Собираем хеши из недавних постов
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
                except:
                    pass
        
        # Обновляем множества только недавними хешами
        old_hash_count = len(self.memory.published_content_hashes)
        old_url_count = len(self.memory.published_urls)
        
        self.memory.published_content_hashes = recent_hashes
        self.memory.published_urls = recent_urls
        
        logger.info(f"🧹 Очищены старые хеши: {old_hash_count} -> {len(recent_hashes)}, URLs: {old_url_count} -> {len(recent_urls)}")
    
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

    async def authenticate(self) -> bool:
        """Аутентификация в Bluesky с обработкой rate limit"""
        # Инициализируем HTTP сессию если еще не создана
        if not self.http_session:
            self.http_session = aiohttp.ClientSession()
            logger.info("🌐 HTTP сессия инициализирована")
        
        max_retries = 3
        base_delay = 60  # Начальная задержка в секундах
        
        for attempt in range(max_retries):
            try:
                await self.bluesky_client.login(self.handle, self.password)
                logger.info(f"✅ Успешная авторизация: {self.handle}")
                self.authenticated = True
                return True
                
            except Exception as e:
                error_str = str(e)
                
                # Обработка rate limit (429 ошибки)
                if "429" in error_str or "Rate Limit" in error_str or "RateLimitExceeded" in error_str:
                    delay = base_delay * (2 ** attempt)  # Экспоненциальная задержка
                    logger.warning(f"⚠️ Rate limit достигнут. Попытка {attempt + 1}/{max_retries}")
                    logger.info(f"⏳ Ожидание {delay} секунд перед повторной попыткой...")
                    
                    if attempt < max_retries - 1:  # Не ждем после последней попытки
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"❌ Достигнуто максимальное количество попыток авторизации")
                        return False
                else:
                    # Другие ошибки авторизации
                    logger.error(f"❌ Ошибка авторизации: {e}")
                    return False
                    
        return False
    
    # НОВЫЕ МЕТОДЫ ДЛЯ КРАСИВЫХ ПОСТОВ
    
    async def create_scheduled_post(self) -> None:
        """ИСПРАВЛЕННОЕ создание запланированного поста с контролем качества и динамическими весами"""
        try:
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
            
            # Взвешенный выбор стратегии
            strategy = self._weighted_choice(strategies)
            post = await strategy()
            
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
                
                # Публикуем с правильными facets
                created = await self.bluesky_client.send_post(
                    text=post.text,
                    facets=post.facets if post.facets else None,
                    embed=post.embed if hasattr(post, 'embed') and post.embed else None,
                    langs=post.langs if hasattr(post, 'langs') and post.langs else ['ru']
                )
                
                # ПОМЕЧАЕМ КОНТЕНТ КАК ОПУБЛИКОВАННЫЙ
                self._mark_content_as_published(post.text, url, image_url)
                
                self.session_stats['posts_created'] += 1
                self.daily_post_count += 1
                logger.info(f"✅ Опубликован качественный пост #{self.daily_post_count}: {post.text[:80].replace(chr(10), ' ')}...")
                
                # Сохраняем для анализа с хешем
                content_hash = self._generate_content_hash(post.text, url, image_url)
                self.memory.successful_posts.append({
                    'text': post.text,
                    'uri': created.uri,
                    'created_at': datetime.now(),
                    'timestamp': datetime.now().isoformat(),
                    'type': getattr(post, 'content_type', 'general'),
                    'quality_score': getattr(post, 'quality_score', 0.8),
                    'content_hash': content_hash,
                    'url': url,
                    'image_url': image_url
                })
                
                # Планируем отложенный анализ производительности
                asyncio.create_task(self.delayed_performance_check(created.uri, 3600))
                
            else:
                logger.warning("⚠️ Пост не прошел проверку качества. Пропускаем публикацию.")
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания поста: {e}")
            self.session_stats['errors'] += 1
    
    def _weighted_choice(self, strategies: List[Tuple]) -> callable:
        """Взвешенный выбор стратегии создания поста"""
        functions, weights = zip(*strategies)
        return random.choices(functions, weights=weights)[0]
    
    def _evaluate_post_quality(self, post: RichTextPost) -> bool:
        """Оценка качества поста перед публикацией"""
        if not post or not post.text:
            return False
        
        score = 0.0
        
        # Длина поста (оптимальная 80-280 символов)
        text_length = len(post.text)
        if 80 <= text_length <= 280:
            score += 0.3
        elif text_length < 80:
            score += 0.1  # Слишком короткий
        else:
            score += 0.2  # Слишком длинный
        
        # Наличие эмодзи
        emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002700-\U000027BF]', post.text))
        if emoji_count > 0:
            score += 0.2
        
        # Наличие хештегов (если требуется)
        hashtag_count = post.text.count('#')
        if hashtag_count > 0:
            score += 0.2
        elif self.require_hashtags:
            logger.warning("⚠️ Пост не содержит обязательных хештегов")
            return False
        
        # Структурированность (списки, вопросы)
        if any(marker in post.text for marker in ['1.', '2.', '•', '◦', '▪', '?']):
            score += 0.2
        
        # Вовлекающий контент
        engaging_words = ['как', 'что', 'почему', 'какой', 'где', 'когда', 'думаете', 'мнение', 'считаете']
        if any(word in post.text.lower() for word in engaging_words):
            score += 0.1
        
        post.quality_score = score
        logger.info(f"📊 Оценка качества поста: {score:.2f}/1.0")
        
        return score >= self.min_post_quality_score
    
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
                        
                        # Пауза между источниками для вежливости
                        await asyncio.sleep(0.3)
                        
            except asyncio.TimeoutError:
                source_name = feed_url.split('//')[-1].split('/')[0]
                logger.warning(f"⏰ {source_name}: таймаут ({timeout}с)")
                continue
            except Exception as e:
                source_name = feed_url.split('//')[-1].split('/')[0]
                logger.warning(f"❌ {source_name}: {str(e)[:80]}...")
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
            timeline = await self.bluesky_client.get_timeline(limit=50)
            interactions = 0
            posts_analyzed = 0
            high_relevance_posts = 0
            reposts_made = 0
            comments_made = 0
            
            # Получаем настройки взаимодействия
            engagement_settings = self.config.get('engagement_settings', {})
            repost_threshold = engagement_settings.get('repost_threshold', 0.75)  # ИЗМЕНЕНО: Повышен порог для репостов (было 0.65)
            comment_threshold = engagement_settings.get('comment_threshold', 0.65)  # ИЗМЕНЕНО: Повышен порог для комментов (было 0.5)
            repost_probability = engagement_settings.get('repost_probability', 0.15)  # ИЗМЕНЕНО: Снижена вероятность репоста (было 0.4)
            comment_probability = engagement_settings.get('comment_probability', 0.2)  # ИЗМЕНЕНО: Снижена вероятность комментария (было 0.35)
            max_reposts = engagement_settings.get('max_reposts_per_cycle', 1)  # ИЗМЕНЕНО: Максимум 1 репост за цикл (было 3)
            max_comments = engagement_settings.get('max_comments_per_cycle', 2)  # ИЗМЕНЕНО: Максимум 2 комментария за цикл (было 4)
            
            logger.info(f"📰 Получено {len(timeline.feed)} постов для анализа")
            if BLUESKY_COMPLIANT_MODE and NO_AUTO_COMMENTS:
                logger.info(f"🎯 Пороги: репост≥{repost_threshold} (комментарии отключены)")
            else:
                logger.info(f"🎯 Пороги: репост≥{repost_threshold}, комментарий≥{comment_threshold}")
            
            for post in timeline.feed:
                if interactions >= self.max_interactions_per_cycle:
                    break
                
                if not hasattr(post.post.record, 'text'):
                    continue
                
                text = post.post.record.text
                author_handle = getattr(post.post.author, 'handle', 'unknown')
                author_did = getattr(post.post.author, 'did', None)
                
                # Пропускаем свои посты или посты без автора (с защитой от AttributeError)
                my_did = getattr(self.bluesky_client.me, 'did', None) if hasattr(self.bluesky_client, 'me') and self.bluesky_client.me else None
                if not author_did or (my_did and author_did == my_did):
                    continue
                
                posts_analyzed += 1
                
                # Вычисляем релевантность
                relevance_score = self.calculate_relevance(text.lower(), post)
                
                # Логируем анализ каждого поста
                logger.info(f"🔍 Пост #{posts_analyzed} от @{author_handle}: score={relevance_score:.2f}")
                logger.info(f"    Текст: {text[:100]}{'...' if len(text) > 100 else ''}")
                
                # Решаем, как взаимодействовать
                if relevance_score > 0.25:  # ИЗМЕНЕНО: Повышен порог для лайка (было 0.15)
                    high_relevance_posts += 1
                    logger.info(f"🎯 Достаточная релевантность! Действуем...")
                    
                    try:
                        # 1. Лайкаем релевантные посты (с защитой от дубликатов)
                        if post.post.uri not in self.liked_posts:
                            await self.bluesky_client.like(post.post.uri, post.post.cid)
                            self.session_stats['likes_given'] += 1
                            interactions += 1
                            self.liked_posts.add(post.post.uri)  # НОВОЕ: запоминаем лайкнутый пост
                            logger.info(f"❤️ Лайк поставлен!")
                            
                            # ДОБАВЛЕНО: Человеческая пауза после лайка
                            await asyncio.sleep(random.uniform(5, 10))
                        else:
                            logger.info(f"❤️ Пост уже был лайкнут ранее, пропускаем")
                        
                        # 2. НОВОЕ: Репостим высококачественный контент (с лимитом и защитой от дубликатов)
                        if (relevance_score >= repost_threshold and 
                            reposts_made < max_reposts and 
                            random.random() < repost_probability and
                            post.post.uri not in self.reposted_posts):  # НОВОЕ: проверка на уже репостнутые
                            await self.bluesky_client.repost(post.post.uri, post.post.cid)
                            self.session_stats['reposts_made'] += 1
                            reposts_made += 1
                            self.reposted_posts.add(post.post.uri)  # НОВОЕ: запоминаем репостнутый пост
                            logger.info(f"🔄 Репост выполнен! (score: {relevance_score:.2f}, #{reposts_made}/{max_reposts})")
                        elif post.post.uri in self.reposted_posts:
                            logger.info(f"🔄 Пост уже был репостнут ранее, пропускаем")
                        
                        # 3. ОТКЛЮЧЕНО: Комментарии автоматические (соблюдение правил BlueSky)
                        if BLUESKY_COMPLIANT_MODE and NO_AUTO_COMMENTS:
                            # Полностью отключаем автоматические комментарии для соблюдения правил
                            logger.info(f"🚫 Автоматические комментарии отключены (BlueSky compliance)")
                        elif (relevance_score >= comment_threshold and 
                            comments_made < max_comments and
                            post.post.uri not in self.commented_posts):  # НОВОЕ: проверка на уже прокомментированные посты
                            # Увеличиваем вероятность комментария для очень релевантных постов
                            adaptive_comment_prob = min(comment_probability * (relevance_score / comment_threshold), 0.4)
                            
                            if random.random() < adaptive_comment_prob:
                                comment = await self.generate_smart_comment(text)
                                if comment and self._is_comment_unique(comment):  # НОВОЕ: проверка уникальности
                                    await self.reply_to_post(post, comment)
                                    comments_made += 1
                                    self.commented_posts.add(post.post.uri)  # НОВОЕ: запоминаем пост
                                    self._track_recent_comment(comment)  # НОВОЕ: отслеживаем комментарий
                                    logger.info(f"💬 Комментарий отправлен! (score: {relevance_score:.2f}, #{comments_made}/{max_comments})")
                                else:
                                    logger.info(f"🔄 Комментарий пропущен: не уникальный или пустой")
                        
                        # Сохраняем информацию для обучения (только если есть author_did)
                        if author_did:
                            self.update_user_relationship(author_did, 'engagement', relevance_score)
                        
                    except Exception as e:
                        logger.error(f"Ошибка взаимодействия: {e}")
                    
                    await asyncio.sleep(random.uniform(8, 15))  # ИЗМЕНЕНО: Увеличена пауза между анализом постов (было 2-5)
                else:
                    logger.info(f"    ⏭️ Релевантность слишком низкая ({relevance_score:.2f} < 0.25)")  # ИЗМЕНЕНО: обновлен порог в логе
            
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
        """Вычисление релевантности поста"""
        score = 0.0
        text_lower = text.lower()
        
        # Расширенные ключевые слова на основе анализа популярных тем BlueSky
        keywords = [
            # ТОП-15 тем из анализа
            'искусство', 'art', 'программирование', 'programming', 'философия', 'philosophy',
            'культура', 'culture', 'природа', 'nature', 'технологии', 'tech', 'путешествия', 'travel',
            'образование', 'education', 'юмор', 'humor', 'фотография', 'photography', 'книги', 'books',
            'наука', 'science', 'дизайн', 'design', 'коты', 'cats',
            
            # Технические темы
            'ai', 'ии', 'искусственный интеллект', 'машинное обучение', 'python', 'javascript',
            'development', 'programming', 'инновации', 'стартап', 'startup', 'исследование', 'research',
            'code', 'coding', 'developer', 'software', 'app', 'web', 'data', 'algorithm', 'framework',
            'api', 'cloud', 'devops', 'machine learning', 'neural', 'database', 'backend', 'frontend',
            
            # Творчество и хобби
            'музыка', 'music', 'кино', 'movies', 'игры', 'games', 'готовка', 'cooking',
            'спорт', 'sport', 'фитнес', 'fitness', 'танцы', 'dance', 'мода', 'fashion',
            'creative', 'create', 'creating', 'artist', 'artistic', 'paint', 'draw', 'write',
            'writing', 'writer', 'photo', 'video', 'film', 'media', 'content', 'blog',
            
            # Социальные темы
            'психология', 'psychology', 'отношения', 'relationships', 'семья', 'family',
            'работа', 'work', 'карьера', 'career', 'бизнес', 'business', 'мотивация', 'motivation',
            'community', 'social', 'people', 'human', 'society', 'culture', 'tradition',
            'mental', 'emotional', 'feeling', 'experience', 'life', 'living', 'daily',
            
            # Повседневная жизнь
            'здоровье', 'health', 'еда', 'food', 'дом', 'home', 'животные', 'animals',
            'погода', 'weather', 'новости', 'news', 'экология', 'ecology',
            'morning', 'evening', 'day', 'night', 'today', 'weekend', 'coffee', 'tea',
            'dog', 'cat', 'pet', 'nature', 'environment', 'climate', 'green', 'sustainable',
            
            # Эмоциональные и вовлекающие
            'любовь', 'love', 'дружба', 'friendship', 'счастье', 'happiness', 'грусть', 'sadness',
            'радость', 'joy', 'вдохновение', 'inspiration', 'мечта', 'dream',
            'amazing', 'awesome', 'great', 'good', 'beautiful', 'interesting', 'cool',
            'wow', 'nice', 'best', 'favorite', 'like', 'enjoy', 'fun', 'happy',
            
            # Актуальные темы
            'crypto', 'blockchain', 'nft', 'metaverse', 'remote', 'hybrid', 'productivity',
            'mindfulness', 'meditation', 'workout', 'recipe', 'diy', 'hack', 'tip', 'advice',
            'tutorial', 'guide', 'learn', 'study', 'skill', 'course', 'book', 'podcast',
            'youtube', 'twitter', 'instagram', 'tiktok', 'social media', 'internet', 'online'
        ]
        
        found_keywords = []
        for keyword in keywords:
            if keyword in text_lower:
                score += 0.05  # Понижен с 0.1 до 0.05 для более широкого охвата
                found_keywords.append(keyword)
        
        # Бонус за хештеги
        hashtag_bonus = 0
        if '#' in text:
            hashtag_bonus = 0.1
            score += hashtag_bonus
        
        # Бонус за вопросы (вовлечение)
        question_bonus = 0
        if '?' in text:
            question_bonus = 0.1
            score += question_bonus
        
        # Учитываем вовлеченность поста
        likes = getattr(post.post, 'like_count', 0) or 0
        reposts = getattr(post.post, 'repost_count', 0) or 0
        engagement = likes + reposts * 2
        engagement_bonus = 0
        if engagement > 20:
            engagement_bonus = 0.15
            score += engagement_bonus
        elif engagement > 10:
            engagement_bonus = 0.1
            score += engagement_bonus
        
        # Детальное логирование расчета
        logger.info(f"      📊 Детали расчета релевантности:")
        logger.info(f"        Ключевые слова: {found_keywords} (+{len(found_keywords) * 0.05:.2f})")
        logger.info(f"        Хештеги: {'+0.10' if hashtag_bonus else '0.00'}")
        logger.info(f"        Вопросы: {'+0.10' if question_bonus else '0.00'}")
        logger.info(f"        Вовлеченность: {likes} лайков + {reposts} репостов = {engagement} (+{engagement_bonus:.2f})")
        logger.info(f"        Итоговый score: {min(score, 1.0):.2f}")
        
        return min(score, 1.0)
    
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
                logger.info(f"🔄 Цикл {cycle_count + 1} - {datetime.now()}")
                
                # Умное взаимодействие с контентом (каждый цикл для большей активности)
                await self.smart_engagement()
                
                # Стратегия подписок (еще реже)
                if cycle_count % 5 == 0:  # Каждый пятый цикл
                    await self.follow_strategy()
                
                # Генерация контента с контролем времени
                time_since_last_post = datetime.now() - last_post_time
                min_interval = timedelta(minutes=self.post_interval[0])
                
                if time_since_last_post >= min_interval:
                    await self.create_scheduled_post()
                    last_post_time = datetime.now()
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
                if cycle_count % 144 == 0:  # Примерно раз в 24 часа при цикле ~10мин
                    self._cleanup_old_content_hashes()
                    self._cleanup_old_commented_posts()  # Теперь очищает все взаимодействия
                
                # Диагностика RSS каждые 50 циклов (примерно раз в 8-10 часов)
                if cycle_count % 50 == 0 and cycle_count > 0:
                    logger.info("🔧 Запуск периодической диагностики RSS...")
                    await self.test_rss_feeds_diagnostics()
                
                # Анализ разнообразия постов каждые 30 циклов (примерно раз в 5-6 часов)
                if cycle_count % 30 == 0 and cycle_count > 0:
                    logger.info("📊 Запуск анализа разнообразия постов...")
                    await self.analyze_post_diversity()
                
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
                logger.error(f"❌ Ошибка в цикле бота: {e}")
                self.session_stats['errors'] += 1
                
                # Попытка переподключения при ошибке
                logger.info("🔄 Попытка переподключения через 5 минут...")
                await asyncio.sleep(300)  # 5 минут вместо 1 минуты
                
                if not await self.authenticate():
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
        
        try:
            # НОВОЕ: Сохраняем множества защиты от дубликатов в память перед выходом
            if hasattr(self, 'commented_posts'):
                self.memory.commented_posts_cache = self.commented_posts
            if hasattr(self, 'recent_comments'):
                self.memory.recent_comments_cache = self.recent_comments[-20:]  # Последние 20
            if hasattr(self, 'liked_posts'):
                self.memory.liked_posts_cache = self.liked_posts
            if hasattr(self, 'reposted_posts'):
                self.memory.reposted_posts_cache = self.reposted_posts
            if hasattr(self, 'followed_users'):
                self.memory.followed_users_cache = self.followed_users
            
            # Сохраняем память
            self.memory.last_update = datetime.now()
            self.memory.save()
            logger.info("💾 Финальное сохранение памяти (включая кэши защиты)")
            
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
        """Отложенная проверка эффективности поста"""
        await asyncio.sleep(delay)
        
        try:
            performance = await self.analyze_post_performance(post_uri)
            
            # Обновляем память
            for post in self.memory.successful_posts:
                if post.get('uri') == post_uri:
                    post['engagement_rate'] = performance['engagement_rate']
                    post['final_stats'] = performance
                    
                    # Учимся на результатах
                    if performance['engagement_rate'] > 10:
                        logger.info(f"🎯 Успешный пост! Вовлеченность: {performance['engagement_rate']}")
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
                    
                    if should_follow and profile.did not in self.followed_users:  # НОВОЕ: проверка на уже подписанных
                        try:
                            await self.bluesky_client.follow(profile.did)
                            self.session_stats['follows_made'] += 1
                            followed += 1
                            self.followed_users.add(profile.did)  # НОВОЕ: запоминаем подписку
                            logger.info(f"➕ Подписка на @{profile.handle} выполнена!")
                            
                            # Сохраняем в отношения с защитой от ошибок
                            try:
                                self.update_user_relationship(profile.did, 'follow', 5)
                            except Exception as rel_error:
                                logger.warning(f"⚠️ Ошибка обновления отношений для @{profile.handle}: {rel_error}")
                                # Не прерываем выполнение, подписка уже сделана
                            
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
                        post_engagement > 50 and full_profile.did not in self.followed_users):  # НОВОЕ: проверка
                        
                        try:
                            await self.bluesky_client.follow(full_profile.did)
                            self.session_stats['follows_made'] += 1
                            followed += 1
                            self.followed_users.add(full_profile.did)  # НОВОЕ: запоминаем подписку
                            logger.info(f"➕ Подписка на автора популярного поста @{full_profile.handle}!")
                            
                            # Сохраняем в отношения с защитой от ошибок
                            try:
                                self.update_user_relationship(full_profile.did, 'follow', 7)  # Выше балл за популярность
                            except Exception as rel_error:
                                logger.warning(f"⚠️ Ошибка обновления отношений для @{full_profile.handle}: {rel_error}")
                                # Не прерываем выполнение, подписка уже сделана
                            
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
        """
        Генерирует структурированный пост (текст + хештеги) и возвращает dict.
        """
        try:
            raw_response = await self.pollinations_ai.generate_content(prompt, model_key=model_key, json_output=True)
            if raw_response:
                data = json.loads(raw_response)
                if 'post_text' in data and 'hashtags' in data:
                    logger.info("✅ AI сгенерировал структурированный пост (текст + хештеги)")
                    return data
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
                return await fallback_func()
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

async def main():
    # Загружаем конфигурацию из переменных окружения
    config = {
        'handle': os.getenv('BLUESKY_HANDLE', 'your-bot.bsky.social'),
        'password': os.getenv('BLUESKY_PASSWORD', 'your-app-password'),
        'openai_api_key': os.getenv('OPENAI_API_KEY', 'your-openai-key')
    }
    
    # Проверяем конфигурацию
    if 'your-' in config['handle'] or 'your-' in config['password']:
        logger.error("❌ Необходимо настроить учетные данные!")
        logger.info("Установите переменные окружения:")
        logger.info("  BLUESKY_HANDLE - ваш handle в Bluesky")
        logger.info("  BLUESKY_PASSWORD - пароль приложения")
        logger.info("  OPENAI_API_KEY - ключ API OpenAI")
        return
    
    # Создаем и запускаем улучшенного бота
    bot = AutonomousBlueskyBotV2()
    
    try:
        await bot.run_bot_cycle()
    except KeyboardInterrupt:
        logger.info("⌨️ Получен сигнал остановки")
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main()) 