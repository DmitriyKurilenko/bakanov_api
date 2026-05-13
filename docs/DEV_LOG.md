# Development Log

Хронологический журнал изменений. Новые записи — сверху.

## Формат записи

```
### YYYY-MM-DD — Краткое описание
- **Файлы:** список изменённых файлов
- **Что сделано:** описание
- **Валидация:** manage.py check, тесты, HTTP-проверка
- **Риски:** что может сломаться
```

---

### 2026-05-13 — Bitrix24 spam lead: автозагрузка при статусе СПАМ (v0.2.1-dev)

- **Файлы:**
  - `apps/integrations/tasks.py` — автотриггер `Bitrix24SpamLeadSyncService` при `ONCRMLEADUPDATE` со статусом СПАМ
  - `config/settings.py` — `BITRIX24_SPAM_STATUS_ID`
  - `VERSION` → `0.2.1-dev`
  - `CHANGELOG.md` — секция [0.2.1-dev]
  - `docs/TASK_STATE.md`, `docs/DEV_LOG.md`, `docs/DECISIONS.md`
- **Что сделано:** При переносе лида в этап "СПАМ" (`STATUS_ID=UC_Q4I0BY`) в Bitrix24, webhook `ONCRMLEADUPDATE` автоматически запускает загрузку `client_id` в Яндекс.Метрику.
- **Валидация:** `manage.py check` — OK. Все тесты проходят.
- **Риски:** Статус СПАМ должен быть настроен в Bitrix24 и в `.env` (`BITRIX24_SPAM_STATUS_ID`).

### 2026-05-13 — Подготовка коммита (v0.2.0-dev)

- **Файлы:**
  - `VERSION` → `0.2.0-dev`
  - `CHANGELOG.md` — секция [0.2.0-dev]
  - `docs/TASK_STATE.md` — задача #6 перенесена в завершённые
  - `docs/KNOWN_ISSUES.md` — KI-001 (NameError logger) закрыт
  - `docs/RELEASE_NOTES.md` — запись о фильтре спам-заявок Bitrix24
- **Что сделано:** Подготовка релиза: обновлена версия, changelog, release notes, task state, known issues.
- **Валидация:** `manage.py check` — OK. 110/110 тестов проходят.
- **Риски:** Нет.

### 2026-05-13 — Bitrix24: фильтр спам-заявок (offline conversions)

- **Файлы:**
  - `apps/integrations/services/bitrix24_spam_lead_service.py` — сервис извлечения client_id из Bitrix24 и загрузки в Метрику
  - `apps/integrations/tasks.py` — Celery task `process_bitrix24_spam_lead_webhook`
  - `apps/integrations/api.py` — endpoint `POST /api/integrations/webhooks/bitrix24/spam-lead`
  - `config/settings.py` — env `BITRIX24_SPAM_CLIENT_ID_FIELD_CODES`, `BITRIX24_SPAM_CLIENT_ID_FIELD_NAMES`
  - `.env.dev.example`, `.env.example`, `.env.prod.example` — новые переменные
  - `apps/integrations/tests/test_bitrix24_spam_lead_service.py` — 14 тестов сервиса
  - `apps/integrations/tests/test_bitrix24_spam_webhook_api.py` — 8 тестов API
  - `docs/DECISIONS.md`, `docs/DEV_LOG.md`, `docs/TASK_STATE.md`, `docs/PROJECT_OVERVIEW.md` — обновлены
- **Что сделано:** Полная интеграция спам-фильтра для Bitrix24: извлечение client_id из UF_CRM_ полей лида/контакта/компании, загрузка в Яндекс.Метрику. Паттерн идентичен amoCRM.
- **Валидация:** `manage.py check` — OK. Все тесты проходят. Нет регрессий.
- **Риски:** Требуется настроить `BITRIX24_WEBHOOK_URL` для outgoing запросов к Bitrix24.

### 2026-04-13 — Создание полной документации проекта

- **Файлы:**
  - `docs/PROJECT_OVERVIEW.md` — подробная документация по всему проекту
  - `AGENTS.MD` — обновлен порядок чтения
  - `docs/TASK_STATE.md` — обновлен статус
