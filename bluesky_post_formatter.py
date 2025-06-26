#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для создания красиво оформленных постов в BlueSky
Поддерживает rich text, эмодзи, ссылки, упоминания и вложения
"""

import re
import json
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import aiohttp
from urllib.parse import urlparse
import emoji
import logging

logger = logging.getLogger(__name__)

@dataclass
class TextSpan:
    """Представляет участок текста с форматированием"""
    text: str
    start: int
    end: int
    type: str  # 'plain', 'link', 'mention', 'hashtag'
    metadata: Dict = field(default_factory=dict)

@dataclass
class RichTextPost:
    """Класс для создания поста с богатым форматированием"""
    text: str
    facets: List[Dict] = field(default_factory=list)
    embed: Optional[Dict] = None
    langs: List[str] = field(default_factory=list)
    labels: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Преобразование в словарь для API"""
        result = {"text": self.text}
        if self.facets:
            result["facets"] = self.facets
        if self.embed:
            result["embed"] = self.embed
        if self.langs:
            result["langs"] = self.langs
        if self.labels:
            result["labels"] = self.labels
        return result

class BlueskyPostFormatter:
    """Форматирование постов для BlueSky с rich text поддержкой"""
    
    def __init__(self, client=None):
        """
        Инициализация форматировщика
        Args:
            client: BlueSky AsyncClient для резолва DID (опционально)
        """
        self.client = client
        
        self.link_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
        self.mention_pattern = re.compile(r'@([a-zA-Z0-9.-]+)')
        self.hashtag_pattern = re.compile(r'#(\w+)')
        
        # Эмодзи для разных типов контента
        self.content_emojis = {
            'tech': ['💻', '🖥️', '📱', '⚡', '🚀', '🔧', '⚙️', '🛠️'],
            'ai': ['🤖', '🧠', '🎯', '✨', '🔮', '💡', '🎓', '📊'],
            'science': ['🔬', '🧬', '🔭', '🌌', '⚗️', '🧪', '📡', '🛰️'],
            'art': ['🎨', '🖼️', '🎭', '🎪', '🎬', '📸', '🎵', '🎸'],
            'news': ['📰', '📢', '🗞️', '📻', '📺', '🎙️', '📡', '🌍'],
            'discussion': ['💬', '🗣️', '💭', '🤔', '❓', '💡', '🎯', '📝'],
            'success': ['🎉', '🎊', '✅', '🏆', '🥇', '⭐', '🌟', '👏'],
            'warning': ['⚠️', '🚨', '❗', '⛔', '🔴', '🟡', '📍', '🔔'],
            'love': ['❤️', '💚', '💙', '💜', '🧡', '💛', '💕', '💖']
        }
        
        # Декоративные элементы
        self.decorations = {
            'bullet': '• ',
            'arrow': '→ ',
            'star': '★ ',
            'dot': '· ',
            'dash': '— ',
            'quote': '「',
            'quote_end': '」'
        }
    
    async def _resolve_handle_to_did(self, handle: str) -> Optional[str]:
        """Резолвит handle пользователя в DID через BlueSky API"""
        if not self.client:
            logger.warning(f"⚠️ Клиент не инициализирован, не могу резолвить @{handle}")
            return None
            
        try:
            # Убираем @ если есть
            clean_handle = handle.lstrip('@')
            
            # Используем BlueSky API для резолва
            profile = await self.client.app.bsky.actor.get_profile(params={'actor': clean_handle})
            
            if profile and hasattr(profile, 'did'):
                logger.info(f"✅ Резолв @{clean_handle} -> {profile.did}")
                return profile.did
            else:
                logger.warning(f"⚠️ Не удалось получить DID для @{clean_handle}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка резолва @{handle}: {e}")
            return None

    async def _extract_facets(self, text: str) -> List[Dict]:
        """Извлекает все facets (ссылки, упоминания, хештеги) из текста"""
        facets = []
        text_bytes = text.encode('utf-8')
        
        # Обрабатываем ссылки
        for match in self.link_pattern.finditer(text):
            byte_start = len(text[:match.start()].encode('utf-8'))
            byte_end = len(text[:match.end()].encode('utf-8'))
            
            facets.append({
                "$type": "app.bsky.richtext.facet",
                "index": {
                    "byteStart": byte_start,
                    "byteEnd": byte_end
                },
                "features": [{
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": match.group(0)
                }]
            })
        
        # Обрабатываем упоминания с реальным резолвом DID
        for match in self.mention_pattern.finditer(text):
            byte_start = len(text[:match.start()].encode('utf-8'))
            byte_end = len(text[:match.end()].encode('utf-8'))
            
            handle = match.group(1)
            did = await self._resolve_handle_to_did(handle)
            
            if did:
                # Используем реальный DID
                facets.append({
                    "$type": "app.bsky.richtext.facet",
                    "index": {
                        "byteStart": byte_start,
                        "byteEnd": byte_end
                    },
                    "features": [{
                        "$type": "app.bsky.richtext.facet#mention",
                        "did": did
                    }]
                })
                logger.info(f"✅ Упоминание @{handle} обработано с DID")
            else:
                # Если не удалось резолвить, пропускаем упоминание (не добавляем facet)
                logger.warning(f"⚠️ Упоминание @{handle} пропущено - не удалось резолвить DID")
        
        # Обрабатываем хештеги
        for match in self.hashtag_pattern.finditer(text):
            byte_start = len(text[:match.start()].encode('utf-8'))
            byte_end = len(text[:match.end()].encode('utf-8'))
            
            facets.append({
                "$type": "app.bsky.richtext.facet",
                "index": {
                    "byteStart": byte_start,
                    "byteEnd": byte_end
                },
                "features": [{
                    "$type": "app.bsky.richtext.facet#tag",
                    "tag": match.group(1)
                }]
            })
        
        return facets
    
    def create_post(self, 
                   text: str, 
                   auto_format: bool = True,
                   add_emojis: bool = True,
                   content_type: str = 'general',
                   image_blob: Optional[Dict] = None,
                   image_alt_text: str = "Изображение к посту") -> RichTextPost:
        """
        Создает пост с автоматическим форматированием
        
        ВАЖНО: Если используете упоминания (@username), убедитесь что передали client в __init__
        """
        if auto_format:
            text = self._auto_format_text(text)
        
        if add_emojis:
            text = self._add_contextual_emojis(text, content_type)
        
        # ВНИМАНИЕ: Для упоминаний нужно использовать асинхронную версию
        # Synchronous version - упоминания будут пропущены если нет client
        if '@' in text and not self.client:
            logger.warning("⚠️ Найдены упоминания, но клиент не инициализирован. Упоминания не будут активными.")
        
        # Извлекаем facets (синхронная версия без резолва DID)
        facets = self._extract_facets_sync(text)
        
        # Создаем базовый пост
        post = RichTextPost(text=text, facets=facets)
        
        # Добавляем изображение если есть
        if image_blob:
            post.embed = {
                "$type": "app.bsky.embed.images",
                "images": [{
                    "alt": image_alt_text,
                    "image": image_blob
                }]
            }
        
        return post

    async def create_post_async(self, 
                               text: str, 
                               auto_format: bool = True,
                               add_emojis: bool = True,
                               content_type: str = 'general',
                               image_blob: Optional[Dict] = None,
                               image_alt_text: str = "Изображение к посту") -> RichTextPost:
        """
        АСИНХРОННАЯ версия создания поста с поддержкой резолва упоминаний
        """
        if auto_format:
            text = self._auto_format_text(text)
        
        if add_emojis:
            text = self._add_contextual_emojis(text, content_type)
        
        # Асинхронно извлекаем facets с резолвом DID для упоминаний
        facets = await self._extract_facets(text)
        
        # Создаем пост
        post = RichTextPost(text=text, facets=facets)
        
        # Добавляем изображение если есть
        if image_blob:
            post.embed = {
                "$type": "app.bsky.embed.images",
                "images": [{
                    "alt": image_alt_text,
                    "image": image_blob
                }]
            }
        
        return post
    
    def _extract_facets_sync(self, text: str) -> List[Dict]:
        """Синхронная версия извлечения facets БЕЗ резолва DID (упоминания пропускаются)"""
        facets = []
        
        # Обрабатываем ссылки
        for match in self.link_pattern.finditer(text):
            byte_start = len(text[:match.start()].encode('utf-8'))
            byte_end = len(text[:match.end()].encode('utf-8'))
            
            facets.append({
                "$type": "app.bsky.richtext.facet",
                "index": {
                    "byteStart": byte_start,
                    "byteEnd": byte_end
                },
                "features": [{
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": match.group(0)
                }]
            })
        
        # Упоминания пропускаем в синхронной версии
        if self.mention_pattern.search(text):
            logger.info("ℹ️ Найдены упоминания, используйте create_post_async() для их обработки")
        
        # Обрабатываем хештеги
        for match in self.hashtag_pattern.finditer(text):
            byte_start = len(text[:match.start()].encode('utf-8'))
            byte_end = len(text[:match.end()].encode('utf-8'))
            
            facets.append({
                "$type": "app.bsky.richtext.facet",
                "index": {
                    "byteStart": byte_start,
                    "byteEnd": byte_end
                },
                "features": [{
                    "$type": "app.bsky.richtext.facet#tag",
                    "tag": match.group(1)
                }]
            })
        
        return facets
    
    def add_link_card(self, post: RichTextPost, url: str, 
                     title: str, description: str, 
                     image_url: Optional[str] = None) -> RichTextPost:
        """Добавляет карточку ссылки к посту с изображением"""
        external_data = {
            "uri": url,
            "title": self._smart_truncate(title, 50),
            "description": self._smart_truncate(description, 200)
        }
        
        # Если есть изображение, добавляем его
        if image_url:
            # Здесь должна быть загрузка и получение blob через AT Protocol
            # Пока оставляем упрощенную версию
            try:
                # В реальной реализации нужно:
                # 1. Скачать изображение
                # 2. Загрузить его через client.upload_blob()
                # 3. Получить blob reference
                external_data["thumb"] = {
                    "$type": "blob",
                    "ref": {"$link": "bafybeigxqx3nnv6xwjhqzj5m5q7h3j6"},  # Заглушка
                    "mimeType": "image/jpeg",
                    "size": 0
                }
            except Exception as e:
                # Если не удалось добавить изображение, продолжаем без него
                pass
        
        post.embed = {
            "$type": "app.bsky.embed.external",
            "external": external_data
        }
        
        return post
    
    async def add_image_to_post(self, post: RichTextPost, image_url: str, 
                               client = None) -> RichTextPost:
        """Добавляет изображение к посту (требует BlueSky client)"""
        try:
            if not client:
                return post
                
            # Скачиваем изображение
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        # Загружаем через AT Protocol
                        blob = await client.upload_blob(image_data)
                        
                        # Создаем embed с изображением
                        post.embed = {
                            "$type": "app.bsky.embed.images",
                            "images": [{
                                "alt": "Изображение к посту",
                                "image": blob
                            }]
                        }
                        
        except Exception as e:
            # Если не удалось добавить изображение, продолжаем без него
            pass
            
        return post
    
    def format_thread(self, posts_texts: List[str], 
                     thread_emoji: str = "🧵") -> List[RichTextPost]:
        """Форматирует серию постов как thread"""
        formatted_posts = []
        
        for i, text in enumerate(posts_texts):
            if i == 0:
                # Первый пост
                post_text = f"{thread_emoji} {text}\n\n(1/{len(posts_texts)})"
            elif i == len(posts_texts) - 1:
                # Последний пост
                post_text = f"{text}\n\n({i+1}/{len(posts_texts)}) Конец треда {thread_emoji}"
            else:
                # Средние посты
                post_text = f"{text}\n\n({i+1}/{len(posts_texts)})"
            
            formatted_posts.append(self.create_post(post_text))
        
        return formatted_posts
    
    def create_formatted_list(self, title: str, items: List[str], 
                            style: str = 'bullet') -> RichTextPost:
        """Создает красиво оформленный список"""
        decoration = self.decorations.get(style, '• ')
        
        text_parts = [title]
        for item in items:
            text_parts.append(f"{decoration}{item}")
        
        text = '\n'.join(text_parts)
        return self.create_post(text)
    
    def create_quote_post(self, quote: str, author: str = None) -> RichTextPost:
        """Создает пост с цитатой"""
        text = f"{self.decorations['quote']}{quote}{self.decorations['quote_end']}"
        
        if author:
            text += f"\n\n— {author}"
        
        return self.create_post(text, content_type='discussion')
    
    def create_announcement(self, title: str, details: str, 
                          urgency: str = 'normal') -> RichTextPost:
        """Создает пост-объявление"""
        emoji_map = {
            'normal': '📢',
            'important': '🚨',
            'success': '🎉',
            'warning': '⚠️'
        }
        
        emoji = emoji_map.get(urgency, '📢')
        text = f"{emoji} {title}\n\n{details}"
        
        return self.create_post(text, content_type='news')
    
    def add_language_tags(self, post: RichTextPost, langs: List[str]) -> RichTextPost:
        """Добавляет языковые теги к посту"""
        post.langs = langs
        return post
    
    def add_content_warning(self, post: RichTextPost, warning: str) -> RichTextPost:
        """Добавляет предупреждение о содержимом"""
        post.labels.append({
            "$type": "com.atproto.label.defs#selfLabel",
            "val": warning
        })
        return post
    
    def estimate_post_length(self, text: str) -> Dict[str, int]:
        """Оценивает длину поста в символах и байтах"""
        char_count = len(text)
        byte_count = len(text.encode('utf-8'))
        grapheme_count = len(list(text))  # Приблизительная оценка
        
        return {
            'characters': char_count,
            'bytes': byte_count,
            'graphemes': grapheme_count,
            'is_valid': byte_count <= 300
        }
    
    def split_long_text(self, text: str, max_bytes: int = 290) -> List[str]:
        """Разбивает длинный текст на части для thread'а"""
        parts = []
        current_part = ""
        
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sentence in sentences:
            test_part = current_part + " " + sentence if current_part else sentence
            if len(test_part.encode('utf-8')) <= max_bytes:
                current_part = test_part
            else:
                if current_part:
                    parts.append(current_part.strip())
                current_part = sentence
        
        if current_part:
            parts.append(current_part.strip())
        
        return parts

    def _auto_format_text(self, text: str) -> str:
        """Автоматическое форматирование текста"""
        # Базовая очистка
        text = text.strip()
        
        # Нормализация пробелов
        text = re.sub(r'\s+', ' ', text)
        
        # Исправление двойных точек
        text = re.sub(r'\.{2,}', '...', text)
        
        return text

    def _add_contextual_emojis(self, text: str, content_type: str) -> str:
        """Добавляет контекстные эмодзи к тексту"""
        if not text:
            return text
            
        # Если уже есть эмодзи в начале, не добавляем
        if any(emoji.is_emoji(char) for char in text[:5]):
            return text
            
        # Выбираем эмодзи по типу контента
        if content_type in self.content_emojis:
            import random
            selected_emoji = random.choice(self.content_emojis[content_type])
            return f"{selected_emoji} {text}"
            
        return text

    def _smart_truncate(self, text: str, max_length: int) -> str:
        """Умная обрезка текста по последнему пробелу перед лимитом"""
        if not text or len(text) <= max_length:
            return text
        
        # Ищем последний пробел перед лимитом
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length * 0.7:  # Если пробел найден не слишком далеко от конца
            return truncated[:last_space] + "..."
        else:
            return truncated.rstrip() + "..."

