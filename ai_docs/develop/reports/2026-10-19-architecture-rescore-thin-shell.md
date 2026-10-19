# Report: Architecture Re-score + Thin Bot Shell

**Date:** 2026-10-19  
**Plan:** re-score thin shell (Relevance + Follow + RSS)

## Re-score

| | Phase 1–2 | Post Phase 7 + thin shell |
|--|----------:|--------------------------:|
| Overall | 6.5 | **7.5** |

Audit: `ai_docs/develop/audits/2026-10-19-architecture-and-layout.md`

## Thin shell

| Module | Extracted from bot |
|--------|-------------------|
| `app/relevance_scoring.py` | `calculate_relevance` |
| `app/follow_strategy.py` | `should_follow_user`, follow suggestions/timeline orchestration |
| `app/rss_content.py` | `fetch_external_content` + image/priority/dedupe helpers |

Bot LOC: **~3648 → ~3151** (~497 lines moved).

## Verify

```text
python verify_bot.py --smoke → 2/2 PASS
python -m unittest discover -s tests -v → 306 OK, 3 skipped
```
