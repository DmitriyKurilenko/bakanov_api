# Changelog

All notable changes to this project will be documented in this file.

## [0.3.1-dev] — 2026-05-15

### Fixed
- Bitrix24 spam → Метрика: устранена корневая причина полной остановки флоу — `ModuleNotFoundError: django_redis` (KI-002). Дедупликация переведена на штатный пакет `redis` через `apps/integrations/services/redis_client.py`
- Транзиентные ошибки Bitrix/Metrica (`requests.RequestException`) теперь пробрасываются и ретраятся Celery вместо тихой потери конверсии
- Эндпоинт `/webhooks/bitrix24/spam-lead` приведён к реальному формату outgoing webhook Bitrix24: убрана излишняя проверка токена, добавлена поддержка явного `entity_id` + стандартного `data[FIELDS][ID]`

### Added
- Надёжность флоу: декуплинг спам-загрузки от generic webhook, дедуп-замок с корректным снятием при сбоях, алерты в Telegram при окончательных ошибках
- Env-переменная `BITRIX24_SPAM_DEDUP_TTL` (по умолчанию 3600 с) для настройки окна дедупликации
- 8 тестов `test_bitrix24_spam_auto_dispatch.py` для покрытия диспатча, ретрая, дедупа и громких сбоев

### Changed
- `process_bitrix24_webhook` теперь диспатчит `process_bitrix24_spam_lead_webhook` как отдельную Celery-задачу вместо синхронного вызова
- `config/settings.py`: `REDIS_URL` вынесен в отдельную переменную для переиспользования

## [0.3.0-dev] — 2026-05-14

### Added
- Bitrix24 contract generation: iframe form in deal detail tab (`CRM_DEAL_DETAIL_TAB` placement)
- `Bitrix24ContractService` — maps Bitrix24 `UF_CRM_*` fields to contract context, renders PDF, uploads to deal
- `ContractRenderer.build_context_from_data()` — source-agnostic method for building template context from any data source
- Views `bitrix24_contract_form` and `bitrix24_contract_generate` with CSRF exempt + X-Frame-Options exempt
- Template `bitrix24/contract_form.html` — DaisyUI + Alpine.js + BX24 JS SDK (auto-fill from deal/contact)
- 16 env variables `BITRIX24_CONTRACT_FIELD_*` for configurable UF_CRM_* field mapping
- Routes `/bitrix24/contract/` and `/bitrix24/contract/generate/`
- Tests for Bitrix24 contract views, service, and field helpers

### Changed
- `ContractRenderer._build_context()` refactored to delegate to `build_context_from_data()`

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