# Примеры использования
class PostTemplates:
    """Готовые шаблоны для различных типов постов"""
    
    @staticmethod
    def tech_news(title: str, summary: str, link: str) -> str:
        """Шаблон для технических новостей"""
        return f"""🚀 {title}

{summary}

💡 Что думаете об этом?

🔗 {link}

#технологии #новости #tech"""
    
    @staticmethod
    def ai_insight(topic: str, insight: str, question: str) -> str:
        """Шаблон для AI инсайтов"""
        return f"""🤖 AI-инсайт: {topic}

{insight}

🤔 {question}

#AI #искусственныйинтеллект #будущее"""
    
    @staticmethod
    def tutorial_announcement(title: str, topics: List[str], link: str) -> str:
        """Шаблон для анонса туториала"""
        topics_str = " ".join([f"#{topic}" for topic in topics])
        return f"""📚 Новый туториал: {title}

Разбираем:
{chr(10).join([f'• {topic}' for topic in topics[:3]])}

Полезно для начинающих и не только!

🔗 {link}

{topics_str}"""
    
    @staticmethod
    def discussion_starter(topic: str, context: str, question: str) -> str:
        """Шаблон для начала дискуссии"""
        return f"""💭 Давайте обсудим: {topic}

{context}

❓ {question}

Делитесь мнениями в комментариях! 👇

#обсуждение #дискуссия"""

