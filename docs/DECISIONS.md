# Architecture Decisions

Решения по архитектуре и поведению системы. Каждая запись — факт, а не предложение.
Если решение отменено — пометить `[ОТМЕНЕНО]` и указать причину.

---

## DEC-001: Стек технологий (2026-04-09)

**Контекст:** Зафиксировать стек, чтобы агенты и разработчики не добавляли зависимости без согласования.

**Решение:**
- Django 5.2 LTS, Python 3.13
- PostgreSQL (через psycopg 3)
- Redis (брокер Celery + кэш)
- Celery 5 + Beat + Flower
- django-ninja (API)
- WeasyPrint + ReportLab (генерация документов)
- DaisyUI + Tailwind CSS (фронт, подключены через CDN)
- Alpine.js (интерактивность фронта)
- Font Awesome (иконки)
- Docker / docker-compose (единственная среда разработки и деплоя)

**Последствия:** Любое расширение стека требует явного одобрения владельца проекта.

---

## DEC-002: Docker-only разработка (2026-04-09)

**Контекст:** Исключить расхождение окружений host ↔ контейнер.

**Решение:** Все команды выполняются через `docker compose exec` / `docker compose run --rm`. Никаких `pip install`, `brew install`, `npm install -g` на хосте.

**Последствия:** CSS-билды через `docker run --rm -v "$(pwd)":/app -w /app node:18-alpine sh -c "npm install && npx tailwindcss ..."`.

---

## DEC-003: Роли пользователей (2026-04-09)

**Контекст:** Система разграничения доступа.

**Решение:** Три роли: `manager`, `head` (РОП), `admin`. Доступ контролируется на уровне view/API.

**Последствия:** Расширение ролей возможно, но требует обновления всех проверок доступа.

---

## DEC-004: Интеграция с Битрикс24 (2026-04-09)

**Контекст:** Добавить поддержку Bitrix24 CRM наравне с AmoCRM.

**Решение:**
- Outgoing webhooks: `Bitrix24Client` (dataclass + factory `from_settings()`) вызывает REST API Bitrix24 через webhook URL с токеном.
- Incoming webhooks: POST `/api/integrations/webhooks/bitrix24` принимает события CRM (lead/deal/contact add/update/delete), проверяет `BITRIX24_INBOUND_TOKEN`, диспатчит в Celery task.
- Конфигурация через env: `BITRIX24_WEBHOOK_URL`, `BITRIX24_INBOUND_TOKEN`, `BITRIX24_TIMEOUT`.
- Паттерн идентичен AmoCRM: service → task → API endpoint.

**Последствия:** Новые зависимости не добавлены. Используется только `requests` (уже в стеке).

---

## DEC-005: Битрикс24 — встроенное приложение (local app) (2026-04-10)

**Контекст:** Интеграция должна иметь интерфейс внутри Битрикс24 (iframe).

**Решение:**
- Тип: локальное приложение (server iframe), регистрируется в Bitrix24 Marketplace → Разработчикам → Локальные приложения.
- Модель `Bitrix24Portal` хранит credentials портала (member_id, domain, access/refresh tokens, expires_at, app_status).
- OAuth-сервис отвечает за сохранение и обновление токенов через `https://oauth.bitrix.info/oauth/token/`.
- `Bitrix24Client` расширен методом `from_portal()` и автоматической инъекцией `auth` параметра в OAuth-режиме.
- Views: `bitrix24_install` (POST, BX24.installFinish()), `bitrix24_app` (POST, основной UI).
- Оба endpoint: `@csrf_exempt` + `@xframe_options_exempt` (Bitrix24 iframe требует отсутствия X-Frame-Options и не шлёт CSRF).
- UI: DaisyUI + Alpine.js для визуала, BX24 JS SDK для получения текущего пользователя и быстрых CRM-запросов (callBatch).
- Конфигурация: `BITRIX24_APP_ID`, `BITRIX24_APP_SECRET` (env).

**Последствия:** Требуется HTTPS для production. Новые зависимости не добавлены.

---

## DEC-006: Bitrix24 — фильтр спам-заявок (offline conversions) (2026-05-13)

**Контекст:** Нужно загружать `client_id` спам-лидов/сделок из Bitrix24 в Яндекс.Метрику, аналогично amoCRM.

**Решение:**
- Сервис `Bitrix24SpamLeadSyncService` (паттерн идентичен `AmoCrmSpamLeadSyncService`):
  - Получает сущность (lead/deal) из Bitrix24 REST API.
  - Извлекает `client_id` из кастомных полей (`UF_CRM_*`) самой сущности, затем связанного контакта (`CONTACT_ID`), затем связанной компании (`COMPANY_ID`).
  - Поиск по кодам полей (`BITRIX24_SPAM_CLIENT_ID_FIELD_CODES`) или по названиям (`BITRIX24_SPAM_CLIENT_ID_FIELD_NAMES`), либо эвристически.
  - Загружает найденные `client_id` в Метрику через `YandexMetricaService.upload_spam_client_ids()`.
- Endpoint: `POST /api/integrations/webhooks/bitrix24/spam-lead` — принимает `entity_type`, `entity_id`, `auth[application_token]`, валидирует токен, ставит задачу Celery.
- Celery task: `process_bitrix24_spam_lead_webhook` с автоповторами при сетевых ошибках.
- env: `BITRIX24_SPAM_CLIENT_ID_FIELD_CODES`, `BITRIX24_SPAM_CLIENT_ID_FIELD_NAMES`.

