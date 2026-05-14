#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"

log()  { echo "==> $*"; }
die()  { echo "[FAIL] $*" >&2; exit 1; }

log "Деплой $(date '+%Y-%m-%d %H:%M:%S') — $ROOT_DIR"

# 1. Обновить код
if [[ -d .git ]]; then
  git fetch --all --prune -q
  git pull --ff-only -q || die "git pull завершился с ошибкой"
  log "Коммит: $(git log -1 --oneline)"
fi

# 2. Собрать и запустить
log "Docker compose up --build..."
docker compose down
docker compose build --no-cache
docker compose up -d

# 3. Ждём БД
MAX_RETRIES=30
for i in $(seq 1 $MAX_RETRIES); do
  if docker compose exec -T db pg_isready -U "${POSTGRES_USER:-bakanov}" -q 2>/dev/null; then
    break
  fi
  if [[ $i -eq $MAX_RETRIES ]]; then
    die "База данных не стала доступна"
  fi
  sleep 2
done

# 4. Миграции и статика
log "Миграции..."
docker compose exec -T web python manage.py migrate --noinput

log "Collectstatic..."
docker compose exec -T web python manage.py collectstatic --noinput

# 5. Проверка сервисов
for svc in web db redis celery_worker celery_beat; do
  if ! docker compose ps --status running "$svc" 2>/dev/null | grep -q "$svc"; then
    die "Сервис не запущен: $svc"
  fi
  log "$svc OK"
done

# 6. Healthcheck
MAX_HEALTH_RETRIES=20
for i in $(seq 1 "$MAX_HEALTH_RETRIES"); do
  if docker compose exec -T web \
    python -c "import json,sys,urllib.request; req=urllib.request.Request('http://localhost:8000/api/healthz', headers={'X-Forwarded-Proto': 'https'}); body=urllib.request.urlopen(req,timeout=5).read().decode('utf-8'); data=json.loads(body); sys.exit(0 if data.get('status')=='ok' else 1)" >/dev/null 2>&1; then
    log "Healthcheck OK"
    break
  fi
  if [[ $i -eq $MAX_HEALTH_RETRIES ]]; then
    die "Healthcheck не прошёл"
  fi
  sleep 2
done

log "Деплой завершён — $(date '+%H:%M:%S')"
docker compose ps
