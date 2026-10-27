# План исполнения: Improvement Wave 0 + Wave 1 (Analytics)

**Created:** 2026-10-27  
**Orchestration:** `orch-2026-10-27-improvement-w0w1`  
**Status:** 🟢 Ready  
**Product plan (SoT):** `IMPROVEMENT_PLAN.md`  
**Goal:** Зафиксировать baseline роста и внедрить аналитику волны 1 (инциденты → cohort → quality logging), без изменения поведения A+B+C сверх логирования.  
**Total Tasks:** 9  
**Priority:** High  

## Scope этого цикла

**Включено:**
- Волна 0 — Baseline dump с хоста
- Волна 1 — Analytics only, порядок: **1.2 → 1.1 → 1.3**

**Отложено (не в этом orchestration):**
- Волна 2 — Schedule windows для follow/engagement
- Волна 3 — UA pool + sticky proxy canary

## Инварианты

- SoT кода: `app/` → sync flat в `/opt/bluesky-bot/`
- Hermetic tests + deploy-verify (SHA SoT↔`/opt`, оба конфига, PID ≥ mtime, нет Traceback)
- **Не снимать** `llm_retro.dry_run` (см. `ai_docs/develop/plans/2026-10-19-llm-retro-dry-run-criteria.md`)
- Host baseline / deploy: `192.168.2.6`, unit `bluesky-bot`, cwd `/opt/bluesky-bot`

## Tasks Overview

1. **W0-001** → Baseline dump с хоста  
   - Priority: Critical  
   - Complexity: Simple  
   - Dependencies: None  

2. **W1-002** → Модуль api_incident_log + классификатор  
   - Priority: Critical  
   - Complexity: Moderate  
   - Dependencies: W0-001  

3. **W1-003** → Wiring инцидентов в ATProto / engagement / auth / publish  
   - Priority: Critical  
   - Complexity: Moderate  
   - Dependencies: W1-002  

4. **W1-004** → Daily api_health + hermetic tests инцидентов  
   - Priority: High  
   - Complexity: Moderate  
   - Dependencies: W1-003  

5. **W1-005** → Follower cohort / returners (модуль + state)  
   - Priority: High  
   - Complexity: Complex  
   - Dependencies: W1-004  

6. **W1-006** → Wiring cohort + daily report + tests  
   - Priority: High  
   - Complexity: Moderate  
   - Dependencies: W1-005  

7. **W1-007** → Follow quality logging на outbound follow  
   - Priority: High  
   - Complexity: Moderate  
   - Dependencies: W1-006  

8. **W1-008** → Скрипт analyze_follow_quality (join ≥7d)  
   - Priority: Medium  
   - Complexity: Moderate  
   - Dependencies: W1-007  

9. **W1-009** → Wave 1 DoD: deploy-verify на хосте  
   - Priority: Critical  
   - Complexity: Simple  
   - Dependencies: W1-004, W1-006, W1-007  

## Dependencies Graph

```text
W0-001
  └─► W1-002
        └─► W1-003
              └─► W1-004
                    └─► W1-005
                          └─► W1-006
                                └─► W1-007
                                      ├─► W1-008
                                      └─► W1-009 ◄── (also W1-004, W1-006)
```

**Порядок исполнения (sequential):**  
`W0-001 → W1-002 → W1-003 → W1-004 → W1-005 → W1-006 → W1-007 → W1-008 → W1-009`

## Progress (updated by orchestrator)

- ✅ W0-001: Baseline dump с хоста (Completed)
- 🔄 W1-002: Модуль api_incident_log + классификатор (In Progress)
- ⏳ W1-003: Wiring инцидентов в call sites (Pending)
- ⏳ W1-004: Daily api_health + tests (Pending)
- ⏳ W1-005: Follower cohort / returners (Pending)
- ⏳ W1-006: Wiring cohort + daily + tests (Pending)
- ⏳ W1-007: Follow quality logging (Pending)
- ⏳ W1-008: analyze_follow_quality script (Pending)
- ⏳ W1-009: Deploy-verify Wave 1 (Pending)

---

## Task Details

### W0-001: Baseline dump с хоста

**Priority:** Critical | **Complexity:** Simple | **Dependencies:** None

**Цель:** Зафиксировать «до/после A+B+C» без изменения runtime.

