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

### 2026-05-15 — Bitrix24 spam → Метрика: восстановление и закалка флоу

- **Файлы:**
  - `apps/integrations/tasks.py` — `process_bitrix24_webhook` декуплирован (диспатч отдельной задачи); `process_bitrix24_spam_lead_webhook` переписан: штатный redis-клиент, корректный dedup/retry, громкие сбои + Telegram
  - `apps/integrations/services/redis_client.py` — новый: `get_redis_client()` на пакете `redis` (без `django-redis`)
  - `apps/integrations/services/bitrix24_webhook_handler.py` — `_fetch_entity` пробрасывает `requests.RequestException` (ретрай вместо тихой потери)
  - `apps/integrations/services/bitrix24_spam_lead_service.py` — `_fetch_entity/_fetch_contact/_fetch_company` пробрасывают транзиентные ошибки
  - `apps/integrations/api.py` — `bitrix24_spam_lead_webhook` принимает явный `entity_id` и стандартный outgoing payload
  - `config/settings.py` — `REDIS_URL` вынесен, добавлен `BITRIX24_SPAM_DEDUP_TTL`
  - `apps/integrations/tests/test_bitrix24_spam_auto_dispatch.py` — новый: 8 тестов (диспатч, ретрай, dedup, громкие сбои)
  - `apps/integrations/tests/test_bitrix24_spam_webhook_api.py` — тест токена приведён к DEC-009
  - docs: DECISIONS (DEC-009), KNOWN_ISSUES (KI-002 closed, KI-003 open), TASK_STATE, RELEASE_NOTES
- **Что сделано:** Найдена и устранена корневая причина «сработал 1-2 раза и перестал» — `ModuleNotFoundError: django_redis` (коммит `0ceba61`). Дедуп переведён на штатный `redis`. Флоу закалён: декуплинг от generic-вебхука, ретраи на транзиентных ошибках, громкие алерты вместо тихих сбоев, корректное взаимодействие dedup+retry.
- **Валидация:** `manage.py check` — OK. Целевые тесты изменённых модулей — 59/59 OK. Полный прогон — 141/146 (5 падений — незавершённая фича договоров, KI-003, не регрессия: затронутые модули не менялись). Сборка образа OK, импорт `redis_client` OK.
- **Риски:** На проде нужны заполненные `YANDEX_METRIKA_TOKEN`/`YANDEX_METRIKA_COUNTER_ID` (подтверждено пользователем — заполнены). KI-003 (тесты договоров) вне scope.

### 2026-05-14 — Bitrix24: генерация договоров (iframe placement)

- **Файлы:**
  - `apps/crm/services/contract_renderer.py` — рефакторинг: выделен `build_context_from_data()` (source-agnostic)
  - `apps/integrations/services/bitrix24_contract_service.py` — новый: маппинг полей Bitrix24 → контекст договора, рендеринг PDF
  - `apps/integrations/views.py` — добавлены `bitrix24_contract_form`, `bitrix24_contract_generate`
  - `templates/bitrix24/contract_form.html` — новый: DaisyUI + Alpine.js + BX24 JS SDK форма договора
  - `config/urls.py` — маршруты `/bitrix24/contract/`, `/bitrix24/contract/generate/`
  - `config/settings.py` — 16 новых env-переменных `BITRIX24_CONTRACT_FIELD_*`
  - `apps/integrations/tests/test_bitrix24_contract.py` — тесты (views, service, helpers)
- **Что сделано:** Полная реализация генерации договоров для Bitrix24: iframe-форма в карточке сделки, предзаполнение из CRM, редактирование, генерация PDF через WeasyPrint, загрузка в файловое поле сделки, отправка по email. ContractRenderer рефакторинг для работы с любым источником данных.
- **Валидация:** Синтаксис всех файлов OK. Тесты написаны (не запущены — Docker не доступен).
- **Риски:** Требуется настроить `BITRIX24_CONTRACT_FIELD_*` в `.env`. Регистрация placement в manifest приложения Bitrix24.

---

### 2026-05-13 — Упрощение деплоя: единый docker-compose.yml + traefik (v0.2.1-dev)

- **Файлы:**
  - Удалены: `docker-compose.prod.yml`, `.env.dev.example`, `.env.example`
  - `docker-compose.yml` — единственный compose, traefik labels, external network `traefik-public`
  - `.env.example` — переименован из `.env.prod.example`, `DOMAIN=kapitan.prvms.ru`
  - `deploy.sh` — `PRIMARY_COMPOSE_FILE=docker-compose.yml`, убрана проверка на dev compose
- **Что сделано:** Один compose-файл для production с traefik, один `.env.example`. Убраны дублирующие dev-файлы.
- **Валидация:** `manage.py check` — OK.
- **Риски:** Требуется ручная миграция на сервере (убрать старые volume `./:/app`).

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
