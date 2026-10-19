# Review agents

Локальные агенты проверки проекта (аналоги стека из матрицы выбора).

| Агент | Аналог | Что делает |
|---|---|---|
| `pr_review_agent.py` | [pr-agent](https://github.com/The-PR-Agent/pr-agent) | Review git diff / последнего коммита через OpenRouter |
| `security_agent.py` | RepoRook-lite | Bandit + pip-audit + эвристики секретов |
| `audit_agent.py` | audit-project | Multi-lens deep audit ключевых `.py` через OpenRouter |

## CI: PR-Agent (GitHub Actions)

Workflow: [`.github/workflows/pr-agent.yml`](../.github/workflows/pr-agent.yml)

Запускает [The-PR-Agent/pr-agent](https://github.com/The-PR-Agent/pr-agent) (бывший `qodo-ai/pr-agent`) на открытие/обновление PR и на комментарий `/review`. Образ закреплён на Docker-тег `pragent/pr-agent:0.48.0-github_action` (не `@main`).

### Секреты и переменные (только в GitHub UI)

**Не коммитьте ключи в репозиторий.** Настроить вручную:

1. Репозиторий → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**:
   - Name: `OPENROUTER_API_KEY`
   - Value: ключ с [openrouter.ai](https://openrouter.ai/)
3. (Опционально) **Variables** → **New repository variable**:
   - Name: `PR_AGENT_MODEL`
   - Value: id модели OpenRouter в OpenAI-compatible виде, напр. `openai/gpt-4o-mini` (дефолт в workflow, если var не задан)

Workflow мапит `OPENROUTER_API_KEY` → `OPENAI_KEY` и шлёт запросы на `https://openrouter.ai/api/v1` (`OPENAI.API_BASE`).

### Поведение без секрета

Если `OPENROUTER_API_KEY` не задан, job падает на шаге **Require OpenRouter API key** с явной ошибкой (review не выполняется). Агенты не могут выставить секрет удалённо — только через UI.

## Запуск

```bash
python agents/run_all.py
# или по отдельности:
python agents/security_agent.py
python agents/pr_review_agent.py
python agents/audit_agent.py
```

Отчёты: `reports/*_agent_report.md` и `.json`.

## Post-deploy smoke (SMOKE-001)

Hermetic post-deploy / dry-run check (no live Bluesky network by default):
import health, `bot_config.json` presence, `DRY_RUN` path sanity, creds fail-fast exit semantics.

```bash
python verify_bot.py --smoke
# or:
python scripts/smoke_check.py
```

| Exit code | Meaning |
|---|---|
| `0` | All smoke checks passed |
| `1` | One or more checks failed |

Optional DNS-only live gate (still no API login; off by default):

```bash
# Unix
SMOKE_LIVE=1 python scripts/smoke_check.py
# Windows PowerShell
$env:SMOKE_LIVE=1; python scripts/smoke_check.py
```

Report: `reports/smoke_report.json`. Full suite (not smoke-only): `python verify_bot.py`.
