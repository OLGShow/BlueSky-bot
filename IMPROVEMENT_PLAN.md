# План улучшений бота: аналитика роста, окна по времени, прокси/UA

**Дата:** 2026-10-27  
**Статус:** Waves 0–2 done + Wave 3.1 UA live (`proxy.enabled=false`); Wave 3.2 proxy canary pending
**Контекст:** после A+B+C follow growth (`every_n_cycles=2`, `max_follows_per_pass=3`, `require_bio_keyword=false`, commit `f26deb2`) нужно отделить полезный рост подписчиков от шума и риска бана/rate-limit.

**Инварианты:**
- SoT кода: `app/` → sync flat в `/opt/bluesky-bot/`
- Knobs: `bot_config.json` (+ зеркала `etc/`, `opt/`); секреты только в `.env`
- Hermetic tests + deploy-verify (SHA SoT↔`/opt`, оба конфига, PID ≥ mtime, нет Traceback)
- `llm_retro.dry_run` не снимать по этому плану (см. `ai_docs/develop/plans/2026-10-19-llm-retro-dry-run-criteria.md`)

**Уже есть в коде (опора плана):**
| Область | Модули / knobs |
|---------|----------------|
| Follow A+B+C | `app/follow_strategy.py` (`FollowPolicy`, `should_follow_user`), cadence `app/bot_cycle.py`, wiring `app/bluesky_bot_v2.py`, knobs `follow_strategy.*` |
| Followers snapshots | `app/follower_tracker.py` → `learning_followers.json`; reward weight в `learning_parameters` |
| Decisions log | `app/agent_decision_log.py` → `reports/agent_decisions.jsonl` |
| Posting windows only | `bluesky_bot_v2._is_posting_window` + `scheduling.quiet_hours` / `active_windows` (сейчас пустые) |
| Safety | `app/safety_governor.py` (`followers_shock_abs`, budget ratio) |
| HTTP / UA (частично) | `app/http_session.py`; UA захардкожен в `openrouter_adapter.py`, `pollinations_adapter.py` |
| Retry / 429 | `_atproto_execute` / RetryPolicy пути в боте и адаптерах |
| Daily reports | `app/daily_reporting.py` → `reports/daily_*.json` |

**Стоп-критерии (откат A+B+C без нового кода):**  
в `bot_config.follow_strategy` вернуть `every_n_cycles: 5`, `max_follows_per_pass: 1`, `require_bio_keyword: true` → sync `/opt`↔`/etc` → `systemctl restart bluesky-bot`.  
Также стоп при: SafetyGovernor freeze storm, `AccountTakedown`/`Suspended`, рост auth-fail, churn 48h > ~50% новых follows.

---

## Волна 0 — Baseline (до фич-кода)

**Оценка:** ~0.5 дня  
**Цель:** зафиксировать «до/после A+B+C», чтобы волны 1–3 сравнивались честно.

### Шаги
1. Снять с хоста за последние 7 дней: followers series (`learning_followers.json`), outbound follows / likes из `bot.log` / session stats, count `429`/`ERROR`/`Traceback`.
2. Записать артефакт `reports/growth_baseline_YYYY-MM-DD.json` (скрипт `scripts/growth_baseline.py` или одноразовый remote dump).
3. Не менять runtime-поведение.

### Метрики baseline
| Метрика | Источник |
|---------|----------|
| `followers_delta_7d` | `learning_followers.json` |
| `outbound_follows_7d` | `bot.log` / session `follows_made` |
| `likes_7d` | session / decisions |
| `http_429_approx` | journal + `bot.log` |
| `session_errors` | session stats |
| `follow_back_proxy` | `delta / outbound` (грубо, до cohort) |

---

## Волна 1 — Аналитика: returners, bans, этап отказа (P0)

**Оценка:** 2–3 дня  
**Цель:** ответить: A+B+C даёт **удержание** или **одноразовый шум**; на каком **stage** сыпятся отказы API.

### 1.2 Incident / ban / rate-limit telemetry (делать первым)

| # | Шаг | Файлы |
|---|-----|--------|
| 1 | Модуль нормализованных событий: `ts`, `stage`, `op`, `status`/`error_class`, optional `did`/`uri` | **новый** `app/api_incident_log.py` → append `reports/api_incidents.jsonl` |
| 2 | Классификатор: `429`, `AuthRequired`, `AccountTakedown`/`Suspended`, `Forbidden`, `network`, `other` | тот же модуль |
| 3 | Обернуть точки выхода ATProto / engagement / auth / publish | `app/engagement_service.py`, `_atproto_execute` в `app/bluesky_bot_v2.py`, `app/auth_service.py`, `app/publish_orchestrator.py` |
| 4 | Суточная сводка `stage × error_class` | `reports/api_health_daily_YYYY-MM-DD.json` (+ опционально hook в `daily_reporting.py`) |
| 5 | Hermetic tests классификатора | `tests/test_api_incident_log.py` |

