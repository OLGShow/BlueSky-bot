# Plan: Layout FIX (Stages 1–4) + God Object Structural Prep

**Created:** 2026-10-19 14:33
**Orchestration:** orch-2026-10-19-14-33-layout-godobj
**Status:** 🟢 Ready
**Goal:** Закрыть layout hygiene Stages 1–4 (repo-organizer) и начать структурную подготовку к декомпозиции God Object `AutonomousBlueskyBotV2`: ADR(s) + первый extraction slice (ports для EngagementService) + skeleton strategy registry; остальное — в follow-up plan.
**Priority:** High (layout Low–Med; architecture Critical/High)
**Total Tasks:** 9
**Estimated Time:** ~10h
**Mode:** documentation plan (`enabled.plans = true`)

## Sources
- `ai_docs/develop/audits/2026-10-19-architecture-and-layout.md`
- repo-organizer AUDIT (Stages 1–4 FIX; **не** Stage 5B untrack opt py)
- senior-reviewer: Health 5.5/10; God Object ~4k LOC; EngagementService(bot)/ContentService(bot)

## Constraints
- ≤10 задач в этом цикле (этот план: **9**)
- **Не делать:** untrack `opt/*.py`, трогать `.cursor/`, secrets, flatten `ai_docs`
- Layout: только Stages 1–4
- God Object: полный split **не** в этом цикле — только ADR + ports slice + strategy skeleton
- Commits только по явному запросу пользователя (не часть этого плана)
- Verify после code-задач: `python verify_bot.py --smoke` и `python -m unittest discover -s tests -v`

## Tasks Overview

| # | ID | Name | Priority | Complexity | Est. |
|---|-----|------|----------|------------|------|
| 1 | LAY-001 | Remove tracked root `__pycache__/` | Low | Simple | 0.25h |
| 2 | LAY-002 | Align `opt/.../env.example` with root SoT | Low | Simple | 0.5h |
| 3 | LAY-003 | Single systemd unit SoT + build-deb `cp` + LF | Low–Med | Moderate | 1h |
| 4 | LAY-004 | Add `opt/README.md` (mirror vs local runtime) | Low | Simple | 0.5h |
| 5 | ADR-001 | ADR layering + ports + phased decomposition | Critical | Moderate | 1.5h |
| 6 | REF-001 | Define engagement ports (Protocols) | High | Moderate | 1.5h |
| 7 | REF-002 | Refactor EngagementService onto ports | High | Complex | 2h |
| 8 | REF-003 | Strategy registry skeleton + follow-up plan | Medium | Moderate | 1.5h |
| 9 | TEST-001 | Tests + smoke/unittest verification gate | High | Moderate | 1.5h |

**Total estimated:** ~10.25h

## Dependencies Graph

```
LAY-001 ──┐
LAY-002 ──┤── (layout parallel OK) ──┐
LAY-003 ──┤                          │
LAY-004 ──┘                          ├──→ TEST-001
                                     │
ADR-001 ──→ REF-001 ──→ REF-002 ─────┤
         └──────────→ REF-003 ───────┘
```

- **Layout (LAY-001…004):** независимы друг от друга; можно параллелить
- **ADR-001** блокирует REF-001 / REF-003 (контракты и границы слоёв)
- **REF-002** после REF-001 (ports → wiring)
- **REF-003** после ADR-001; можно параллельно с REF-001/002, если не трогает те же строки `bluesky_bot_v2.py` (иначе сериализовать после REF-002)
- **TEST-001** последним после всех code/docs изменений этого цикла

### Recommended execution order

1. LAY-001 ∥ LAY-002 ∥ LAY-004  
2. LAY-003  
3. ADR-001  
4. REF-001 → REF-002  
5. REF-003 (после ADR; предпочтительно после REF-002 если оба правят bot)  
6. TEST-001  

---

## Progress (updated by orchestrator)

- ✅ LAY-001: Remove tracked `__pycache__/` (Completed)
- ✅ LAY-002: Align opt env.example (Completed)
- ✅ LAY-003: Systemd SoT + build-deb cp (Completed)
- ✅ LAY-004: opt/README.md (Done)
- ✅ ADR-001: Architecture ADR(s) (Completed)
- ✅ REF-001: Engagement ports (Completed)
- ✅ REF-002: EngagementService ports wiring (Completed)
- ✅ REF-003: Strategy registry skeleton + follow-up (Completed)
- ✅ TEST-001: Verification gate (Completed)

---

## Task Details

### LAY-001: Remove tracked root `__pycache__/`
- **Priority:** Low | **Complexity:** Simple | **Deps:** none
- **Files:** root `__pycache__/*.pyc` (tracked), `.gitignore`
- **Actions:**
  1. `git rm -r --cached __pycache__` (или удалить tracked `.pyc`)
  2. Убедиться, что `.gitignore` уже содержит `__pycache__/` и `*.py[cod]` (сейчас есть — не ослаблять)
  3. Не коммитить секреты; не трогать runtime caches вне git
