# Тестовый деплой: чек-лист

## 1. Подготовка `.env`

Минимум для приложения:

- `SECRET_KEY`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DEBUG=false`
- `SECURE_SSL_REDIRECT=true`
- `SESSION_COOKIE_SECURE=true`
- `CSRF_COOKIE_SECURE=true`
- `SECURE_HSTS_SECONDS=31536000`

Для связки amoCRM -> Метрика (спам-лиды):

- `AMOCRM_BASE_URL`
- `AMOCRM_ACCESS_TOKEN`
- `AMOCRM_REDIRECT_URI=https://<your-domain>/api/integrations/amocrm/oauth/callback`
- `YANDEX_METRIKA_TOKEN`
- `YANDEX_METRIKA_COUNTER_ID`
- `YANDEX_METRIKA_OFFLINE_GOAL_ID=spam_lead`
- `AMOCRM_SPAM_CLIENT_ID_FIELD_IDS=952089`

## 2. Preflight перед деплоем

По умолчанию `deploy.sh` работает в строгом preflight-режиме (`PREFLIGHT_STRICT=1`).

```bash
bash ./deploy.sh --preflight-only
```

Если нужно временно ослабить проверки (не рекомендуется):

```bash
PREFLIGHT_STRICT=0 bash ./deploy.sh --preflight-only
```

То же для полного деплоя:

```bash
PREFLIGHT_STRICT=0 bash ./deploy.sh
```

## 3. Деплой

```bash
bash ./deploy.sh
```

Скрипт:

- делает preflight автоматически;
- поднимает контейнеры;
- выполняет `migrate`, `collectstatic`, `check --deploy`;
- проверяет, что сервисы `web/db/redis/celery_worker/celery_beat` запущены;
- проверяет health endpoint `GET /api/healthz`.

## 4. Smoke-тест webhook

URL:

- `POST /api/integrations/webhooks/amocrm/spam-lead`

Минимальный payload от amoCRM webhook:

```bash
curl -X POST "https://<your-domain>/api/integrations/webhooks/amocrm/spam-lead" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "leads[add][0][id]=21688211"
```

Ожидаемый ответ: `status=ok`, `queued=1`, `task_ids` не пустой.

## 5. Проверка обработки в Celery

```bash
docker compose -f docker-compose.prod.yml logs celery_worker --tail=200
```

Ищем выполнение задачи `process_amocrm_spam_lead_webhook`.

## 6. Что делать при проблемах

- Проверить вывод `bash ./deploy.sh --preflight-only`.
- Проверить доступ токена к amoCRM и Метрике.
- Проверить, что поле `952089` реально содержит `client_id` в сделке/контакте/компании.
- Проверить логи:
  - `docker compose -f docker-compose.prod.yml logs web --tail=200`
  - `docker compose -f docker-compose.prod.yml logs celery_worker --tail=200`

## 7. Обновление TLS-сертификата

`init.sh` настраивает `certbot-renew.timer` (2 раза в сутки).  
Обновление выполняется без `stop/start nginx`: используется `certbot renew --deploy-hook "systemctl reload nginx || true"`.