**Этапы (`stage`) для оценки follow growth:**  
`auth` → `suggestions` → `get_profile` → `follow` → `like` → `repost` → `create_post` → `get_timeline` / `get_trends`.

### 1.1 Follower cohort / returners (API-осторожно)

| # | Шаг | Файлы |
|---|-----|--------|
| 1 | Расширить трекинг: не только `count`, а периодический snapshot множества DID (или hash-bucket) входящих follows | **новый** `app/follower_analytics.py`; расширить `app/follower_tracker.py` |
| 2 | Классификация: `new` / `returned` (был→ушёл→снова) / `churned` | state `learning_followers_cohort.json` |
| 3 | Суточный отчёт | `reports/followers_daily_YYYY-MM-DD.json`; опционально строка в `app/daily_reporting.py` |
| 4 | Wire редко (раз в N циклов или раз в сутки), с лимитом страниц API + backoff | `app/bot_cycle.py` и/или hook рядом с `refresh_followers_count` в `app/bluesky_bot_v2.py` |
| 5 | Tests на cohort math | `tests/test_follower_analytics.py` |

**Ограничение:** полный список followers дорогой — не каждый цикл; кэш + rate budget.

### 1.3 Связка quality A+B+C ↔ удержание

| # | Шаг | Файлы |
|---|-----|--------|
| 1 | На каждый outbound follow логировать: `source` (suggestions/timeline), `reason` (`quality_ok` / keyword / `liked_enough`), `did` | `app/follow_strategy.py` → `agent_decision_log` или `api_incident_log` domain=`follow` |
| 2 | Через ≥7 дней: join follow events × cohort (остался ли через 48h / 7d) | `scripts/analyze_follow_quality.py` → `reports/follow_quality_*.json` |

### Definition of Done — волна 1
- [ ] Daily: net followers, new/returned/churned (best-effort), outbound follows, incidents by stage
- [ ] Можно ответить: «после soft heuristic — удержание или churn за 48h?»
- [ ] Tests green; deploy-verify на хосте

### Метрики на выходе волны 1
| KPI | Успех |
|-----|--------|
| Incident coverage | follow/like/auth/post появляются в jsonl при ошибках |
| Retention 48h / 7d | считается по cohort (даже если sample ограничен) |
| Stage hotspot | топ-1 stage по 429/ban-class известен |
| A+B+C signal | доля follows с `reason=quality_ok` vs `liked_enough` vs keyword |

---

## Волна 2 — Лимиты по времени суток (P1)

**Оценка:** ~1 день  
**Цель:** не долбить follow/like в часы жёсткого throttling. Постинг уже умеет quiet/active — **расширить на engagement/follow**.

**Зависимость:** желательно ≥3–5 дней телеметрии волны 1.2, чтобы окна взять из пиков `429_by_hour`, а не угадать. Допускается консервативный дефолт UTC night сразу.

### 2.1 Конфиг

В `bot_config.json` расширить `scheduling` (или соседний блок `traffic_windows`):

```json
"scheduling": {
  "timezone": "UTC",
  "quiet_hours": [],
  "active_windows": [],
  "engagement_quiet_hours": [2, 3, 4, 5],
  "follow_quiet_hours": [2, 3, 4, 5],
  "follow_active_windows": [[7, 23]]
}
```

Зеркала: `etc/bluesky-bot/bot_config.json`, `opt/bluesky-bot/bot_config.json` (+ live `/opt` и `/etc` на хосте).

### 2.2 Код

| # | Шаг | Файлы |
|---|-----|--------|
| 1 | Вынести `_is_posting_window` → общий helper | **новый** `app/schedule_windows.py` (`is_allowed(now, kind=post\|engagement\|follow)`) |
| 2 | Рефактор бота на helper | `app/bluesky_bot_v2.py` |
| 3 | В `BotCycleRunner.tick`: skip follow/engagement вне окна + log | `app/bot_cycle.py` (+ port при необходимости) |
| 4 | Опционально soft-cap: в «серой» зоне `max_follows_per_pass=1` вместо полного skip | `FollowPolicy` + cycle |
| 5 | Tests окон (зачаток уже в `verify_bot.test_scheduling`) | `tests/test_schedule_windows.py`; обновить cycle tests |

### Definition of Done — волна 2
- [ ] 0 (или soft-cap) follow/like в quiet hours
- [ ] Постинг по своим окнам без регрессии
- [ ] Конфиг крутится без правки кода

