#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для создания богато оформленных постов в BlueSky
Поддерживает изображения, карточки ссылок, цитирование и сложные эмбеды
"""

import asyncio
import aiohttp
import base64
from typing import List, Dict, Optional, Tuple, Union, Any
from dataclasses import dataclass, field
from urllib.parse import urlparse
import re
from PIL import Image, ImageOps
import io
import mimetypes
from datetime import datetime
import json
import logging

from bluesky_post_formatter import BlueskyPostFormatter, RichTextPost

logger = logging.getLogger(__name__)

@dataclass 
class ImageData:
    """Данные изображения для загрузки"""
    data: bytes
    mime_type: str
    alt_text: Optional[str] = None
    aspect_ratio: Optional[Tuple[int, int]] = None
    
@dataclass
class LinkCard:
    """Данные для карточки ссылки"""
    url: str
    title: str
    description: str
    thumbnail: Optional[ImageData] = None

class BlueskyRichPostCreator:
    """Создатель богатых постов с поддержкой медиа"""
    
    def __init__(self, client=None):
        self.client = client
        self.formatter = BlueskyPostFormatter()
        self.max_image_size = 1_000_000  # 1MB
        self.supported_image_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        
    async def upload_image(self, image_data: ImageData) -> Optional[Dict]:
        """Загружает изображение и возвращает blob для embed"""
        if not self.client:
            raise ValueError("Client not initialized")
            
        try:
            # Оптимизируем изображение если нужно
            if len(image_data.data) > self.max_image_size:
                image_data = await self.optimize_image(image_data)
            
            # Загружаем blob
            response = await self.client.upload_blob(image_data.data)
            
            return {
                "$type": "blob",
                "ref": response.blob.ref,
                "mimeType": image_data.mime_type,
                "size": len(image_data.data)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки изображения: {e}")
            return None
    
    async def optimize_image(self, image_data: ImageData) -> ImageData:
        """Оптимизирует изображение для соответствия ограничениям"""
        img = Image.open(io.BytesIO(image_data.data))
        
        # Конвертируем в RGB если нужно
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        
        # Уменьшаем размер если слишком большой
        max_dimension = 2048
        if img.width > max_dimension or img.height > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        
        # Сохраняем с оптимизацией
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        
        return ImageData(
            data=output.getvalue(),
            mime_type='image/jpeg',
            alt_text=image_data.alt_text,
            aspect_ratio=(img.width, img.height)
        )
    
    async def create_post_with_images(self, 
                                    text: str,
                                    images: List[ImageData],
                                    content_type: str = 'general') -> RichTextPost:
        """Создает пост с изображениями"""
        # Форматируем текст
        post = self.formatter.create_post(text, content_type=content_type)
        
        if not images:
            return post
            
        # Загружаем изображения
        uploaded_images = []
        for img in images[:4]:  # Максимум 4 изображения
            blob = await self.upload_image(img)
            if blob:
                image_embed = {
                    "alt": img.alt_text or "",
                    "image": blob
                }
                if img.aspect_ratio:
                    image_embed["aspectRatio"] = {
                        "width": img.aspect_ratio[0],
                        "height": img.aspect_ratio[1]
                    }
                uploaded_images.append(image_embed)
        
        # Добавляем embed
        if uploaded_images:
            post.embed = {
                "$type": "app.bsky.embed.images",
                "images": uploaded_images
            }
        
        return post
    
    async def create_post_with_link_card(self,
                                       text: str,
                                       link_card: LinkCard,
                                       content_type: str = 'general') -> RichTextPost:
        """Создает пост с карточкой ссылки"""
        post = self.formatter.create_post(text, content_type=content_type)
        
        external = {
            "uri": link_card.url,
            "title": link_card.title,
            "description": link_card.description
        }
        
        # Добавляем миниатюру если есть
        if link_card.thumbnail:
            thumb_blob = await self.upload_image(link_card.thumbnail)
            if thumb_blob:
                external["thumb"] = thumb_blob
        
        post.embed = {
            "$type": "app.bsky.embed.external",
            "external": external
        }
        
        return post
    
    async def fetch_link_metadata(self, url: str) -> Optional[LinkCard]:
        """Автоматически извлекает метаданные из URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        return None
                    
                    html = await response.text()
                    
                    # Простой парсинг meta-тегов
                    title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
                    title = title_match.group(1) if title_match else url
                    
                    desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                    description = desc_match.group(1) if desc_match else ""
                    
                    # Ищем og:image
                    og_image_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                    
                    thumbnail = None
                    if og_image_match:
                        image_url = og_image_match.group(1)
                        # Загружаем изображение
                        try:
                            async with session.get(image_url, timeout=5) as img_response:
                                if img_response.status == 200:
                                    img_data = await img_response.read()
                                    mime_type = img_response.headers.get('Content-Type', 'image/jpeg')
                                    thumbnail = ImageData(data=img_data, mime_type=mime_type)
                        except:
                            pass
                    
                    return LinkCard(
                        url=url,
                        title=title[:100],  # Ограничиваем длину
                        description=description[:300],
                        thumbnail=thumbnail
                    )
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения метаданных для {url}: {e}")
            return None
    
    async def create_quote_post(self, 
                              text: str,
                              quoted_post_uri: str,
                              quoted_post_cid: str) -> RichTextPost:
        """Создает пост с цитированием другого поста"""
        post = self.formatter.create_post(text)
        
        post.embed = {
            "$type": "app.bsky.embed.record",
            "record": {
                "uri": quoted_post_uri,
                "cid": quoted_post_cid
            }
        }
        
        return post
    
    async def create_media_gallery_post(self,
                                      caption: str,
                                      image_urls: List[str],
                                      alt_texts: Optional[List[str]] = None) -> RichTextPost:
        """Создает пост-галерею из URL изображений"""
        images = []
        
        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(image_urls[:4]):
                try:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.read()
                            mime_type = response.headers.get('Content-Type', 'image/jpeg')
                            alt_text = alt_texts[i] if alt_texts and i < len(alt_texts) else None
                            
                            images.append(ImageData(
                                data=data,
                                mime_type=mime_type,
                                alt_text=alt_text
                            ))
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки изображения {url}: {e}")
        
        return await self.create_post_with_images(caption, images, content_type='art')
    
    def create_styled_post(self, template: str, **kwargs) -> RichTextPost:
        """Создает пост по стилизованному шаблону"""
        templates = {
            'announcement': """
{emoji} ОБЪЯВЛЕНИЕ: {title}

{content}

{hashtags}
""",
            'achievement': """
🎉 Достижение разблокировано! 🎉

{achievement_name}

{description}

Статистика:
{stats}

#achievement #milestone {additional_tags}
""",
            'daily_tip': """
💡 Совет дня по {topic}

{tip}

Попробуйте это сегодня и поделитесь результатами!

#dailytip #{topic_tag} #learning
""",
            'poll': """
📊 Опрос времени!

{question}

Варианты:
{options}

Голосуйте в комментариях! 👇

#опрос #poll #community
""",
            'weekly_recap': """
📅 Итоги недели

✅ Достигнуто:
{achievements}

📈 Статистика:
{stats}

🎯 Планы на следующую неделю:
{plans}

#weeklyrecap #productivity
"""
        }
        
        template_text = templates.get(template, "{content}")
        formatted_text = template_text.format(**kwargs)
        
        return self.formatter.create_post(formatted_text)