**Последствия:** Новые зависимости не добавлены. Требуется настроить `BITRIX24_WEBHOOK_URL` для outgoing запросов к Bitrix24.

---

## DEC-007: Bitrix24 spam lead — автозагрузка при статусе СПАМ (2026-05-13)

**Контекст:** Необходимо автоматически загружать `client_id` в Метрику только при переносе лида в специальный этап "СПАМ" в Bitrix24.

**Решение:**
- `process_bitrix24_webhook` (Celery task) при событии `ONCRMLEADUPDATE` проверяет `STATUS_ID` полученного лида.
- Если `STATUS_ID` совпадает с `BITRIX24_SPAM_STATUS_ID` (по умолчанию `IN_PROCESS`, переопределяется через env), автоматически вызывается `Bitrix24SpamLeadSyncService.sync_entity()` для загрузки в Метрику.
- Статус "СПАМ" создан как отдельный этап в воронке (`STATUS_ID=UC_Q4I0BY`).
- Отдельный endpoint `/webhooks/bitrix24/spam-lead` сохранён для ручной/тестовой загрузки.

**Последствия:** Требуется настроить `BITRIX24_SPAM_STATUS_ID` в `.env` под реальный этап в Bitrix24.

---

## DEC-008: Генерация договоров в Bitrix24 (2026-05-14)

**Контекст:** В amoCRM уже работает генерация PDF-договоров. Нужно перенести функционал в Bitrix24 с улучшенным UX — через iframe-приложение с формой редактирования.

**Решение:**
- Рефакторинг `ContractRenderer`: выделен `build_context_from_data(data: dict)` — source-agnostic метод, принимающий нормализованный словарь.
- `Bitrix24ContractService` — маппит поля Bitrix24 (`UF_CRM_*`) в формат контекста договора.
- View `bitrix24_contract_form` — рендерит iframe-форму (placement `CRM_DEAL_DETAIL_TAB`).
- View `bitrix24_contract_generate` — API endpoint для генерации PDF + загрузка в сделку + email.
- Шаблон `bitrix24/contract_form.html` — DaisyUI + Alpine.js + BX24 JS SDK.
- Маппинг полей через env-переменные (`BITRIX24_CONTRACT_FIELD_*`).

**Последствия:** Требуется настроить `BITRIX24_CONTRACT_FIELD_*` в `.env` под реальные UF_CRM_* коды портала. Регистрация placement в manifest приложения.

---

## DEC-009: Bitrix24 spam → Метрика — устойчивость флоу (2026-05-15)

**Контекст:** Флоу передачи спам-лидов из Bitrix24 в Яндекс.Метрику «сработал один-два раза и перестал». Корневая причина: коммит `0ceba61` добавил `from django_redis import get_redis_connection` в задачу дедупликации, но пакет `django-redis` не входит в стек (нет в `requirements.txt`, `CACHES` не настроен). Каждый вызов `process_bitrix24_spam_lead_webhook` падал с `ModuleNotFoundError`. Сопутствующие дефекты: тихое проглатывание транзиентных ошибок Bitrix (конверсия терялась без ретрая и следа), связанность спам-загрузки с обработкой generic-вебхука, отсутствие алертов.

**Решение:**
- Дедуп переведён на штатный клиент `redis` (уже зависимость брокера Celery) через новый хелпер `apps/integrations/services/redis_client.py` и `settings.REDIS_URL`. **`django-redis` не вводится** — стек не расширяется (DEC-001).
- Спам-загрузка декуплирована: `process_bitrix24_webhook` при `ONCRMLEADUPDATE` + `STATUS_ID == BITRIX24_SPAM_STATUS_ID` **диспатчит** отдельную задачу `process_bitrix24_spam_lead_webhook` (свой ретрай и дедуп), а не вызывает sync инлайн. Сбой Метрики больше не роняет обработку обычных вебхуков.
- Транзиентные ошибки Bitrix (`requests.RequestException`) в `_fetch_entity`/`_fetch_contact`/`_fetch_company` пробрасываются → Celery autoretry, вместо «entity not found» и тихой потери.
- Любой окончательный сбой (нет client_id, не настроен токен Метрики, неожиданная ошибка) логируется на ERROR и шлёт алерт в Telegram. Никаких тихих сбоев.
- Дедуп-замок снимается при любом сбое (ретрай/передоставка может отработать) и сохраняется/продлевается только при успехе. TTL вынесен в `BITRIX24_SPAM_DEDUP_TTL` (по умолчанию 3600 с) — гасит всплески `ONCRMLEADUPDATE`, пока лид в этапе СПАМ, но допускает повторную загрузку при возврате позже.
- Эндпоинт `/webhooks/bitrix24/spam-lead` принимает оба формата: явный `entity_id`/`entity_type` (ручной/тестовый триггер) и стандартный outgoing-webhook (`event` + `data[FIELDS][ID]`). Эндпоинт намеренно без проверки токена: штатный outgoing-вебхук Bitrix24 не несёт `application_token`, совпадающий с `BITRIX24_INBOUND_TOKEN` (продолжение решения коммита `e042ece`). Статус-aware путь `/webhooks/bitrix24` остаётся под токеном.

**Последствия:** Дедуп-загрузка спам-лидов работает на штатном Redis. Требуется `REDIS_URL` (уже есть) и заполненные `YANDEX_METRIKA_TOKEN`/`YANDEX_METRIKA_COUNTER_ID` на проде. При пустых креденшелах флоу не работает, но теперь это **громко** видно (ERROR + Telegram), а не тихо.
