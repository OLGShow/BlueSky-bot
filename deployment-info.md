# 🚀 BlueSky Bot - Файлы развертывания

## 📁 Созданные файлы для автоматической установки:

### 🔧 Основные файлы установки:
- `install.sh` - **Главный автоматический инсталлятор**
- `env.example` - Пример конфигурации
- `quick-install.md` - Краткая инструкция установки

### 🐳 Docker поддержка:
- `Dockerfile` - Образ контейнера
- `docker-compose.yml` - Оркестрация
- `.dockerignore` - Исключения для Docker

### 🛠️ Системная интеграция:
- `systemd/bluesky-bot.service` - Systemd unit файл

### 📚 Документация:
- `README.md` - Обновленная документация с инструкциями
- `deployment-info.md` - Этот файл

---

## 🚀 Инструкция для публикации на GitHub:

### 1. Замените YOUR_USERNAME в файлах:
```bash
# В файлах нужно заменить YOUR_USERNAME на ваш GitHub username:
- install.sh (строка 96)
- README.md (строка 29) 
- quick-install.md (строка 5)
- systemd/bluesky-bot.service (строка 3)
```

### 2. Загрузите проект на GitHub:
```bash
git add .
git commit -m "🚀 Добавлена автоматическая установка для Ubuntu Server"
git push origin main
```

### 3. Установка на сервере:
```bash
curl -sSL https://raw.githubusercontent.com/ВАШ_USERNAME/BlueSky-Bot/main/install.sh | bash
```

---

## ✨ Что делает автоматический инсталлятор:

1. **Проверка системы** - Ubuntu 24.04.2
2. **Установка зависимостей** - Python, Git, системные пакеты
3. **Клонирование репозитория** - в ~/BlueSky-Bot
4. **Python окружение** - виртуальное окружение + pip пакеты
5. **Systemd сервис** - автозапуск и управление
6. **Утилиты управления** - manage.sh, monitor.sh, update.sh
7. **Глобальные команды** - bot-start, bot-stop, etc.
8. **Логирование** - ротация логов через logrotate
9. **Конфигурация** - .env файл для настроек

---

## 🎮 Команды после установки:

```bash
bot-start      # Запустить бота
bot-stop       # Остановить бота
bot-restart    # Перезапустить бота
bot-status     # Статус сервиса  
bot-logs       # Логи в реальном времени
bot-config     # Редактировать настройки
bot-monitor    # Мониторинг состояния
bot-update     # Обновить из Git
```

---

## 🔍 Альтернативные варианты запуска:

### 🐳 Docker:
```bash
git clone https://github.com/ВАШ_USERNAME/BlueSky-Bot.git
cd BlueSky-Bot
cp env.example .env
nano .env
docker-compose up -d
```

### 🔧 Ручная установка:
```bash
git clone https://github.com/ВАШ_USERNAME/BlueSky-Bot.git
cd BlueSky-Bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example .env
nano .env
python3 bluesky_bot_v2.py
```

---

## 📊 Структура проекта после установки:

```
~/BlueSky-Bot/
├── 🤖 bluesky_bot_v2.py          # Основной бот
├── 🎨 bluesky_post_formatter.py  # Форматирование
├── 🖼️  bluesky_rich_posts.py      # Посты с изображениями  
├── 🤖 pollinations_adapter.py    # AI генерация
├── 📊 dynamic_content_system.py  # Динамический контент
├── 🧠 bot_learning_module.py     # Машинное обучение
├── ⚙️  bot_config.json           # Настройки стратегий
├── 📋 requirements.txt          # Python зависимости
├── 📝 .env                      # Конфигурация (создается)
├── 🔧 manage.sh                 # Управление (создается)
├── 📱 monitor.sh                # Мониторинг (создается)
├── 🔄 update.sh                 # Обновление (создается)
├── 🚀 start_bot.sh              # Запуск (создается)
├── 📄 bot.log                   # Логи (создается)
├── 💾 bot_memory.pkl            # Память бота (создается)
└── 🐍 venv/                     # Python окружение (создается)
```

---

## ✅ Финальный чеклист:

- [x] Автоматический инсталлятор
- [x] Systemd интеграция  
- [x] Docker поддержка
- [x] Утилиты управления
- [x] Глобальные команды
- [x] Мониторинг и логирование
- [x] Система обновлений
- [x] Документация
- [x] Примеры конфигурации

**Проект готов к развертыванию! 🎉** 