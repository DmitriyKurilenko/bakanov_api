# Production Deploy Checklist

## Что изменено

- `docker-compose.yml` — единственный production compose, **нет volume `./:/app`** (код берётся из образа)
- `.env.example` — единственный шаблон env с `DOMAIN=kapitan.prvms.ru`
- `deploy.sh` — использует `docker-compose.yml` напрямую
- Traefik labels добавлены для reverse proxy

## Пошаговая инструкция для сервера

### 1. Остановить старые контейнеры

```bash
cd /opt/kapitan_api
sudo docker compose down
```

### 2. Удалить старые образы (важно!)

```bash
sudo docker rmi $(sudo docker images -q kapitan_api-*) 2>/dev/null || true
```

### 3. Проверить .env

```bash
cat .env | grep -E "^(DOMAIN|ALLOWED_HOSTS|BITRIX24)"
```

Должно быть:
```
DOMAIN=kapitan.prvms.ru
ALLOWED_HOSTS=kapitan.prvms.ru,localhost,127.0.0.1
BITRIX24_WEBHOOK_URL=https://kapitan-trips.bitrix24.ru/rest/17/sodw15cgvf0zp1sw/
BITRIX24_INBOUND_TOKEN=t636m6d0gkp4v3sntcfbys1tekwskx1d
BITRIX24_SPAM_CLIENT_ID_FIELD_CODES=UF_CRM_NF_YM_CLIENT_ID
BITRIX24_SPAM_STATUS_ID=UC_Q4I0BY
```

### 4. Создать traefik сеть (если нет)

```bash
sudo docker network create traefik-public 2>/dev/null || true
```

### 5. Запустить деплой

```bash
cd /opt/kapitan_api
sudo ./deploy.sh
```

### 6. Проверить, что контейнеры запущены

```bash
sudo docker compose ps
```

### 7. Проверить healthcheck

```bash
curl -s https://kapitan.prvms.ru/api/healthz
```

Должно вернуть: `{"status": "ok"}`

### 8. Проверить Bitrix24 webhook

```bash
curl -s -X POST https://kapitan.prvms.ru/api/integrations/webhooks/bitrix24/spam-lead \
  -d "entity_type=lead" \
  -d "entity_id=245" \
  -d "auth[application_token]=t636m6d0gkp4v3sntcfbys1tekwskx1d"
```

Должно вернуть: `{"status": "ok", ...}`

## Если что-то пошло не так

### Проверить логи

```bash
sudo docker compose logs -f web
sudo docker compose logs -f celery_worker
```

### Проверить, что код в образе обновлён

```bash
sudo docker compose exec web cat /app/apps/integrations/tasks.py | grep -n "auto-upload"
```

Должно найти строку с `Bitrix24 spam auto-upload`.

### Полная пересборка (если контейнеры кэшируют старый код)

```bash
cd /opt/kapitan_api
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

## Важно

- **НЕ используйте** `docker-compose.yml` с volume `./:/app` — это dev-режим
- **ВСЕГДА** запускайте `./deploy.sh` или `docker compose -f docker-compose.yml up -d --build`
- После `git pull` обязательно `docker compose build` чтобы пересобрать образ с новым кодом