- **Acceptance:**
  - `git ls-files '__pycache__' '*/__pycache__/*'` пуст
  - `.gitignore` ловит `__pycache__/`
  - Исходники приложения не затронуты

### LAY-002: Align `opt/bluesky-bot/env.example` with root
- **Priority:** Low | **Complexity:** Simple | **Deps:** none
- **Files:** `env.example` (SoT), `opt/bluesky-bot/env.example`, optionally `packaging/sync-opt-from-sot.sh`
- **Actions:**
  1. Сверить root `env.example` vs `opt/bluesky-bot/env.example`
  2. Выровнять opt-копию с root **или** расширить `sync-opt-from-sot.sh` для копирования `env.example` (и при необходимости отметить `requirements` / `bot_config` как sync targets — без untrack py)
  3. Не менять secret values; только example template
- **Acceptance:**
  - Содержимое opt `env.example` = root SoT (byte-identical или документированный sync)
  - Sync-скрипт (если расширен) идемпотентен и упомянут в комментарии/README

### LAY-003: Single systemd unit SoT + build-deb `cp` + LF
- **Priority:** Low–Med | **Complexity:** Moderate | **Deps:** none
- **Decision (SoT):** `systemd/bluesky-bot.service` — единый SoT для разработчиков; `etc/systemd/system/bluesky-bot.service` либо удаляется из роли SoT и становится копией/ссылкой через sync, либо заменяется заметкой «generated/synced from systemd/». Сейчас оба файла идентичны.
- **Files:** `systemd/bluesky-bot.service`, `etc/systemd/system/bluesky-bot.service`, `packaging/build-deb.sh`
- **Actions:**
  1. Зафиксировать SoT в `systemd/bluesky-bot.service`
  2. В `build-deb.sh` заменить heredoc (`cat << 'UNIT'`) на `cp` из SoT в stage `etc/systemd/system/`
  3. Нормализовать LF (без CRLF) в unit-файле(ах)
  4. Синхронизировать/документировать вторую копию под `etc/`
- **Acceptance:**
  - Один явный SoT; нет расходящегося heredoc в build-deb
  - `packaging/build-deb.sh` копирует unit из SoT
  - Unit файл(ы) с LF line endings
  - Поведение unit (ExecStart, paths, User) не регрессирует относительно текущего содержимого

### LAY-004: Add `opt/README.md`
- **Priority:** Low | **Complexity:** Simple | **Deps:** none
- **Files:** `opt/README.md` (new)
- **Actions:**
  1. Описать: tracked mirror (`opt/bluesky-bot/*.py` synced from `app/` SoT) vs local-only (venv, logs — gitignored)
  2. Краткая заметка про optional local log cleanup
  3. Ссылка на `packaging/sync-opt-from-sot.sh` / `app/README.md`
  4. Явно: **не** untrack `opt/*.py` в этом цикле
- **Acceptance:**
  - `opt/README.md` существует и объясняет mirror vs runtime
  - Нет инструкций, требующих Stage 5B

### ADR-001: ADR layering + ports + phased decomposition
- **Priority:** Critical | **Complexity:** Moderate | **Deps:** none
- **Files (new):**
  - `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md` (обязательный ADR)
  - опционально второй ADR-фрагмент в том же файле или `...-post-strategy-registry.md` если объём велик
- **Content must cover:**
  1. Слои: orchestration (`AutonomousBlueskyBotV2`) → application services → ports → adapters (ATProto/HTTP/LLM)
  2. Правило: **services must not take `bot`** — только узкие Protocols/dataclasses
  3. Целевые порты для Engagement (client, ledger, budget, dry-run, stats) и направление для ContentService (follow-up)
  4. Strategy registry (OCP) для post creation paths
  5. Фазы декомпозиции God Object (этот цикл = Phase 0/1; rest → follow-up)
  6. Упомянуть будущие: RetryPolicy wiring, unified quality pipeline, shared HTTP session — **out of scope** сейчас
- **Acceptance:**
  - ADR лежит в `ai_docs/develop/architecture/`
  - Содержит Decision / Consequences / Migration phases
  - Worker/refactor могут реализовывать REF-* без догадок о границах

### REF-001: Define engagement ports (Protocols)
- **Priority:** High | **Complexity:** Moderate | **Deps:** ADR-001
- **Files:** новый модуль напр. `app/ports/engagement.py` или `app/engagement_ports.py` (следовать существующим naming conventions), возможно `__init__.py` если пакет
- **Actions:**
  1. Ввести `typing.Protocol` (или ABC) для зависимостей, которые сейчас читаются с `self.bot` в `EngagementService`: config/mode, activity_budget, action_ledger, liked/reposted sets, bluesky_client, dry_run + dry_run_log, session_stats, audit logger usage
  2. Не менять поведение; только контракты + тонкие adapter/facade типы при необходимости
  3. Документировать mapping Protocol ↔ bot attributes в docstring или ADR cross-link
- **Acceptance:**
  - Порты импортируемы без импорта `bluesky_bot_v2`
  - Нет циклических импортов services → bot
  - Unit-тесты на «duck typing» / fake ports (минимум в TEST-001)

