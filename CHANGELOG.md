# Changelog

All notable changes to this project will be documented in this file.

## [0.2.1-dev] — 2026-05-13

### Added
- Bitrix24 spam lead: automatic upload to Yandex.Metrica when lead status changes to "СПАМ" (`STATUS_ID=UC_Q4I0BY`)
- Env variable `BITRIX24_SPAM_STATUS_ID` for configurable spam stage detection
- `process_bitrix24_webhook` now triggers `Bitrix24SpamLeadSyncService` on `ONCRMLEADUPDATE` with matching spam status
- Traefik labels in `docker-compose.yml` for reverse proxy integration

### Changed
- **Deployment simplified**: single `docker-compose.yml` (removed `docker-compose.prod.yml`)
- Single `.env.example` with `DOMAIN=kapitan.prvms.ru` (removed `.env.dev.example`)
- `deploy.sh` updated to use `docker-compose.yml` directly

## [0.2.0-dev] — 2026-05-13

### Added
- Bitrix24 — фильтр спам-заявок: endpoint `POST /api/integrations/webhooks/bitrix24/spam-lead`
- Сервис `Bitrix24SpamLeadSyncService` для извлечения `client_id` из UF_CRM_ полей лида/контакта/компании Bitrix24
- Celery task `process_bitrix24_spam_lead_webhook` с auto-retry и exponential backoff
- Env-переменные: `BITRIX24_SPAM_CLIENT_ID_FIELD_CODES`, `BITRIX24_SPAM_CLIENT_ID_FIELD_NAMES`
- 22 теста для Bitrix24 spam lead (сервис + API)
- Подробное логирование входящих webhook payload и UF_CRM_ полей для диагностики

### Fixed
- Исправлен `NameError: name 'logger' is not defined` в `bitrix24_spam_lead_service.py`

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
