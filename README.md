# BlueSky Bot

Автономный AI-бот для [Bluesky](https://bsky.app): посты, engagement, тренды «Актуальные», Thompson-bandit обучение и safety-гейты. Язык контента по умолчанию — **английский** (аудитория Bluesky).

**Аккаунт в проде (пример):** `olj1.bsky.social`  
**SoT кода:** [`app/`](app/) → в деплое flat-копия в `/opt/bluesky-bot/`

---

## Возможности

| Область | Что делает |
|---------|------------|
| **Постинг** | Стратегии из `bot_config` (news / viral / dynamic / theme / poll / insight…), quality pipeline, картинки через OpenRouter |
| **Engagement** | Like / follow / smart engagement с бюджетом и whitelist |
| **Тренды** | Bluesky `getTrends` («Актуальные») → темы для постов + engagement (`trends` / `trends_engagement`) |
| **Обучение** | Thompson bandits: стратегия, формат, engagement; credit 6h/24h; followers delta в reward |
| **Safety** | `SafetyGovernor` (бюджет / followers shock); `llm_retro.dry_run` — LLM только пишет отчёты, пока не сняли dry_run |
| **Устойчивость** | Retry/backoff, state JSON, action ledger, single-instance lock |

Архитектура: composition root `app/bluesky_bot_v2.py` + порты/сервисы (publish, learning, auth, media, health, strategies). Подробнее — [ADR-001](ai_docs/develop/architecture/2026-10-19-layering-and-ports.md), [ADR-002](ai_docs/develop/architecture/ADR-002-policy-learner-bandit.md).

---

## Быстрый старт (Ubuntu 24.04+)

### Вариант 1: одна команда

```bash
curl -sSL https://raw.githubusercontent.com/OLGShow/BlueSky-bot/main/install.sh | bash
```

### Вариант 2: APT

```bash
echo "deb [trusted=yes] https://olgshow.github.io/BlueSky-bot/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/bluesky-bot.list
sudo apt update
sudo apt install bluesky-bot
```

### Локальная разработка

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env   # заполнить BLUESKY_* и OPENROUTER_API_KEY
python verify_bot.py --smoke
```

---

## Настройка

### Секреты — `/etc/bluesky-bot/.env` (или локальный `.env`)

```bash
BLUESKY_HANDLE=your-bot.bsky.social
BLUESKY_PASSWORD=your-app-password   # App Password из настроек Bluesky
OPENROUTER_API_KEY=sk-or-v1-...
BOT_LANGUAGE=en
```

Полный шаблон: [`env.example`](env.example).

### Поведение — `bot_config.json`

SoT в корне репо; на хосте процесс читает **`/opt/bluesky-bot/bot_config.json`** (WorkingDirectory). Зеркало ops: `/etc/bluesky-bot/bot_config.json` — держите в синхроне.

Ключевые блоки:

| Ключ | Назначение |
|------|------------|
| `post_strategies` | Веса стратегий постинга |
| `activity_budget` / `scheduling` | Лимиты и расписание |
| `learning_parameters` / `format_learning` / `engagement_learning` | Bandits + credit |
| `safety_governor` | Freeze при шоке бюджета / фолловеров |
| `llm_retro` | Недельный LLM-ретро; **`dry_run: true`** пока нет статистики |
| `trends` | `getTrends`: посты + engagement |

Критерии снятия `llm_retro.dry_run`: [`ai_docs/develop/plans/2026-10-19-llm-retro-dry-run-criteria.md`](ai_docs/develop/plans/2026-10-19-llm-retro-dry-run-criteria.md).

После правки конфига на хосте:

```bash
# синхронизировать /opt и /etc, затем:
sudo systemctl restart bluesky-bot
```

---

## Карта репозитория

```text
app/                  # SoT runtime Python (не править «только opt»)
  bluesky_bot_v2.py   # composition root / цикл
  strategies/         # extracted post strategies
  trends.py           # getTrends client + theme pick
  trends_engagement.py
  publish_orchestrator.py / learning_orchestrator.py / …
tests/                # hermetic unit tests
packaging/            # .deb build, sync-opt-from-sot.sh
opt/bluesky-bot/      # deploy mirror (синк из app/)
systemd/              # unit SoT для пакета
docs/ops/             # ops / install notes
ai_docs/              # ADR, audits, plans, reports
agents/               # agent playbooks
bot_config.json       # поведение (не секреты)
```

Синк зеркала:

```bash
bash packaging/sync-opt-from-sot.sh
```

---

## Основные модули (`app/`)

| Модуль | Роль |
|--------|------|
| `bluesky_bot_v2.py` | Lifecycle, wiring ports, thin delegates |
| `bot_cycle.py` | Основной цикл |
| `publish_orchestrator.py` | Оркестрация scheduled post |
| `learning_orchestrator.py` | Bandit pick / credit / safety status |
| `policy_learner.py` / `engagement_learner.py` | Thompson sampling |
| `safety_governor.py` / `llm_retro.py` / `follower_tracker.py` | Wave 3 autonomy |
| `trends.py` / `trends_engagement.py` | «Актуальные» |
| `engagement_service.py` / `smart_engagement.py` | Engagement слой |
| `content_service.py` / `quality_pipeline.py` | Контент + quality |
| `auth_service.py` / `media_service.py` / `health_service.py` | Thin-shell сервисы |
| `state_service.py` / `resilience_service.py` | State + retry |
| `verify_bot.py` | Smoke / verification suite |

---

## Ops (systemd)

Типичный хост: unit `bluesky-bot`, cwd `/opt/bluesky-bot`.

| Путь | Что |
|------|-----|
| `/opt/bluesky-bot/` | Код + рабочий `bot_config.json` |
| `/etc/bluesky-bot/` | `.env`, копия конфига |
| `/var/lib/bluesky-bot/` | State (если так настроено пакетом) |
| `/etc/systemd/system/bluesky-bot.service` | Unit |

### Статус и логи

```bash
systemctl status bluesky-bot --no-pager
journalctl -u bluesky-bot --since "10 min ago" --no-pager
```

### Обновление пакета

```bash
sudo apt update && sudo apt install --only-upgrade bluesky-bot
```

### Переустановка / удаление

```bash
sudo apt install --reinstall bluesky-bot
# полное удаление:
sudo apt purge -y bluesky-bot
sudo apt autoremove -y
sudo rm -f /etc/apt/sources.list.d/bluesky-bot.list
```

### Deploy-verify (обязательно после ручного scp)

Не считать «ок» только по `scp` / `active`. Чеклист: [`.cursor/rules/deploy-verify.mdc`](.cursor/rules/deploy-verify.mdc) — SHA256 SoT↔`/opt`, оба конфига, PID ≥ mtime, нет Traceback, smoke import.

---

## Тесты и CI

```bash
python verify_bot.py --smoke
python -m unittest discover -s tests -v
```

- GitHub Actions: unittest на PR/push.
- `.deb` публикуется при `push` в `main` (релевантные пути); версия push-сборок: `3.1.<github_run_number>`.

---

## Документация

| Документ | О чём |
|----------|--------|
| [`docs/ops/`](docs/ops/) | Установка и эксплуатация |
| [`app/README.md`](app/README.md) | SoT ↔ sync |
| [`opt/README.md`](opt/README.md) | Локальное зеркало /opt |
| [`ai_docs/develop/architecture/`](ai_docs/develop/architecture/) | ADR (ports, PolicyLearner) |
| [`ai_docs/develop/audits/`](ai_docs/develop/audits/) | Architecture / layout scores |
| [`ai_docs/develop/plans/`](ai_docs/develop/plans/) | Планы оркестраций |
| Secret rotation | [`ai_docs/develop/architecture/2026-09-15-secret-rotation-runbook.md`](ai_docs/develop/architecture/2026-09-15-secret-rotation-runbook.md) |
| Opkg (не основной путь) | [`packaging/OPKG-ALTERNATIVE.md`](packaging/OPKG-ALTERNATIVE.md) |

---

## Безопасность

- В git только App Password / API keys через `.env` (не коммитить).
- `ALLOW_PICKLE_MIGRATION=0` по умолчанию — без небезопасной миграции pickle.
- Compliant mode: без авто-комментов/ментов (`BLUESKY_COMPLIANT_MODE`).

---

Последнее обновление: 2026-10-19 (Trends «Актуальные», PolicyLearner Wave 1–3, publish/learning orchestrators, architecture ~8.0/10)
