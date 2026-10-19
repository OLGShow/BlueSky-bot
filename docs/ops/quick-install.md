# 🚀 BlueSky Bot - Быстрая установка

## 1️⃣ Одна команда (Ubuntu 24.04.2):

```bash
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/BlueSky-Bot/main/install.sh | bash
```

## 2️⃣ Настройка:

```bash
cd ~/BlueSky-Bot
nano .env
```

Заполните:
```bash
BLUESKY_HANDLE=ваш-бот.bsky.social
BLUESKY_PASSWORD=ваш-пароль-приложения
```

## 3️⃣ Запуск:

```bash
bot-start
```

## 📋 Команды управления:

- `bot-start` - запустить
- `bot-stop` - остановить  
- `bot-restart` - перезапустить
- `bot-status` - статус
- `bot-logs` - логи
- `bot-monitor` - мониторинг
- `bot-config` - настройки
- `bot-update` - обновить

## 🐳 Альтернатива - Docker:

```bash
git clone https://github.com/YOUR_USERNAME/BlueSky-Bot.git
cd BlueSky-Bot
cp env.example .env
nano .env  # настройте
docker-compose up -d
```

## 🆘 Помощь:

- Логи: `bot-logs` или `journalctl -u bluesky-bot`
- Статус: `bot-status` 
- Issues: https://github.com/YOUR_USERNAME/BlueSky-Bot/issues

---

**Готово!** Бот работает автономно 24/7 🤖 