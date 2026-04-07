# 🤖 BlueSky Bot v3.0 - Революционный AI-бот с вирусным контентом

Интеллектуальный бот для BlueSky с передовыми AI-алгоритмами для максимального роста аудитории и viral engagement.

## 🔥 НОВОЕ в версии 3.0 - AI Revolution:

### **🎯 Анализатор вирусного потенциала:**

- Автоматическая оценка viral score каждого поста
- Детекция трендовых тем в реальном времени
- Оптимизация контента для максимального engagement

### **📈 Умные стратегии контента:**

- **25% горячие мнения** - дискуссионный контент для максимальных лайков
- **20% комментарии к трендам** - реакции на актуальные события
- **20% личные инсайты** - уникальные наблюдения и опыт
- **15% качественные новости** - отобранный контент с высоким потенциалом
- **10% предсказания** - смелые прогнозы для привлечения внимания

### **📊 Полная аналитика репостов:**

- Tracking эффективности каждого репоста
- Анализ viral коэффициента постов
- Обучение на успешных взаимодействиях

### **⏰ Оптимизация времени постинга:**

- Фокус на пиковые часы активности (7, 13, 18, 22 UTC)
- Адаптивные интервалы на основе engagement
- Максимизация видимости контента

### **🚀 Ожидаемые результаты:**

- **+40% лайков** за счет вирусного контента
- **+60% репостов** благодаря горячим мнениям  
- **+25-40% роста аудитории** в первый месяц

## 🌟 Ключевые возможности

### 🛡️ Безопасность и соблюдение правил

- ✅ **Полное соблюдение правил BlueSky** - никаких автоматических комментариев
- 🚫 **Отключены автоматические упоминания** - только лайки и репосты
- 🔒 **Защита от дубликатов** - продвинутая система предотвращения повторов
- ⏰ **Человекоподобные интервалы** - 60-90 минут между постами
- 📊 **Rate limit управление** - адаптивные таймауты и паузы

### 🤖 Революционный AI v3.0

- 🔥 **Анализатор вирусного потенциала** - ContentQualityAnalyzer для оценки viral score
- 📈 **Оптимизатор engagement** - EngagementOptimizer для максимального охвата
- 🎯 **5 новых стратегий контента** - горячие мнения, тренды, инсайты, предсказания
- 🎨 **Генерация изображений** через Pollinations.AI с улучшенными промптами
- 💬 **Умная генерация контента** - адаптивные алгоритмы на основе анализа аудитории
- 🧠 **Продвинутое машинное обучение** - анализ репостов и viral метрик
- 🔄 **Динамическая система контента** - реальная адаптация под тренды
- 📊 **Полная аналитика** - tracking всех типов взаимодействий

### 🌐 Контент и интеграции

- 📰 **RSS интеграция** - 24 качественных источника новостей
- 🌍 **Мультиязычность** - английский (приоритет) и русский
- 📋 **Разнообразные типы постов** - новости, мнения, советы, списки
- 🎯 **Умное взаимодействие** - релевантные лайки и репосты

### 🏥 Мониторинг и восстановление

- 💓 **Система Heartbeat** - отслеживание активности бота
- 🔧 **Автомониторинг здоровья** - проверка сети, памяти, API
- 🚨 **Экстренное восстановление** - автоматическое решение проблем
- 📊 **Детальная аналитика** - статистика работы и эффективности
- 📱 **Внешний мониторинг** - скрипт для контроля зависаний

---

## 🚀 Установка через APT (рекомендуемый способ для Ubuntu 24.04+)

### 1. Подключите репозиторий и установите:

```bash
echo "deb [trusted=yes] https://olgshow.github.io/BlueSky-bot/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/bluesky-bot.list
sudo apt update
sudo apt install bluesky-bot
```

### 2. Настройте конфигурацию:

```bash
sudo nano /etc/bluesky-bot/.env
```

### 3. Перезапустите:

```bash
sudo systemctl restart bluesky-bot
```

Примечание: если после установки в `/etc/bluesky-bot/.env` остались значения по умолчанию (`your-bot...`), пакет **не запускает сервис автоматически** до заполнения реальных учетных данных.

### Обновление бота:

```bash
sudo apt update && sudo apt upgrade
```

или точечно:

```bash
sudo apt install --only-upgrade bluesky-bot
```

### Откат на предыдущую версию:

```bash
sudo apt install bluesky-bot=3.1.0
```

(замените `3.1.0` на нужную версию из `apt list -a bluesky-bot`)

### Проверки после обновления:

```bash
sudo systemctl status bluesky-bot
journalctl -u bluesky-bot --since "5 min ago" --no-pager
```