**Шаги:**
1. С хоста `192.168.2.6` за последние 7 дней снять: `learning_followers.json`, outbound follows / likes из `bot.log` / session stats, count `429` / `ERROR` / `Traceback`.
2. Записать артефакт `reports/growth_baseline_YYYY-MM-DD.json` (скрипт `scripts/growth_baseline.py` или одноразовый remote dump).
3. Не менять runtime-поведение.

**Файлы:** `scripts/growth_baseline.py` (опционально), `reports/growth_baseline_*.json`

**Acceptance:**
- [ ] JSON baseline содержит метрики: `followers_delta_7d`, `outbound_follows_7d`, `likes_7d`, `http_429_approx`, `session_errors`, `follow_back_proxy`
- [ ] Runtime / config на хосте не изменены

**Agent:** worker (+ shell ops)

---

### W1-002: Модуль api_incident_log + классификатор

**Priority:** Critical | **Complexity:** Moderate | **Dependencies:** W0-001

**Цель:** Нормализованные события инцидентов API (фундамент волны 1.2).

**Шаги:**
1. Новый модуль `app/api_incident_log.py` → append `reports/api_incidents.jsonl`
2. Поля события: `ts`, `stage`, `op`, `status`/`error_class`, optional `did`/`uri`
3. Классификатор: `429`, `AuthRequired`, `AccountTakedown`/`Suspended`, `Forbidden`, `network`, `other`

**Stages:** `auth` → `suggestions` → `get_profile` → `follow` → `like` → `repost` → `create_post` → `get_timeline` / `get_trends`

**Файлы:** `app/api_incident_log.py`

**Acceptance:**
- [ ] Модуль пишет jsonl с нормализованными полями
- [ ] Классификатор покрывает перечисленные error_class
- [ ] SoT только в `app/`

**Agent:** worker

---

### W1-003: Wiring инцидентов в call sites

**Priority:** Critical | **Complexity:** Moderate | **Dependencies:** W1-002

**Цель:** Обернуть точки выхода ATProto / engagement / auth / publish.

**Файлы:**
- `app/engagement_service.py`
- `_atproto_execute` в `app/bluesky_bot_v2.py`
- `app/auth_service.py`
- `app/publish_orchestrator.py`

**Acceptance:**
- [ ] Ошибки follow/like/auth/post попадают в jsonl с корректным `stage`
- [ ] Успешный happy-path не ломается (best-effort log on error)
- [ ] Нет снятия `llm_retro.dry_run`

**Agent:** worker

---

### W1-004: Daily api_health + hermetic tests инцидентов

**Priority:** High | **Complexity:** Moderate | **Dependencies:** W1-003

**Цель:** Суточная сводка `stage × error_class` + тесты классификатора.

**Шаги:**
1. `reports/api_health_daily_YYYY-MM-DD.json` (+ опционально hook в `daily_reporting.py`)
2. Hermetic tests: `tests/test_api_incident_log.py`

**Acceptance:**
- [ ] Daily summary строится из jsonl
- [ ] Tests green (hermetic)
- [ ] Можно назвать топ stage по 429/ban-class на тестовых фикстурах

**Agent:** worker → test-writer → test-runner

---

### W1-005: Follower cohort / returners (модуль + state)

**Priority:** High | **Complexity:** Complex | **Dependencies:** W1-004

**Цель:** Периодический snapshot множества DID + классификация new/returned/churned (волна 1.1).

**Шаги:**
1. Новый `app/follower_analytics.py`; расширить `app/follower_tracker.py`
2. State: `learning_followers_cohort.json`
3. Классы: `new` / `returned` / `churned`

**Ограничение:** полный список followers дорогой — не каждый цикл; кэш + rate budget.

**Acceptance:**
- [ ] Cohort math корректно классифицирует new/returned/churned на фикстурах
- [ ] State файл определён и сериализуется стабильно

**Agent:** worker

---

### W1-006: Wiring cohort + daily report + tests

**Priority:** High | **Complexity:** Moderate | **Dependencies:** W1-005

**Цель:** Редкий вызов API + суточный отчёт + hermetic tests.