### REF-002: Refactor EngagementService onto ports
- **Priority:** High | **Complexity:** Complex | **Deps:** REF-001
- **Files:** `app/engagement_service.py`, wiring в `app/bluesky_bot_v2.py` (минимальный glue)
- **Actions:**
  1. Заменить `EngagementService.__init__(self, bot)` на инъекцию портов (или один composition root object, собранный ботом)
  2. Сохранить публичное поведение `like` / `repost` / follow helpers
  3. Bot остаётся composition root: собирает ports из своих полей и передаёт в service
  4. **Не** рефакторить ContentService в этом цикле (только отметить в follow-up)
- **Acceptance:**
  - `EngagementService` не хранит `self.bot`
  - Существующие вызовы из bot обновлены
  - Поведение like/repost/budget/ledger/dry-run эквивалентно (покрыто тестами)
  - `python -m unittest discover -s tests -v` зелёный после TEST-001

### REF-003: Strategy registry skeleton + follow-up plan
- **Priority:** Medium | **Complexity:** Moderate | **Deps:** ADR-001
- **Files:**
  - новый skeleton напр. `app/post_strategies.py` (registry + Protocol `PostStrategy`, 0–1 no-op/wrapper strategy)
  - опциональная тонкая точка расширения в bot **без** полного переноса create_scheduled_post / media helpers
  - `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md` (deferred work)
- **Actions:**
  1. Skeleton registry: register/get/list; Protocol с async `execute` или `create`
  2. Не переносить все private post methods (~create_post_with_image и т.д.) — только каркас + 1 адаптер-заглушка или thin wrap одного пути
  3. Follow-up plan: ContentService ports, full strategy migration, RetryPolicy wiring, unified QualityGate vs ContentQualityAnalyzer, shared ClientSession, domain tests
- **Acceptance:**
  - Registry модуль существует, тестируем register/get
  - Bot либо не ломается без registry, либо использует opt-in skeleton без смены runtime paths
  - Follow-up plan file создан со списком отложенных фаз

### TEST-001: Tests + verification gate
- **Priority:** High | **Complexity:** Moderate | **Deps:** LAY-* (layout non-blocking), REF-001, REF-002, REF-003
- **Files:** `tests/` (новые/обновлённые hermetic tests)
- **Actions:**
  1. Тесты на ports + EngagementService с fake ports
  2. Тесты на strategy registry skeleton
  3. Прогон verify:
     - `python verify_bot.py --smoke`
     - `python -m unittest discover -s tests -v`
  4. Зафиксировать результаты в progress/report notes
- **Acceptance:**
  - Оба verify-команды exit 0
  - Новые тесты покрывают REF-001/002/003 happy paths + 1–2 edge (budget exhausted, duplicate ledger key)
  - Layout-only изменения не требуют новых Python tests, но не ломают smoke

---

## Architecture Decisions (this cycle)

1. **Layout SoT:** root `app/` + root `env.example` + `systemd/bluesky-bot.service`; `opt/` = tracked mirror + local runtime (documented)
2. **DIP start:** Engagement first (highest coupling via `bot`); ContentService deferred
3. **Composition root:** `AutonomousBlueskyBotV2` остаётся оркестратором в Phase 1; не «убиваем» God Object целиком
4. **Out of scope:** Stage 5B, RetryPolicy full wiring, quality pipeline merge, session unification

## Implementation Notes

- Сохранять ацикличный граф: services/ports **не** импортируют `bluesky_bot_v2`
- Предпочтительны `typing.Protocol` + structural typing для минимального churn
- При конфликтах правок в `bluesky_bot_v2.py`: порядок REF-002 затем REF-003
- Worker: следовать `.cursor/skills/architecture-principles` и `code-quality-standards`
- Documenter: отчёт в `ai_docs/develop/reports/` после цикла

## Risks

| Risk | Mitigation |
|------|------------|
| Скрытые обращения EngagementService к undocumented bot attrs | Inventory в REF-001; grep `self.bot.` |
| Регрессия engagement в dry-run/budget | Fake ports + TEST-001 edge cases |
| Двойной systemd drift после SoT | build-deb только `cp`; вторая копия sync/doc |
| Scope creep God Object | Жёсткий cap: только engagement ports + strategy skeleton |

## Deferred → Follow-up Plan

Файл: `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md` (создаётся в REF-003)

Ожидаемое содержание (черновик):
- ContentService ports
- Full post strategy migration (scheduled / media / link preview)
- RetryPolicy on all outbound I/O
- Unified quality pipeline
- Shared aiohttp session injection
- Further slices of `bluesky_bot_v2.py` (state, scheduling, learning hooks)

## Verify Commands (mandatory gate)

```bash
python verify_bot.py --smoke
python -m unittest discover -s tests -v
```

## Next Steps

Execute: `/orchestrate execute orch-2026-10-19-14-33-layout-godobj`  
Or: `/orchestrate execute` (latest active)