- **Что сделано:** Создана исчерпывающая документация по архитектуре, моделям, API, сервисам, бизнес-процессам, переменным окружения и развёртыванию. Документ позволяет быстро вспомнить структуру проекта через месяц.
- **Валидация:** Нет изменений кода — валидация не требуется.
- **Риски:** Нет.

### 2026-04-10 — Битрикс24: встроенное приложение (local app + iframe)

- **Файлы:**
  - `apps/integrations/models.py` — модель `Bitrix24Portal` (member_id, domain, tokens, app_status)
  - `apps/integrations/migrations/0001_initial.py` — миграция
  - `apps/integrations/services/bitrix24_oauth.py` — OAuth: save_portal_from_request, refresh_tokens, ensure_valid_token
  - `apps/integrations/services/bitrix24_service.py` — расширен: from_portal(), OAuth-режим в _call()
  - `apps/integrations/views.py` — bitrix24_install, bitrix24_app (csrf_exempt + xframe_options_exempt)
  - `apps/integrations/admin.py` — Bitrix24PortalAdmin
  - `templates/bitrix24/app.html` — DaisyUI + Alpine.js + BX24 JS SDK (user info, CRM stats, leads table)
  - `templates/bitrix24/install_success.html` — BX24.installFinish()
  - `templates/bitrix24/error.html` — страница ошибки
  - `config/urls.py` — маршруты bitrix24/install/, bitrix24/app/
  - `config/settings.py` — BITRIX24_APP_ID, BITRIX24_APP_SECRET
  - `.env.dev.example`, `.env.example`, `.env.prod.example` — новые переменные
  - `apps/integrations/tests/test_bitrix24_oauth.py` — 9 тестов OAuth
  - `apps/integrations/tests/test_bitrix24_views.py` — 7 тестов views
- **Что сделано:** Полноценное встроенное приложение для Bitrix24: OAuth-авторизация, хранение токенов, iframe UI с DaisyUI, BX24 JS SDK для получения данных текущего пользователя и CRM-статистики. Bitrix24Client расширен методом from_portal() для работы в OAuth-режиме.
- **Валидация:** `manage.py check` — OK. 82/82 тестов проходят (16 новых). Миграция применена. Нет регрессий.
- **Риски:** Требуется HTTPS для production (Bitrix24 не загружает iframe по HTTP).

### 2026-04-09 — Интеграция с Битрикс24

- **Файлы:**
  - `apps/integrations/services/bitrix24_service.py` — клиент REST API (outgoing webhooks)
  - `apps/integrations/services/bitrix24_webhook_handler.py` — обработчик входящих событий
  - `apps/integrations/api.py` — endpoint `POST /api/integrations/webhooks/bitrix24`
  - `apps/integrations/schemas.py` — схемы ответов
  - `apps/integrations/tasks.py` — Celery task `process_bitrix24_webhook`
  - `config/settings.py` — env-переменные `BITRIX24_*`
  - `.env.dev.example`, `.env.example`, `.env.prod.example` — шаблоны
  - `apps/integrations/tests/test_bitrix24_service.py` — 13 тестов клиента
  - `apps/integrations/tests/test_bitrix24_webhook_api.py` — 6 тестов API
  - `apps/integrations/tests/test_bitrix24_webhook_handler.py` — 15 тестов обработчика
- **Что сделано:** Полная интеграция с Bitrix24: outgoing (CRUD leads/deals/contacts/companies с пагинацией) + incoming (webhook с валидацией токена, диспатч в Celery).
- **Валидация:** `manage.py check` — OK. 66/66 тестов проходят. Нет регрессий.
- **Риски:** Нет. Новые зависимости не добавлены.

### 2026-04-09 — Создание структуры документации

- **Файлы:** docs/TASK_STATE.md, docs/DECISIONS.md, docs/KNOWN_ISSUES.md, docs/DEV_LOG.md, docs/RELEASE_NOTES.md, docs/VERSIONING.md, AGENTS.MD
- **Что сделано:** Создана директория `docs/` со всеми файлами, на которые ссылается AGENTS.MD. Зафиксированы начальные решения по стеку и процессам.
- **Валидация:** Нет изменений кода — валидация не требуется.
- **Риски:** Нет.
