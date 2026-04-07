# BlueSky Bot

AI-бот для Bluesky с автопостингом, engagement-логикой, защитой от дублей, retry/backoff и безопасным хранением состояния.

## Быстрый старт (Ubuntu 24.04+)

### Вариант 1: одна команда

```bash
curl -sSL https://raw.githubusercontent.com/OLGShow/BlueSky-bot/main/install.sh | bash
```

### Вариант 2: вручную через APT

```bash
echo "deb [trusted=yes] https://olgshow.github.io/BlueSky-bot/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/bluesky-bot.list
sudo apt update
sudo apt install bluesky-bot
```

## Настройка после установки

Если установщик не спросил креды (или нужно поменять):

```bash
sudo nano /etc/bluesky-bot/.env
sudo systemctl restart bluesky-bot
```

Минимально обязательные переменные:

```bash
BLUESKY_HANDLE=your-bot.bsky.social
BLUESKY_PASSWORD=your-app-password
```

## Актуальные команды

### Статус и логи

```bash
systemctl status bluesky-bot --no-pager
journalctl -u bluesky-bot --since "10 min ago" --no-pager
```

### Обновление

```bash
sudo apt update && sudo apt upgrade
```

Точечно:

```bash
sudo apt install --only-upgrade bluesky-bot
```

### Переустановка

```bash
sudo apt install --reinstall bluesky-bot
```

### Полное удаление

```bash
sudo apt purge -y bluesky-bot
sudo apt autoremove -y
sudo rm -f /etc/apt/sources.list.d/bluesky-bot.list
sudo apt update
```

Проверка, что удалено:

```bash
dpkg -l | grep bluesky-bot || echo "package removed"
test -d /opt/bluesky-bot || echo "/opt removed"
test -d /etc/bluesky-bot || echo "/etc removed"
test -d /var/lib/bluesky-bot || echo "/var/lib removed"
systemctl status bluesky-bot 2>/dev/null || echo "service removed"
```

## Пути установки пакета

- Код: `/opt/bluesky-bot/`
- Конфиг: `/etc/bluesky-bot/`
- State-файлы: `/var/lib/bluesky-bot/`
- Service unit: `/etc/systemd/system/bluesky-bot.service`

## Что внутри

- `bluesky_bot_v2.py` — основной runtime
- `state_service.py` — JSON state, action ledger, session store, locks
- `engagement_service.py` — like/repost/follow слой
- `resilience_service.py` — retry/backoff/circuit breaker
- `content_service.py` — генерация контента и пост-проверки
- `verify_bot.py` — локальный verification suite

## CI/CD

- Пакет `.deb` публикуется автоматически при `push` в `main` (по релевантным путям).
- Версия push-сборок: `3.1.<github_run_number>`.

## Полезно

- Для сетапа пакета: `packaging/deb/`
- Для альтернативного opkg-сценария (не основной путь): `packaging/OPKG-ALTERNATIVE.md`

---

Последнее обновление: Апрель 2026
