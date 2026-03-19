# Bakanov API / Личный кабинет

MVP-каркас приложения под Django 5 + Ninja API для интеграции с AmoCRM.

## Версия Python

- Обязательная версия: `Python 3.11`
- В Docker используется образ `python:3.11-slim`

## Что уже есть

- Django 5 + `django-ninja`
- Роли пользователей: `manager`, `head` (РОП), `admin`
- API-заготовки под ключевые бизнес-процессы
- Генерация договора по HTML-шаблону через WeasyPrint (логика на базе `prepare_contract_v4`)
- Интеграции: AmoCRM, Telegram, Zadarma webhook, Google Form webhook
- Фоновая обработка: Celery worker + Beat + Flower
- Инфраструктура: Postgres, Redis, Docker, docker-compose
- Базовый дашборд (шаблоны + role-based отображение)

## Быстрый старт

1. Скопировать окружение:
   ```bash
   cp .env.dev.example .env
   ```
   Для сервера используйте:
   ```bash
   cp .env.prod.example .env
   ```
2. (Локально) создать venv на Python 3.11:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Заполнить `.env` (минимум: AmoCRM/Telegram/SMTP при использовании интеграций).
   - Для договора можно переопределить `CONTRACT_HTML_TEMPLATE`, `CONTRACT_HTML_TEMPLATE_U` и `CONTRACT_EUR_RATE`.
4. Запустить проект:
   ```bash
   docker compose up --build
   ```
5. Создать суперпользователя:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

Для production-режима используйте отдельный compose-файл:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Шаблоны окружения:

- `.env.dev.example` — локальная разработка
- `.env.prod.example` — сервер/production
- `.env.example` — совместимый alias локального шаблона

## Основные endpoints (черновые)

- `POST /api/crm/contract/generate`
- `POST /api/crm/lead/assign-min-load`
- `POST /api/crm/lead/new/telegram-notify`
- `POST /api/integrations/webhooks/zadarma`
- `POST /api/integrations/webhooks/google-form`
- `POST /api/integrations/webhooks/amocrm/spam-lead`
- `GET /api/healthz`

## Важно

Текущая версия — архитектурный MVP: часть логики реализована как заглушки (placeholder), чтобы быстро наращивать функционал без переделки структуры.

Для `POST /api/crm/contract/generate`:

Разовая проверка генерации/загрузки договора для одного lead (без management-команд):
```bash
python scripts/test_contract_upload.py --lead-id 21688211 --expect-pdf
```

В Docker:
```bash
docker compose run --rm --no-deps web python scripts/test_contract_upload.py --lead-id 21688211 --expect-pdf
```

Проверка работоспособности договора для одного lead (как в webhook):

```bash
docker compose run --rm --no-deps web python scripts/check_contracts_health.py --lead-id 21688211 --expect-pdf
```

## Поток spam-lead (amoCRM -> Metrica)

1. amoCRM webhook присылает `lead_id` в `POST /api/integrations/webhooks/amocrm/spam-lead`.
2. API ставит асинхронную задачу Celery `process_amocrm_spam_lead_webhook`.
3. Задача получает сделку из amoCRM, извлекает `client_id` из custom fields:
   - сначала из сделки;
   - затем из связанных контактов;
   - затем из связанных компаний.
4. Найденные `client_id` загружаются в Метрику через `offline_conversions/upload` в существующую цель `YANDEX_METRIKA_OFFLINE_GOAL_ID` (например, `spam_lead`).

Ключевые env-переменные:

- `AMOCRM_BASE_URL`
- `AMOCRM_ACCESS_TOKEN`
- `AMOCRM_REDIRECT_URI` (например, `https://<domain>/api/integrations/amocrm/oauth/callback`)
- `YANDEX_METRIKA_TOKEN`
- `YANDEX_METRIKA_COUNTER_ID`
- `YANDEX_METRIKA_OFFLINE_GOAL_ID`
- `AMOCRM_SPAM_CLIENT_ID_FIELD_IDS` / `AMOCRM_SPAM_CLIENT_ID_FIELD_CODES` / `AMOCRM_SPAM_CLIENT_ID_FIELD_NAMES`

## Деплой на тестовый сервер

Скрипты деплоя находятся в корне проекта:

- `./init.sh` — первичная настройка сервера (nginx/certbot/docker + первый деплой)
- `./deploy.sh` — регулярный деплой

См. подробный чек-лист: `TEST_SERVER_DEPLOY.md`.
