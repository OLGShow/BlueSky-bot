# 🤖 BlueSky Bot v2.1

Автономный бот для BlueSky с соблюдением правил платформы, генерацией изображений и качественным контентом.

## ✨ Особенности

- 🛡️ **Соблюдение правил BlueSky** - никаких автоматических комментариев и упоминаний
- 🎨 **Генерация изображений** через Pollinations.AI
- 📰 **RSS интеграция** - 24 качественных источника
- 🧠 **Машинное обучение** - бот учится на результатах
- 📊 **Детальная аналитика** - полная статистика работы
- 🌐 **Мультиязычность** - английский и русский
- 🔒 **Безопасность** - защита от дубликатов и rate limits

---

## 🚀 Быстрая установка (Ubuntu Server 24.04.2)

### Одна команда для полной установки:

```bash
curl -sSL https://raw.githubusercontent.com/OLGShow/BlueSky-Bot/main/install.sh | bash
```

**Что делает скрипт:**
- ✅ Установка всех системных зависимостей
- ✅ Клонирование репозитория в `~/BlueSky-Bot`
- ✅ Создание Python виртуального окружения
- ✅ Установка всех Python пакетов
- ✅ Настройка systemd сервиса
- ✅ Создание утилит управления
- ✅ Настройка логирования и ротации
- ✅ Создание глобальных команд

### После установки:

1. **Настройте конфигурацию:**
   ```bash
   cd ~/BlueSky-Bot
   nano .env
   ```

2. **Введите ваши данные BlueSky:**
   ```bash
   BLUESKY_HANDLE=ваш-бот.bsky.social
   BLUESKY_PASSWORD=ваш-пароль-приложения
   ```

3. **Запустите бота:**
   ```bash
   bot-start
   ```

---

## 🎮 Команды управления

После установки доступны глобальные команды:

```bash
bot-start      # 🚀 Запустить бота
bot-stop       # ⏹️  Остановить бота  
bot-restart    # 🔄 Перезапустить бота
bot-status     # 📊 Статус сервиса
bot-logs       # 📋 Просмотр логов в реальном времени
bot-config     # ⚙️  Редактировать конфигурацию
bot-monitor    # 📱 Мониторинг состояния
bot-update     # 🔄 Обновить бота из Git
```

---

## 📊 Мониторинг

### Просмотр статуса:
```bash
bot-status
```

### Мониторинг в реальном времени:
```bash
bot-monitor
```

### Просмотр логов:
```bash
bot-logs
# или
tail -f ~/BlueSky-Bot/bot.log
```

---

## 🔧 Ручная установка

<details>
<summary>Развернуть инструкции для ручной установки</summary>

### 1. Подготовка системы

```bash
# Обновление пакетов
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
sudo apt install -y python3 python3-pip python3-venv git curl
```

### 2. Клонирование проекта

```bash
git clone https://github.com/YOUR_USERNAME/BlueSky-Bot.git
cd BlueSky-Bot
```

### 3. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Настройка конфигурации

```bash
cp .env.example .env
nano .env
```

Заполните файл `.env`:
```bash
BLUESKY_HANDLE=ваш-бот.bsky.social
BLUESKY_PASSWORD=ваш-пароль-приложения
OPENAI_API_KEY=ваш-ключ-openai  # опционально
```

### 5. Запуск

```bash
python3 bluesky_bot_v2.py
```

</details>

---

## ⚙️ Конфигурация

### Основные настройки (.env):

```bash
# ОБЯЗАТЕЛЬНЫЕ НАСТРОЙКИ
BLUESKY_HANDLE=ваш-бот.bsky.social
BLUESKY_PASSWORD=ваш-пароль-приложения

# ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ
OPENAI_API_KEY=ваш-ключ-openai  # резервный AI (опционально)

# СИСТЕМНЫЕ НАСТРОЙКИ
LOG_LEVEL=INFO
PYTHONPATH=/path/to/BlueSky-Bot
```

### Настройки бота (bot_config.json):

```json
{
  "post_strategies": {
    "_create_quality_news_post": 0.4,
    "_create_personal_opinion_post": 0.25,
    "_create_quality_ai_insight": 0.2,
    "_create_quality_tip_post": 0.1,
    "_create_quality_discussion": 0.05
  },
  "engagement_settings": {
    "repost_threshold": 0.75,
    "comment_threshold": 0.65,
    "repost_probability": 0.15,
    "comment_probability": 0.2,
    "max_reposts_per_cycle": 1,
    "max_comments_per_cycle": 2
  }
}
```