**Шаги:**
1. Wire раз в N циклов или раз в сутки, лимит страниц + backoff — `app/bot_cycle.py` и/или hook рядом с `refresh_followers_count` в `app/bluesky_bot_v2.py`
2. `reports/followers_daily_YYYY-MM-DD.json`; опционально строка в `daily_reporting.py`
3. `tests/test_follower_analytics.py`

**Acceptance:**
- [ ] Wiring не дергает полный список каждый цикл
- [ ] Daily report содержит net / new / returned / churned (best-effort)
- [ ] Tests green

**Agent:** worker → test-writer → test-runner

---

### W1-007: Follow quality logging на outbound follow

**Priority:** High | **Complexity:** Moderate | **Dependencies:** W1-006

**Цель:** Связка A+B+C quality ↔ удержание (волна 1.3, часть логирования).

**Шаги:**
1. На каждый outbound follow логировать: `source` (suggestions/timeline), `reason` (`quality_ok` / keyword / `liked_enough`), `did`
2. Через `agent_decision_log` или `api_incident_log` domain=`follow` — `app/follow_strategy.py`

**Acceptance:**
- [ ] Каждый успешный outbound follow пишет source + reason + did
- [ ] Можно посчитать долю `quality_ok` vs `liked_enough` vs keyword

**Agent:** worker

---

### W1-008: Скрипт analyze_follow_quality

**Priority:** Medium | **Complexity:** Moderate | **Dependencies:** W1-007

**Цель:** Offline join follow events × cohort (остался ли через 48h / 7d). Полный 7d join на проде — после накопления данных; скрипт и формат отчёта — сейчас.

**Файлы:** `scripts/analyze_follow_quality.py` → `reports/follow_quality_*.json`

**Acceptance:**
- [ ] Скрипт читает follow events + cohort state
- [ ] Пишет отчёт с retention 48h / 7d (или placeholder metrics при недостатке данных)
- [ ] Hermetic / dry run на фикстурах без сети

**Agent:** worker

---

### W1-009: Wave 1 DoD — deploy-verify на хосте

**Priority:** Critical | **Complexity:** Simple | **Dependencies:** W1-004, W1-006, W1-007

**Цель:** Закрыть Definition of Done волны 1 по чеклисту deploy-verify.

**Шаги:**
1. Sync затронутых модулей SoT `app/` → `/opt/bluesky-bot/`
2. SHA256 local ↔ remote для каждого touched файла
3. Оба конфига: `/opt` и `/etc` (не менять dry_run)
4. `systemctl restart bluesky-bot`; PID start ≥ mtime; нет Traceback в journal
5. Smoke: import новых модулей; assert wiring strings в `bluesky_bot_v2.py`

**Acceptance (DoD волны 1):**
- [ ] Daily: net followers, new/returned/churned (best-effort), outbound follows, incidents by stage — пути артефактов на месте
- [ ] Можно ответить: «после soft heuristic — удержание или churn за 48h?» (инструменты готовы; полный ответ после ≥48h данных)
- [ ] Tests green; deploy-verify green на `192.168.2.6`
- [ ] Hash-таблица local vs remote в отчёте оркестрации

**Agent:** worker (ops) + test-runner

---

## Architecture Decisions

- Сначала телеметрия отказов (1.2), затем cohort (1.1), затем quality join (1.3) — как в product plan.
- Incident log — append-only jsonl; daily health — агрегация offline/on tick reporting.
- Cohort API — редкий polling с budget; не в каждый cycle.
- Quality logging пишет сразу; analyze script допускает «мало данных» без падения.
- Wave 2/3 **не** входят в этот цикл даже как черновик knobs на проде.

## Risks

| Риск | Митигация |
|------|-----------|
| Cohort API rate-limit | лимит страниц, backoff, редкий schedule |
| Шум в incident log на happy path | log primarily on errors / classified failures |
| Deploy без hash-check | обязательный deploy-verify checklist |
| Случайный lift dry_run | явный инвариант; не трогать `llm_retro` |

## Verification Strategy

После каждой task с кодом: hermetic tests → (для W1-009) полный deploy-verify.  
Не объявлять «задеплоено» без live SSH evidence в том же turn.

## Next Steps

Execute: `/orchestrate execute orch-2026-10-27-improvement-w0w1`  
Первая задача: **W0-001** (baseline), вторая: **W1-002** (incident log).
