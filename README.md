# 🤖 BlueSky Bot v2.1

Автономный бот для BlueSky с AI-генерацией контента и изображениями.

## 📁 Файлы

- `bluesky_bot_v2.py` - **Основной бот**
- `pollinations_adapter.py` - AI генерация через Pollinations.AI
- `bluesky_post_formatter.py` - Форматирование постов
- `bluesky_rich_posts.py` - Посты с изображениями
- `requirements.txt` - Зависимости
- `bot_memory.pkl` - Память бота (создается автоматически)

## ⚙️ Установка

```bash
pip install -r requirements.txt
```

Создайте файл `.env`:
```env
BLUESKY_HANDLE=your-bot.bsky.social
BLUESKY_PASSWORD=your-app-password
OPENAI_API_KEY=your-openai-key  # Опционально
```

## 🚀 Запуск

```bash
python bluesky_bot_v2.py
```

## 🎯 Возможности

- ✅ AI-генерация постов (Pollinations.AI + OpenAI)
- ✅ Автоматические изображения из новостей
- ✅ Умное взаимодействие (лайки, репосты)
- ✅ Самообучение на основе успешных постов
- ✅ Безопасные лимиты (8 постов/день, 45-120 мин интервалы)

Бот работает полностью автономно и не требует вмешательства.

---

*Минималистичная версия BlueSky бота* 