### Проверка установки с сервера (чек-лист)

```bash
# 1) пакет установлен
dpkg -l | grep bluesky-bot

# 2) сервис активен
systemctl is-enabled bluesky-bot
systemctl is-active bluesky-bot

# 3) unit и рабочие пути на месте
ls -la /etc/systemd/system/bluesky-bot.service
ls -la /opt/bluesky-bot
ls -la /etc/bluesky-bot
ls -la /var/lib/bluesky-bot
```

### Полное удаление проекта с сервера

```bash
# Полная деинсталляция пакета + очистка данных/конфигов (postrm purge)
sudo apt purge -y bluesky-bot
sudo apt autoremove -y

# Удалить apt source (если больше не нужен)
sudo rm -f /etc/apt/sources.list.d/bluesky-bot.list
sudo apt update
```

Проверка, что проект удален:

```bash
dpkg -l | grep bluesky-bot || echo "package removed"
test -d /opt/bluesky-bot || echo "/opt removed"
test -d /etc/bluesky-bot || echo "/etc removed"
test -d /var/lib/bluesky-bot || echo "/var/lib removed"
systemctl status bluesky-bot 2>/dev/null || echo "service removed"
```

---

## 🚀 Альтернативная установка (скрипт, без APT)

### Автоматическая установка одной командой:

```bash
curl -sSL https://raw.githubusercontent.com/OLGShow/BlueSky-Bot/main/install.sh | bash
```

**Что делает скрипт:**

- ✅ Установка всех системных зависимостей (Python 3.11+, git, curl)
- ✅ Клонирование репозитория в `~/BlueSky-Bot`
- ✅ Создание Python виртуального окружения
- ✅ Установка всех Python пакетов (включая psutil для мониторинга)
- ✅ Настройка systemd сервиса для автозапуска
- ✅ Создание утилит управления ботом
- ✅ Настройка логирования и ротации логов
- ✅ Создание глобальных команд управления

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
bot-status     # 📊 Статус сервиса systemd
bot-logs       # 📋 Просмотр логов в реальном времени
bot-config     # ⚙️  Редактировать конфигурацию .env
bot-monitor    # 📱 Мониторинг состояния (ручной запуск)
bot-update     # 🔄 Обновить бота из Git репозитория
```

---

## 📊 Мониторинг и диагностика

### Просмотр статуса:

```bash
bot-status  # Показывает статус systemd сервиса
```

### Мониторинг в реальном времени:

```bash
bot-logs  # Логи в реальном времени
# или
tail -f ~/BlueSky-Bot/bot.log
```

### Ручной мониторинг:

```bash
cd ~/BlueSky-Bot
python3 bot_monitor.py  # Однократная проверка
```

### Автоматический мониторинг (cron):

```bash
# Добавить в crontab для проверки каждые 10 минут:
*/10 * * * * cd /home/bluesky/BlueSky-Bot && python3 bot_monitor.py >> monitor.log 2>&1
```

---

## 🔧 Ручная установка

Развернуть инструкции для ручной установки

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

### 5. Настройка systemd сервиса

```bash
# Копировать сервис
sudo cp systemd/bluesky-bot.service /etc/systemd/system/

# Отредактировать пути в сервисе
sudo nano /etc/systemd/system/bluesky-bot.service