# Функция для тестирования
async def demo_formatter():
    """Демонстрация возможностей форматирования"""
    formatter = BlueskyPostFormatter()
    
    # Пример 1: Простой пост с автоформатированием
    post1 = formatter.create_post(
        "Проверяем новый API BlueSky! Документация на https://docs.bsky.app #bluesky #api",
        content_type='tech'
    )
    print("Пост 1:", json.dumps(post1.to_dict(), ensure_ascii=False, indent=2))
    
    # Пример 2: Список
    post2 = formatter.create_formatted_list(
        "🔥 Топ-5 трендов в AI на этой неделе:",
        [
            "GPT-4 Vision получил обновление",
            "Новый open-source LLM от Meta", 
            "Прорыв в квантовых вычислениях",
            "AI-генерация видео стала доступнее",
            "Этические вопросы AI в фокусе"
        ]
    )
    print("\nПост 2:", post2.text)
    
    # Пример 3: Thread
    long_text = """
    Искусственный интеллект меняет мир программирования. 
    Современные IDE интегрируют AI-помощников. 
    Это ускоряет разработку, но требует новых навыков. 
    Важно понимать, как эффективно работать с AI.
    Будущее за человеко-машинным взаимодействием.
    """
    
    thread_posts = formatter.format_thread(
        formatter.split_long_text(long_text, max_bytes=200)
    )
    print("\nThread:")
    for i, post in enumerate(thread_posts):
        print(f"Пост {i+1}: {post.text}\n")
    
    # Пример 4: Использование шаблонов
    news_post = PostTemplates.tech_news(
        "OpenAI выпустил новую модель",
        "Улучшена скорость и качество генерации. Доступна через API.",
        "https://openai.com/blog/new-model"
    )
    formatted_news = formatter.create_post(news_post)
    print("\nНовостной пост:", formatted_news.text)

if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_formatter()) 