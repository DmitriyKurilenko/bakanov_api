# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0-dev] — 2026-04-09

### Added
- Интеграция с Битрикс24: outgoing webhooks (`Bitrix24Client`) и incoming webhook endpoint (`POST /api/integrations/webhooks/bitrix24`)
- CRUD операции для лидов, сделок, контактов и компаний Bitrix24 с пагинацией
- Celery task `process_bitrix24_webhook` с auto-retry и exponential backoff
- Валидация входящих webhook по `BITRIX24_INBOUND_TOKEN`
- Env-переменные: `BITRIX24_WEBHOOK_URL`, `BITRIX24_INBOUND_TOKEN`, `BITRIX24_TIMEOUT`
- 34 теста для Bitrix24 интеграции (клиент, API, обработчик)
- Структура документации проекта: `docs/` (TASK_STATE, DECISIONS, KNOWN_ISSUES, DEV_LOG, RELEASE_NOTES, VERSIONING)
- Протокол для AI-агентов: `AGENTS.MD`