# Перезагрузить systemd и включить автозапуск
sudo systemctl daemon-reload
sudo systemctl enable bluesky-bot.service
sudo systemctl start bluesky-bot.service
```



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

### Настройки стратегий (bot_config.json):

```json
{
  "post_strategies": {
    "_create_quality_news_post": 0.4,        // 40% - новостные посты из RSS
    "_create_personal_opinion_post": 0.25,   // 25% - личные мнения и наблюдения
    "_create_quality_ai_insight": 0.2,       // 20% - AI инсайты и размышления
    "_create_quality_tip_post": 0.1,         // 10% - полезные советы
    "_create_quality_discussion": 0.05       // 5% - дискуссионные вопросы
  },
  "engagement_settings": {
    "repost_threshold": 0.75,     // Порог релевантности для репостов
    "comment_threshold": 0.65,    // Порог для комментариев (отключены)
    "repost_probability": 0.15,   // Вероятность репоста 15%
    "comment_probability": 0.2,   // Вероятность комментария (отключено)
    "max_reposts_per_cycle": 1,   // Максимум 1 репост за цикл
    "max_comments_per_cycle": 2   // Максимум комментариев (отключено)
  }
}
```

### Новые настройки (bot_config.json):

```json
{
  "engagement_mode": "open",
  "engagement_whitelist": [],
  "activity_budget": {
    "hourly_points": 4500,
    "daily_points": 30000
  },
  "scheduling": {
    "timezone": "UTC",
    "active_windows": [[7, 23]],
    "quiet_hours": [0, 1, 2, 3, 4, 5, 6]
  }
}
```

| Параметр | Описание |
|---|---|
| `engagement_mode` | `open` (по умолчанию), `mention_only`, `whitelist_only` |
| `engagement_whitelist` | DID/handle список для whitelist mode |
| `activity_budget.hourly_points` | Лимит ATProto write-points в час (CREATE=3) |
| `activity_budget.daily_points` | Лимит write-points в сутки |
| `scheduling.timezone` | IANA timezone для active windows |
| `scheduling.active_windows` | Диапазоны часов `[start, end)` для постинга |
| `scheduling.quiet_hours` | Часы, когда постинг отключён |

---

## 🛡️ Соблюдение правил BlueSky

Бот **полностью соответствует** требованиям поддержки BlueSky:

### ✅ Что РАЗРЕШЕНО и реализовано:

- 👍 **Лайки релевантного контента** - умный анализ релевантности
- 🔄 **Репосты качественного контента** - с высоким порогом отбора
- 📝 **Собственные посты** - разнообразный качественный контент
- 👥 **Подписки на релевантных пользователей** - по ключевым словам
- ⚡ **Реагирование на упоминания** - только при прямом обращении

### 🚫 Что ОТКЛЮЧЕНО для соблюдения правил:

- ❌ **Автоматические комментарии** - полностью отключены
- ❌ **Автоматические упоминания** - отключены во избежание спама
- ❌ **Массовые действия** - строгие лимиты и человеческие паузы
- ❌ **Агрессивное поведение** - мягкие алгоритмы взаимодействия

---

## 🔄 Система обновлений

### Автоматическое обновление:

```bash
bot-update  # Обновляет код из Git и перезапускает бота
```

### Ручное обновление:

```bash
cd ~/BlueSky-Bot
git pull origin main
bot-restart
```

---

## 🧹 Подготовка к GitHub

Перед `git add/commit` рекомендуется очищать локальные runtime-артефакты:

```bash
rm -f bot_heartbeat.txt
rm -f bot_memory.json.bak
rm -f reports/verification_report.json
```

Локальные служебные планы Cursor и временные отчёты не должны попадать в публикацию.

---

## 🏥 Мониторинг здоровья и восстановление

### Встроенный Health Monitor:

Бот автоматически каждые 3-4 часа проверяет:

- 🌐 **Сетевое подключение** - BlueSky API, Pollinations.AI, OpenAI
- 💾 **Использование памяти** - автоочистка при >400MB
- ⏰ **Последнюю активность** - создание экстренных постов при простое >8 часов
- 🔄 **Состояние процессов** - автоматическое восстановление при зависании

### Heartbeat система:

- 📝 Файл `bot_heartbeat.txt` обновляется каждый цикл
- 🕐 Содержит timestamp, PID процесса и статус
- 🔍 Позволяет внешнему мониторингу отслеживать зависания

### Внешний мониторинг (bot_monitor.py):

```bash
# Ручная проверка
cd ~/BlueSky-Bot && python3 bot_monitor.py

# Автоматический мониторинг (cron каждые 10 минут)
*/10 * * * * cd /home/bluesky/BlueSky-Bot && python3 bot_monitor.py
```

**Что проверяет внешний мониторинг:**

- ✅ Процесс бота запущен (через pgrep)
- 💓 Heartbeat файл обновляется (критично если >20 минут)
- 📋 Записи в логах появляются (критично если >30 минут)
- 🔄 Автоматический перезапуск через systemctl при критических проблемах

---

## 📈 Аналитика и статистика

### Статистика сессии:

```python
{
    'posts_created': 0,      # Созданные посты
    'likes_given': 0,        # Поставленные лайки
    'reposts_made': 0,       # Сделанные репосты
    'follows_made': 0,       # Новые подписки
    'comments_made': 0,      # Комментарии (отключены)
    'errors': 0              # Ошибки
}
```

### Анализ разнообразия постов:

Бот автоматически анализирует разнообразие контента:

- 📊 Соотношение вопросов/утверждений/наблюдений
- 🎯 Оптимальное распределение: 30% вопросы, 50% утверждения, 20% наблюдения
- 💡 Автоматические рекомендации по улучшению контента

### RSS диагностика:

Периодическая проверка всех RSS источников:

- ⚡ Время ответа каждого источника
- 📊 Количество записей с каждого фида
- 🖼️ Статистика изображений
- 💡 Рекомендации по оптимизации

---

## 🐛 Устранение неполадок

### Бот не запускается:

```bash
# Проверить статус
bot-status