# Вспомогательные функции для создания специальных постов
class PostFactory:
    """Фабрика для создания различных типов постов"""
    
    @staticmethod
    def create_morning_greeting() -> str:
        """Создает утреннее приветствие"""
        import random
        greetings = [
            "☀️ Доброе утро! Какие планы на сегодня?",
            "🌅 Новый день - новые возможности! С добрым утром!",
            "☕ Утренний кофе и свежие идеи. Продуктивного дня!",
            "🌞 Просыпаемся и делаем этот день потрясающим!"
        ]
        return random.choice(greetings)
    
    @staticmethod
    def create_evening_reflection() -> str:
        """Создает вечерний пост для рефлексии"""
        import random
        reflections = [
            "🌙 День подходит к концу. Что было самым важным сегодня?",
            "✨ Вечерняя рефлексия: какой урок преподнес сегодняшний день?",
            "🌃 Время подводить итоги. Чем запомнился этот день?",
            "💫 Засыпая, помните о трех хороших вещах, которые произошли сегодня"
        ]
        return random.choice(reflections)
    
    @staticmethod
    def create_motivational_quote() -> str:
        """Создает мотивационную цитату"""
        import random
        quotes = [
            "💪 «Успех - это способность идти от неудачи к неудаче, не теряя энтузиазма» - У. Черчилль",
            "🚀 «Будущее принадлежит тем, кто верит в красоту своей мечты» - Э. Рузвельт", 
            "⭐ «Единственный способ делать великую работу - любить то, что делаешь» - С. Джобс",
            "🎯 «Не важно, как медленно ты идешь, главное - не останавливайся» - Конфуций"
        ]
        return random.choice(quotes)

# Пример интеграции с основным ботом
async def demo_rich_posts():
    """Демонстрация создания богатых постов"""
    creator = BlueskyRichPostCreator()
    
    # Пример 1: Пост с изображением
    print("=== Пост с изображением ===")
    with open("example.jpg", "rb") as f:
        image_data = ImageData(
            data=f.read(),
            mime_type="image/jpeg",
            alt_text="Красивый закат над городом"
        )
    
    image_post = await creator.create_post_with_images(
        "Невероятный закат сегодня! 🌅 Природа - лучший художник",
        [image_data],
        content_type='art'
    )
    print(json.dumps(image_post.to_dict(), ensure_ascii=False, indent=2))
    
    # Пример 2: Пост с карточкой ссылки
    print("\n=== Пост с карточкой ссылки ===")
    link_card = await creator.fetch_link_metadata("https://example.com/article")
    if link_card:
        link_post = await creator.create_post_with_link_card(
            "Отличная статья о будущем AI! Рекомендую к прочтению 📖",
            link_card,
            content_type='tech'
        )
        print(json.dumps(link_post.to_dict(), ensure_ascii=False, indent=2))
    
    # Пример 3: Стилизованный пост
    print("\n=== Стилизованный пост-достижение ===")
    achievement_post = creator.create_styled_post(
        'achievement',
        achievement_name="🏅 1000 подписчиков!",
        description="Спасибо всем за поддержку! Это только начало нашего пути.",
        stats="• Постов создано: 150\n• Лайков получено: 5000\n• Новых друзей: много!",
        additional_tags="#1000followers #thankyou"
    )
    print(achievement_post.text)

if __name__ == "__main__":
    # Для демонстрации без реального клиента
    creator = BlueskyRichPostCreator()
    
    # Создаем разные типы постов
    morning = PostFactory.create_morning_greeting()
    print("Утренний пост:", morning)
    
    quote = PostFactory.create_motivational_quote()
    print("\nМотивационная цитата:", quote)
    
    # Демонстрация шаблонов
    tip_post = creator.create_styled_post(
        'daily_tip',
        topic="Python",
        tip="Используйте list comprehension вместо циклов для создания списков. Это не только короче, но и работает быстрее!",
        topic_tag="python"
    )
    print("\nСовет дня:", tip_post.text) 