---

## 🛡️ Соблюдение правил BlueSky

Бот **полностью соответствует** требованиям поддержки BlueSky:

- ✅ **Лайки и репосты** - разрешены
- ✅ **Собственные посты** - разрешены
- ✅ **Подписки** - нормальное поведение
- 🚫 **Автоматические комментарии** - отключены
- 🚫 **Автоматические упоминания** - отключены
- 🚫 **Unsolicited engagement** - исключен

### Режим соблюдения правил:

```python
BLUESKY_COMPLIANT_MODE = True
NO_AUTO_COMMENTS = True  
NO_AUTO_MENTIONS = True
ONLY_LIKES_AND_REPOSTS = True
```

---

## 📈 Статистика и производительность

### Ключевые метрики:
- **Посты**: 10 в день (человеческий режим)
- **Интервал**: 60-90 минут между постами
- **Взаимодействия**: 5 за цикл
- **Пауза между циклами**: 60-90 минут
- **AI успешность**: 95%+ с Pollinations.AI
- **RSS источники**: 24 проверенных фида

### Типы контента:
- 📰 **Новости** (40%) - RSS с изображениями
- 💭 **Личные мнения** (25%) - динамический контент
- 🤖 **AI инсайты** (20%) - технологические размышления
- 💡 **Советы** (10%) - полезные лайфхаки
- 💬 **Дискуссии** (5%) - вопросы для вовлечения

---

## 🔧 Обновление

### Автоматическое обновление:
```bash
bot-update
```

### Ручное обновление:
```bash
cd ~/BlueSky-Bot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --upgrade
bot-restart
```

---

## 📁 Структура проекта

```
BlueSky-Bot/
├── 📄 bluesky_bot_v2.py           # Основной файл бота
├── 🎨 bluesky_post_formatter.py   # Форматирование постов
├── 🖼️  bluesky_rich_posts.py       # Посты с изображениями
├── 🤖 pollinations_adapter.py     # AI интеграция
├── 📊 dynamic_content_system.py   # Динамический контент
├── 🧠 bot_learning_module.py      # Машинное обучение
├── ⚙️  bot_config.json            # Конфигурация
├── 📋 requirements.txt           # Python зависимости
├── 🚀 install.sh                 # Автоматический инсталлятор
├── 🔧 manage.sh                  # Скрипт управления
├── 📱 monitor.sh                 # Мониторинг
├── 🔄 update.sh                  # Обновление
├── 📝 .env                       # Переменные окружения
└── 📄 README.md                  # Документация
```

---

## 🐛 Диагностика проблем

### Проверка статуса:
```bash
bot-status
```

### Просмотр логов:
```bash
bot-logs
# или детальные логи
journalctl -u bluesky-bot -n 50
```

### Проверка конфигурации:
```bash
cd ~/BlueSky-Bot
cat .env
```

### Тест RSS источников:
```bash
cd ~/BlueSky-Bot
source venv/bin/activate
python3 -c "
import asyncio
from bluesky_bot_v2 import AutonomousBlueskyBotV2
bot = AutonomousBlueskyBotV2()
asyncio.run(bot.test_rss_feeds_diagnostics())
"
```

---

## 🔒 Безопасность

- 🛡️ **Rate limiting** - соблюдение лимитов API
- 🔐 **Переменные окружения** - безопасное хранение ключей
- 🚫 **Защита от дубликатов** - умная система хеширования
- ⏰ **Человеческие паузы** - естественное поведение
- 📊 **Мониторинг ошибок** - автоматическое восстановление

---

## 🤝 Поддержка

### Создание Issue:
Если возникли проблемы, создайте [Issue](https://github.com/YOUR_USERNAME/BlueSky-Bot/issues) с:
- Описанием проблемы
- Логами (`bot-logs`)
- Версией системы (`lsb_release -a`)

### Полезные ссылки:
- [BlueSky API Docs](https://docs.bsky.app)
- [Pollinations.AI](https://pollinations.ai)
- [Python AsyncIO](https://docs.python.org/3/library/asyncio.html)

---

## 📜 Лицензия

MIT License - подробности в файле LICENSE.

---

## 🙏 Благодарности

- **BlueSky Team** - за отличную платформу
- **Pollinations.AI** - за бесплатную AI генерацию
- **Python Community** - за потрясающие библиотеки

---

<div align="center">

**Сделано с ❤️ для BlueSky сообщества**

🌟 **Поставьте звезду, если проект полезен!** 🌟

</div> 