# Проверить логи
bot-logs

# Проверить конфигурацию
bot-config

# Перезапустить
bot-restart
```

### Бот завис:

```bash
# Автоматическая проверка зависания
cd ~/BlueSky-Bot && python3 bot_monitor.py

# Принудительный перезапуск
bot-stop && bot-start

# Проверить heartbeat
cat ~/BlueSky-Bot/bot_heartbeat.txt
```

### Проблемы с памятью:

```bash
# Проверить использование памяти
ps aux | grep python3 | grep bluesky

# Очистить логи
sudo journalctl --vacuum-time=7d

# Уменьшить частоту постов в bot_config.json
```

### Проблемы с сетью:

```bash
# Проверить подключение к BlueSky
ping bsky.social

# Проверить DNS
nslookup bsky.social

# Перезапустить сетевые службы
sudo systemctl restart networking
```

---

## 📚 Архитектура проекта

### Основные файлы:

- `bluesky_bot_v2.py` - Основной файл бота с полной функциональностью
- `bot_monitor.py` - Внешний скрипт мониторинга и восстановления
- `dynamic_content_system.py` - Система динамической генерации контента
- `pollinations_adapter.py` - Адаптер для работы с Pollinations.AI
- `bluesky_post_formatter.py` - Форматирование постов и работа с facets
- `bluesky_rich_posts.py` - Создание постов с изображениями и ссылками
- `bot_learning_module.py` - Модуль машинного обучения

### Сервисный слой:

- `state_service.py` - JSON-хранилище состояния, action ledger, **SingleInstanceLock**, **SessionStore**, **ActivityBudget**
- `engagement_service.py` - Лайки/репосты/фоллоу с **engagement mode guard** и budget pre-check
- `content_service.py` - Обёртка генерации контента и отложенные проверки ER
- `resilience_service.py` - Circuit breaker, retry policy, error classification, backoff
- `log_sanitizer.py` - Маскирование токенов/email/handles в логах
- `verify_bot.py` - Набор из 16 автотестов (state, ledger, sanitizer, lock, session, budget, scheduler)

### Конфигурационные файлы:

- `.env` - Переменные окружения и секреты
- `bot_config.json` - Настройки стратегий, лимитов, engagement mode и scheduling
- `requirements.txt` - Python зависимости
- `systemd/bluesky-bot.service` - Конфигурация systemd сервиса (dev-версия)

### Данные и логи:

- `bot.log` / `audit.log` - Основной лог и аудит действий (ротация)
- `bot_memory.json` - Память бота (JSON, атомарная запись, schema v2)
- `action_ledger.jsonl` - Идемпотентный лог действий (TTL 72h)
- `session.json` - Персистентная сессия ATProto (не коммитится в git)
- `bot.lock` - PID lock-файл для защиты от дубликатов
- `bot_heartbeat.txt` - Файл heartbeat для мониторинга
- `monitor.log` - Логи внешнего мониторинга

### Пути при установке через APT (.deb):

| Что | Путь |
|---|---|
| Код бота | `/opt/bluesky-bot/` |
| Конфиг (.env, bot_config.json) | `/etc/bluesky-bot/` |
| State-данные (memory, ledger, session) | `/var/lib/bluesky-bot/` |
| systemd unit | `/etc/systemd/system/bluesky-bot.service` |
| venv | `/opt/bluesky-bot/venv/` |
| Пользователь | `bluesky-bot` (системный) |

---

## 🤝 Контрибьютинг

1. **Fork** репозитория
2. Создайте ветку для фичи: `git checkout -b feature/amazing-feature`
3. Коммитьте изменения: `git commit -m 'Add amazing feature'`
4. Пушите в ветку: `git push origin feature/amazing-feature`
5. Создайте **Pull Request**

---

## 📝 Лицензия

Этот проект распространяется под лицензией MIT. Смотрите файл [LICENSE](LICENSE) для подробностей.

---

## 🔗 Полезные ссылки

- [BlueSky Developer Documentation](https://docs.bsky.app/)
- [AT Protocol Specification](https://atproto.com/)
- [Pollinations.AI Documentation](https://pollinations.ai/)
- [Python atproto Library](https://github.com/MarshalX/atproto)

---

## 📞 Поддержка

При возникновении проблем:

1. 📋 Проверьте логи: `bot-logs`
2. 🔧 Запустите диагностику: `python3 bot_monitor.py`
3. 📖 Ознакомьтесь с разделом "Устранение неполадок"
4. 🐛 Создайте Issue в GitHub с подробным описанием проблемы

---

*Последнее обновление: Апрель 2026* 