### Метрики на выходе волны 2
| KPI | Успех через 7 дней |
|-----|-------------------|
| `follows_by_hour` | провал в quiet |
| `429_by_hour` | снижение в бывших пиковых часах |
| Net followers / day | не хуже волны 1 (лучше — если резали шум) |
| Outbound follows / day | может чуть ↓ — ок, если retention ↑ |

---

## Волна 3 — User-Agent + прокси (P2)

**Оценка:** 2–3 дня (+ canary)  
**Цель:** снизить fingerprint при росте RPS после A+B+C.  
**Риск:** смена IP mid-session ломает Bluesky auth — **только sticky**, не per-request.

**Зависимость:** после волн 1+2; сначала UA, потом proxy canary.

### 3.1 User-Agent (низкий риск)

| # | Шаг | Файлы |
|---|-----|--------|
| 1 | Пул UA + sticky на процесс / сутки | **новый** `app/http_identity.py` |
| 2 | Подключить к non-ATProto HTTP | `app/openrouter_adapter.py`, `app/pollinations_adapter.py`, RSS/`app/http_session.py` |
| 3 | Knobs | `bot_config.http_identity`: `user_agents[]`, `rotate: daily\|never` |
| 4 | Tests | `tests/test_http_identity.py` |

### 3.2 Прокси (средний/высокий риск)

| # | Шаг | Файлы |
|---|-----|--------|
| 1 | Конфиг + secrets: список URL, режим `sticky_session` (на жизнь процесса / на N часов) | `bot_config.proxy` + env `PROXY_URLS` (**не в git**) |
| 2 | Factory session с proxy | `app/http_session.py`; ATProto — только если transport поддерживается без ломки session |
| 3 | Healthcheck при старте; failover на network errors (**не** на 401) | stage=`proxy` в `api_incident_log` |
| 4 | Ротация: старт / расписание / после N network fail — **не** на каждый follow | `app/proxy_pool.py` (или внутри `http_identity`) |
| 5 | Feature-flag `proxy.enabled: false` по умолчанию | конфиг |
| 6 | Canary 48h на хосте с флагом on + усиленный мониторинг auth | ops + deploy-verify |

### Definition of Done — волна 3
- [ ] UA rotation доказана логами на AI/RSS трафике
- [ ] Proxy за флагом; canary 48h без роста auth resets
- [ ] Откат = `proxy.enabled=false` + restart

### Метрики на выходе волны 3
| KPI | Успех |
|-----|--------|
| `429` rate | ≤ baseline волны 2 |
| Auth / session re-login count | не выше baseline |
| Network errors on proxy | стабильный failover, без флапа |
| Follow/post success rate | без регрессии |

---

## Сводный порядок работ

```text
W0  Baseline dump (лог + followers)
 ↓
W1.2 Incident log by stage          ← быстрый фундамент
 ↓
W1.1 Cohort / returners             ← API-осторожно
 ↓
W2  Schedule windows (follow/engagement)  ← по пикам 429 или UTC night default
 ↓
W1.3 Follow quality join (≥7d data)
 ↓
W3.1 UA pool
 ↓
W3.2 Sticky proxy canary (flag off → on 48h)
```

**Параллелить можно:** W1.2 ∥ черновик конфига W2; W1.1 ∥ тесты `schedule_windows`.

**Не параллелить с продом без флага:** W3.2 proxy.

---

## Сводная таблица KPI (14 дней после полного плана)

| KPI | Как мерить | Цель |
|-----|------------|------|
| Net followers / day | `learning_followers` / cohort daily | ↑ vs ~1.6/day baseline; без взрыва 429 |
| Outbound follows / day | session + follow log | ожидаемо ↑ после A+B+C (~10–15), затем может ↓ после W2 |
| Retention 48h / 7d | cohort analytics | retained ≫ churn «шума» |
| Incidents by stage | `reports/api_incidents.jsonl` | hotspot известен; доля follow-stage 429 не растёт после W2 |
| 429 by hour | api health daily | провал в quiet после W2 |
| Auth/session resets | incident `auth` | не хуже после W3 |
| SafetyGovernor freezes | journal / governor | без штормов |

---

## Оценка трудозатрат

| Волна | Оценка |
|-------|--------|
| W0 Baseline | 0.5d |
| W1 Analytics | 2–3d |
| W2 Time windows | 1d |
| W3 UA + proxy | 2–3d (+ canary) |

---

## Связанные документы

- Follow growth A+B+C: `bot_config.json` → `follow_strategy`
- Dry-run LLM retro: `ai_docs/develop/plans/2026-10-19-llm-retro-dry-run-criteria.md`
- Deploy-verify: `.cursor/rules/deploy-verify.mdc`
- Architecture: `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`

---

## Следующий исполняемый шаг

Начать **W1.2** — `app/api_incident_log.py` + wrap `_atproto_execute` / engagement follow+like + daily summary; затем deploy-verify на `192.168.2.6`.
