# Plan: Health / Media / Auth thin-shell extract

**Created:** 2026-10-19  
**Status:** Done  
**Parent:** God Object shell — after ScheduledPostPublisher  
**Goal:** Move auth, media upload/embed, and health/recovery bodies behind injected ports without changing runtime behavior.

## Scope

1. `app/auth_service.py` — `AuthPorts` + `AuthService.authenticate` / `persist_session`; **no** import of `bluesky_bot_v2`
2. `app/media_service.py` — `MediaPorts` + upload + `create_post_with_image` / `create_post_with_link_preview`
3. `app/health_service.py` — `HealthPorts` + `health_monitor` / helpers / `emergency_recovery`
4. Bot composition root: `_build_*_ports()` + thin wrappers; heartbeat stays on bot
5. Hermetic tests (gate + happy path) + packaging PYFILES + opt sync

## Out of scope

- HeartbeatMonitor extract (already HB-001)
- Moving `create_image_prompt_from_text` / Pollinations glue
- Changing retry / circuit-breaker policy wiring

## Acceptance

- [x] New modules must not import `bluesky_bot_v2`
- [x] Bot delegates `authenticate`, media uploads/embeds, `health_monitor`, `emergency_recovery`
- [x] Tests: gate + happy path per service (no network)
- [x] Packaging lists `auth_service.py` / `media_service.py` / `health_service.py`
