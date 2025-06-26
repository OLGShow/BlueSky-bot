#!/usr/bin/env python3
"""
Адаптер для интеграции Pollinations.AI в BlueSky бот
Полная замена OpenAI API с дополнительными возможностями
"""

import aiohttp
import urllib.parse
import random
import asyncio
import logging
from typing import Optional, Dict, Any, List
import time

logger = logging.getLogger(__name__)

class PollinationsAI:
    """
    Адаптер для работы с Pollinations.AI API
    Полная замена OpenAI API для бота
    """
    
    BASE_URL = "https://text.pollinations.ai"
    IMAGE_BASE_URL = "https://image.pollinations.ai"
    
    # Доступные модели с их характеристиками
    MODELS = {
        'creative': 'openai',           # GPT-4o-mini - творческие задачи
        'powerful': 'openai-large',     # GPT-4o - сложные задачи
        'smart': 'claude-hybridspace',  # Claude - аналитика
        'coder': 'qwen-coder',         # Для программирования
        'reasoning': 'deepseek-r1',     # С рассуждениями
        'fast': 'gemini',              # Быстрые ответы
        'search': 'searchgpt',         # С поиском в реальном времени
        'multilingual': 'llama',        # Многоязычная модель
        'dall-e-3': 'dall-e-3'          # DALL-E 3 для генерации изображений
    }
    
    def __init__(self, default_model: str = 'creative', language: str = 'en'):
        """
        Initialize adapter for BlueSky audience
        
        Args:
            default_model: Default model ('creative', 'powerful', etc.)
            language: Generation language ('en', 'ru')
        """
        self.default_model_key = default_model
        self.language = language
        self._session = None  # Будет создана в get_session()
        
        # Usage statistics
        self.stats = {
            'requests_made': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'models_used': {},
            'images_generated': 0
        }
        
        logger.info(f"🚀 Pollinations.AI adapter initialized for {language.upper()} audience")
        logger.info(f"📊 Available models: {list(self.MODELS.keys())}")
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Получение или создание aiohttp сессии"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60, connect=30)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    'User-Agent': 'BlueSky-Bot/2.1 (Python/aiohttp)'
                }
            )
            logger.debug("🔗 Создана новая aiohttp сессия")
        return self._session
    
    async def close_session(self):
        """Закрытие aiohttp сессии"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("🔒 aiohttp сессия закрыта")
    
    def _get_model_name(self, model_key: str) -> str:
        """Получение реального имени модели"""
        return self.MODELS.get(model_key, self.MODELS[self.default_model_key])
    
    def _build_url(self, prompt: str) -> str:
        """Построение URL для запроса"""
        encoded_prompt = urllib.parse.quote(prompt)
        return f"{self.BASE_URL}/{encoded_prompt}"
    
    def _prepare_params(self, 
                       model_key: str = None,
                       seed: Optional[int] = None,
                       system: Optional[str] = None,
                       json_output: bool = False,
                       private: bool = True,
                       **kwargs) -> Dict[str, Any]:
        """Подготовка параметров запроса"""
        model_key = model_key or self.default_model_key
        model_name = self._get_model_name(model_key)
        
        params = {"model": model_name}
        
        if seed is not None:
            params["seed"] = seed
        if system:
            params["system"] = system
        if json_output:
            params["json"] = "true"
        if private:
            params["private"] = "true"
        
        params.update(kwargs)
        return params
    
    def _get_system_prompt(self, content_type: str = 'general') -> str:
        """Генерация системного промпта в зависимости от языка"""
        if self.language == 'en':
            prompts = {
                'general': "You are a creative social media assistant. Write engaging, thoughtful content in English. Focus on tech, innovation, and meaningful discussions that resonate with the BlueSky community.",
                'comment': "You are a friendly social media user. Write short, positive comments in English with emojis. Be authentic and engaging.",
                'post': "You are a social media content creator. Write in English, use emojis, make content engaging and interesting for tech-savvy audience."
            }
        elif self.language == 'ru':
            prompts = {
                'general': "Ты креативный помощник для социальных сетей. Пиши увлекательный, продуманный контент на русском языке. Фокусируйся на технологиях, инновациях и значимых дискуссиях, которые найдут отклик в сообществе BlueSky.",
                'comment': "Ты дружелюбный пользователь социальных сетей. Пиши короткие, позитивные комментарии на русском языке с эмодзи. Будь искренним и вовлекающим.",
                'post': "Ты создатель контента для социальных сетей. Пиши на русском языке, используй эмодзи, делай контент увлекательным и интересным для технически подкованной аудитории."
            }
        else:
            # Fallback на английский
            return self._get_system_prompt('general')
        
        return prompts.get(content_type, prompts['general'])

    async def generate_content(self, 
                             prompt: str,
                             model_key: str = None,
                             system_role: str = None,
                             json_output: bool = False,
                             seed: Optional[int] = None) -> str:
        """
        Генерация контента (аналог OpenAI chat completion)
        
        Args:
            prompt: Текст запроса
            model_key: Ключ модели ('creative', 'powerful', etc.)
            system_role: Системная роль (аналог system message)
            json_output: Запрашивать ли ответ в формате JSON
            seed: Сид для воспроизводимости
        """
        self.stats['requests_made'] += 1
        model_key = model_key or self.default_model_key
        
        try:
            # Используем системный промпт в зависимости от языка
            if not system_role:
                system_role = self._get_system_prompt('general')
            
            # Строим URL и параметры
            url = self._build_url(prompt)
            params = self._prepare_params(
                model_key=model_key,
                system=system_role,
                seed=seed,
                json_output=json_output,
                private=True
            )
            
            logger.debug(f"🔄 Запрос к Pollinations: модель={self._get_model_name(model_key)}, json={json_output}")
            
            # Увеличенная пауза для предотвращения rate limiting
            pause_time = random.uniform(3, 8)
            logger.debug(f"⏳ Пауза перед запросом: {pause_time:.1f} сек")
            await asyncio.sleep(pause_time)
            
            # Делаем запрос
            response = await self._make_request(url, params)
            
            if response:
                self.stats['successful_requests'] += 1
                model_name = self._get_model_name(model_key)
                self.stats['models_used'][model_name] = self.stats['models_used'].get(model_name, 0) + 1
                
                logger.info(f"✅ Успешный ответ от Pollinations ({len(response)} символов)")
                return response.strip()
            else:
                logger.warning("⚠️ Пустой ответ от Pollinations API")
                raise Exception("Пустой ответ от API")
                
        except Exception as e:
            self.stats['failed_requests'] += 1
            logger.warning(f"⚠️ Ошибка Pollinations API: {e}")
            
            # Возвращаем fallback контент
            fallback = self._generate_fallback_content(prompt)
            logger.info(f"🎲 Используется fallback контент ({len(fallback)} символов)")
            return fallback
    
    async def _make_request(self, url: str, params: Dict[str, Any], timeout: int = 30) -> Optional[str]:
        """ПОЛНОСТЬЮ асинхронный HTTP запрос с aiohttp"""
        max_retries = 3
        base_delay = 5
        
        session = await self.get_session()
        
        for attempt in range(max_retries):
            try:
                async with session.get(url, params=params) as response:
                    logger.debug(f"📡 HTTP {response.status}: {url[:100]}...")
                    
                    # Проверяем статус ответа
                    if response.status == 429:
                        # Rate limiting - экспоненциальная задержка
                        retry_delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
                        logger.warning(f"⚠️ Rate limit (429). Попытка {attempt + 1}/{max_retries}. Ожидание {retry_delay:.1f} сек")
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            logger.error("❌ Превышен лимит попыток для rate limiting")
                            return None
                    
                    elif response.status == 200:
                        content = await response.text()
                        content = content.strip()
                        if content:
                            logger.debug(f"✅ Успешный HTTP запрос: {len(content)} символов")
                            return content
                        else:
                            logger.warning("⚠️ Пустой ответ от сервера")
                            return None
                    else:
                        # Другие HTTP ошибки
                        error_text = await response.text()
                        logger.warning(f"📡 HTTP {response.status}: {error_text[:100]}")
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(base_delay * (attempt + 1))
                            continue
                        else:
                            return None
                            
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout при запросе (попытка {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
                    continue
            except Exception as e:
                logger.warning(f"📡 HTTP ошибка (попытка {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
                    continue
        
        logger.error("❌ Не удалось выполнить HTTP запрос после нескольких попыток")
        return None
    
    def _generate_fallback_content(self, prompt: str) -> str:
        """Генерация fallback контента в зависимости от языка"""
        prompt_lower = prompt.lower()
        
        if self.language == 'en':
            if 'comment' in prompt_lower or 'reply' in prompt_lower:
                fallbacks = [
                    "Interesting point! 🤔",
                    "Thanks for sharing! ✨", 
                    "Great insight! 👍",
                    "Couldn't agree more! 🎯",
                    "This resonates! 💫"
                ]
            else:
                fallbacks = [
                    "🤖 Exploring new ideas in tech and innovation! What's exciting you today?",
                    "💭 Thoughts on the latest developments in our field? Share your perspective!",
                    "🚀 Every day brings new opportunities to learn and grow. What's on your mind?",
                    "✨ The future is being built today. What part are you playing in it?",
                    "🌟 Innovation happens when curiosity meets action. What are you curious about?"
                ]
        else:  # Russian
            if 'коммент' in prompt_lower or 'ответ' in prompt_lower:
                fallbacks = [
                    "Интересная мысль! 🤔",
                    "Спасибо за пост! ✨",
                    "Отличная точка зрения! 👍", 
                    "Полностью согласен! 🎯",
                    "Очень актуально! 💫"
                ]
            else:
                fallbacks = [
                    "🤖 Исследуем новые идеи в технологиях и инновациях! Что вас сегодня вдохновляет?",
                    "💭 Мысли о последних разработках в нашей сфере? Поделитесь своим мнением!",
                    "🚀 Каждый день приносит новые возможности учиться и расти. О чём думаете?",
                    "✨ Будущее создается сегодня. Какую роль в этом играете вы?",
                    "🌟 Инновации рождаются, когда любопытство встречается с действием. Что вас интригует?"
                ]
        
        return random.choice(fallbacks)
    
    async def generate_comment(self, post_text: str, comment_style: str = 'supportive') -> str:
        """
        Генерация комментария к посту
        
        Args:
            post_text: Текст поста для комментирования
            comment_style: Стиль комментария ('supportive', 'question', 'addition')
        """
        if self.language == 'en':
            style_prompts = {
                'supportive': f"Write a short supportive comment for this post (max 80 characters): {post_text[:200]}",
                'question': f"Ask a smart follow-up question about this post (max 80 characters): {post_text[:200]}",
                'addition': f"Add useful information to complement this post (max 80 characters): {post_text[:200]}"
            }
        else:  # Russian
            style_prompts = {
                'supportive': f"Напиши короткий поддерживающий комментарий к посту (максимум 80 символов): {post_text[:200]}",
                'question': f"Задай умный уточняющий вопрос к посту (максимум 80 символов): {post_text[:200]}",
                'addition': f"Дополни мысль из поста полезной информацией (максимум 80 символов): {post_text[:200]}"
            }
        
        prompt = style_prompts.get(comment_style, style_prompts['supportive'])
        system = self._get_system_prompt('comment')
        
        return await self.generate_content(
            prompt=prompt,
            model_key='fast',  # Используем быструю модель для комментариев
            system_role=system
        )
    
    async def generate_post_content(self, topic: str, post_type: str = 'general') -> str:
        """
        Генерация контента для поста
        
        Args:
            topic: Тема поста
            post_type: Тип поста ('motivational', 'news', 'tip', 'question')
        """
        if self.language == 'en':
            type_prompts = {
                'motivational': f"Create a motivational post about '{topic}' (up to 280 characters) with emojis",
                'news': f"Write an informative news post about '{topic}' (up to 280 characters)",
                'tip': f"Share a useful tip about '{topic}' (up to 280 characters)",
                'question': f"Create a discussion question about '{topic}' (up to 280 characters)",
                'general': f"Create an interesting post about '{topic}' (up to 280 characters) with emojis"
            }
        else:  # Russian
            type_prompts = {
                'motivational': f"Создай мотивационный пост на тему '{topic}' (до 280 символов) с эмодзи",
                'news': f"Напиши информационный пост-новость о '{topic}' (до 280 символов)",
                'tip': f"Поделись полезным советом по теме '{topic}' (до 280 символов)",
                'question': f"Создай вопрос для обсуждения на тему '{topic}' (до 280 символов)",
                'general': f"Создай интересный пост на тему '{topic}' (до 280 символов) с эмодзи"
            }
        
        prompt = type_prompts.get(post_type, type_prompts['general'])
        system = self._get_system_prompt('post')
        
        # Выбираем модель в зависимости от типа контента
        model_map = {
            'motivational': 'creative',
            'news': 'smart', 
            'tip': 'powerful',
            'question': 'creative',
            'general': 'creative'
        }
        
        model_key = model_map.get(post_type, 'creative')
        
        return await self.generate_content(
            prompt=prompt,
            model_key=model_key,
            system_role=system
        )
    
    async def generate_image_data(self,
                                prompt: str,
                                model: str = "dall-e-3",
                                width: int = 1024,
                                height: int = 1024,
                                seed: Optional[int] = None) -> Optional[bytes]:
        """Генерация данных изображения по промпту"""
        self.stats['requests_made'] += 1
        
        try:
            # Строим URL
            encoded_prompt = urllib.parse.quote(prompt)
            url = f"{self.IMAGE_BASE_URL}/prompt/{encoded_prompt}"
            params = {
                "model": model,
                "width": width,
                "height": height,
                "private": "true",
            }
            if seed:
                params["seed"] = seed

            logger.debug(f"🔄 Запрос на генерацию изображения: {prompt[:50]}...")
            
            # Делаем запрос на изображение
            image_data = await self._make_image_request(url, params)
            
            if image_data:
                self.stats['successful_requests'] += 1
                self.stats['images_generated'] += 1
                model_name = f"image_{model}"
                self.stats['models_used'][model_name] = self.stats['models_used'].get(model_name, 0) + 1
                
                logger.info(f"✅ Успешно сгенерировано изображение ({len(image_data)} байт)")
                return image_data
            else:
                raise Exception("Пустой ответ от API изображений")
                
        except Exception as e:
            self.stats['failed_requests'] += 1
            logger.warning(f"⚠️ Ошибка генерации изображения: {e}")
            return None
    
    async def _make_image_request(self, url: str, params: Dict[str, Any], timeout: int = 90) -> Optional[bytes]:
        """ПОЛНОСТЬЮ асинхронный HTTP запрос для получения изображения с aiohttp"""
        max_retries = 2
        base_delay = 10
        
        session = await self.get_session()
        
        for attempt in range(max_retries):
            try:
                async with session.get(url, params=params) as response:
                    logger.debug(f"📡 Запрос изображения, HTTP {response.status}: {url[:100]}...")
                    
                    if response.status == 200:
                        image_data = await response.read()
                        if image_data:
                            logger.debug(f"✅ Получено изображение: {len(image_data)} байт")
                            return image_data
                        else:
                            logger.warning("⚠️ Пустой ответ (изображение)")
                            return None
                    
                    # Обработка ошибок
                    if response.status == 429:
                        retry_delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
                        logger.warning(f"⚠️ Rate limit (429) для изображений. Попытка {attempt + 1}/{max_retries}. Ожидание {retry_delay:.1f} сек")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                    
                    # Для других ошибок
                    error_text = await response.text()
                    logger.warning(f"📡 HTTP {response.status} для изображения: {error_text[:100]}")
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(base_delay * (attempt + 1))
                        continue

            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout при запросе изображения (попытка {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
                    continue
            except Exception as e:
                logger.warning(f"📡 HTTP ошибка изображения (попытка {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
                    continue
        
        logger.error("❌ Не удалось получить изображение после нескольких попыток.")
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики использования"""
        success_rate = 0
        if self.stats['requests_made'] > 0:
            success_rate = (self.stats['successful_requests'] / self.stats['requests_made']) * 100
        
        return {
            'requests_made': self.stats['requests_made'],  # Исправлено для совместимости с ботом
            'total_requests': self.stats['requests_made'],
            'successful_requests': self.stats['successful_requests'],
            'failed_requests': self.stats['failed_requests'],
            'success_rate': f"{success_rate:.1f}%",
            'images_generated': self.stats['images_generated'],
            'models_used': self.stats['models_used'],
            'available_models': list(self.MODELS.keys())
        }
    
    async def test_connection(self) -> bool:
        """Асинхронное тестирование подключения к API"""
        try:
            test_prompt = "Hello!" if self.language == 'en' else "Привет!"
            url = self._build_url(test_prompt)
            params = self._prepare_params(model_key='fast')
            
            session = await self.get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    logger.info("✅ Подключение к Pollinations.AI успешно")
                    return True
                else:
                    logger.error(f"❌ Ошибка подключения: HTTP {response.status}")
                    return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Pollinations.AI: {e}")
            return False
    
    async def __aenter__(self):
        """Поддержка async context manager"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие сессии при выходе из контекста"""
        await self.close_session()

# Пример использования
async def test_pollinations():
    """Тестирование адаптера"""
    async with PollinationsAI(language='en') as ai:  # Теперь с context manager
        
        print("🔍 Тестирование Pollinations.AI адаптера...")
        
        # Тест подключения
        if not await ai.test_connection():
            print("❌ Подключение не удалось")
            return
        
        # Тест генерации контента
        print("\n📝 Тест генерации поста...")
        post = await ai.generate_post_content("artificial intelligence", "motivational")
        print(f"Пост: {post}")
        
        # Тест комментария
        print("\n💬 Тест генерации комментария...")
        comment = await ai.generate_comment("Amazing progress in AI development! 🚀", "supportive")
        print(f"Комментарий: {comment}")
        
        # Статистика
        print(f"\n📊 Статистика: {ai.get_statistics()}")

if __name__ == "__main__":
    asyncio.run(test_pollinations()) 