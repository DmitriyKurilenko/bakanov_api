#!/usr/bin/env bash
# deploy.sh — деплой проекта Bakanov API
#
# Использование:
#   ./deploy.sh [--skip-pull] [--skip-build] [--no-backup] [--preflight-only]
#
# Конфигурация читается из .env (корень проекта).
# Любую переменную можно переопределить через shell:
#   ENV_FILE=.env.staging ./deploy.sh
#
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

SCRIPTS_ENV="$ROOT_DIR/.env"
if [[ -f "$SCRIPTS_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SCRIPTS_ENV"
  set +a
fi

ENV_FILE="${ENV_FILE:-.env}"
PRIMARY_COMPOSE_FILE="${PRIMARY_COMPOSE_FILE:-docker-compose.prod.yml}"
SECONDARY_COMPOSE_FILE="${SECONDARY_COMPOSE_FILE:-}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-5}"
DB_SERVICE_NAME="${DB_SERVICE_NAME:-db}"
DB_CONTAINER_USER="${DB_CONTAINER_USER:-${POSTGRES_USER:-postgres}}"
DB_CONTAINER_NAME="${DB_CONTAINER_NAME:-${POSTGRES_DB:-postgres}}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:8000/api/healthz}"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-}"
PREFLIGHT_STRICT="${PREFLIGHT_STRICT:-1}"
SKIP_PULL=${SKIP_PULL:-0}
SKIP_BUILD=${SKIP_BUILD:-0}
NO_BACKUP=${NO_BACKUP:-0}
PREFLIGHT_ONLY=0

_usage() {
  cat <<EOF
Использование: $0 [--skip-pull] [--skip-build] [--no-backup] [--preflight-only]

  --skip-pull      Не обновлять git-репозиторий
  --skip-build     Не пересобирать Docker-образы
  --no-backup      Пропустить резервную копию БД
  --preflight-only Выполнить только preflight-проверки и выйти

Конфигурация (из .env или переменных окружения):
  ENV_FILE              = $ENV_FILE
  PRIMARY_COMPOSE_FILE  = $PRIMARY_COMPOSE_FILE
  SECONDARY_COMPOSE_FILE= $SECONDARY_COMPOSE_FILE
  BACKUP_DIR            = $BACKUP_DIR
  BACKUP_KEEP           = $BACKUP_KEEP
  DB_SERVICE_NAME       = $DB_SERVICE_NAME
  DB_CONTAINER_USER     = $DB_CONTAINER_USER
  DB_CONTAINER_NAME     = $DB_CONTAINER_NAME
  HEALTHCHECK_URL       = $HEALTHCHECK_URL
  HEALTHCHECK_HOST      = $HEALTHCHECK_HOST
  PREFLIGHT_STRICT      = $PREFLIGHT_STRICT
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-pull)       SKIP_PULL=1; shift ;;
    --skip-build)      SKIP_BUILD=1; shift ;;
    --no-backup)       NO_BACKUP=1; shift ;;
    --preflight-only)  PREFLIGHT_ONLY=1; shift ;;
    -h|--help)         _usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1"; _usage; exit 1 ;;
  esac
done

COMPOSE_ARGS=(-f "$PRIMARY_COMPOSE_FILE")
if [[ -n "$SECONDARY_COMPOSE_FILE" && -f "$SECONDARY_COMPOSE_FILE" ]]; then
  COMPOSE_ARGS+=(-f "$SECONDARY_COMPOSE_FILE")
fi

compose_cmd() {
  docker compose --env-file "$ENV_FILE" "${COMPOSE_ARGS[@]}" "$@"
}

log()  { echo "==> $*"; }
warn() { echo "[WARN] $*" >&2; }
die()  { echo "[FAIL] $*" >&2; exit 1; }

is_truthy() {
  local value
  value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

csv_contains_value() {
  local csv="${1:-}"
  local value="${2:-}"
  [[ -n "$value" ]] || return 1
  local normalized=",${csv// /},"
  [[ "$normalized" == *",$value,"* ]]
}

run_preflight() {
  local env_file="$1"
  local strict="${2:-0}"
  [[ -f "$env_file" ]] || die "Файл окружения не найден: $env_file"

  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a

  local errors=()
  local warnings=()

  require_nonempty() {
    local key="$1"
    local value="${!key:-}"
    if [[ -z "$value" ]]; then
      errors+=("$key is required")
    fi
  }

  warn_if_empty() {
    local key="$1"
    local value="${!key:-}"
    if [[ -z "$value" ]]; then
      warnings+=("$key is empty")
    fi
  }

  contains_placeholder() {
    local value
    value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
    [[ "$value" == *"change-me"* || "$value" == *"example"* || "$value" == *"django-insecure-change-me"* ]]
  }

  check_not_placeholder() {
    local key="$1"
    local value="${!key:-}"
    if [[ -n "$value" ]] && contains_placeholder "$value"; then
      errors+=("$key contains placeholder value")
    fi
  }

  require_nonempty "SECRET_KEY"
  require_nonempty "POSTGRES_DB"
  require_nonempty "POSTGRES_USER"
  require_nonempty "POSTGRES_PASSWORD"
  check_not_placeholder "SECRET_KEY"

  if is_truthy "${DEBUG:-false}"; then
    warnings+=("DEBUG should be false on server")
  else
    if ! is_truthy "${SECURE_SSL_REDIRECT:-}"; then
      warnings+=("SECURE_SSL_REDIRECT should be enabled when DEBUG=0")
    fi
    if ! is_truthy "${SESSION_COOKIE_SECURE:-}"; then
      warnings+=("SESSION_COOKIE_SECURE should be enabled when DEBUG=0")
    fi
    if ! is_truthy "${CSRF_COOKIE_SECURE:-}"; then
      warnings+=("CSRF_COOKIE_SECURE should be enabled when DEBUG=0")
    fi
    if [[ "${SECURE_HSTS_SECONDS:-0}" =~ ^[0-9]+$ ]]; then
      if [[ "${SECURE_HSTS_SECONDS:-0}" -le 0 ]]; then
        warnings+=("SECURE_HSTS_SECONDS should be > 0 when DEBUG=0")
      fi
    else
      warnings+=("SECURE_HSTS_SECONDS should be numeric")
    fi
  fi

  if [[ "${ALLOWED_HOSTS:-}" == "*" || -z "${ALLOWED_HOSTS:-}" ]]; then
    warnings+=("ALLOWED_HOSTS should contain explicit hostnames")
  fi
  warn_if_empty "CSRF_TRUSTED_ORIGINS"
  if ! is_truthy "${DEBUG:-false}"; then
    if [[ -z "${DOMAIN:-}" ]]; then
      warnings+=("DOMAIN is empty when DEBUG=0; set DOMAIN for server healthcheck and nginx config")
    else
      if ! csv_contains_value "${ALLOWED_HOSTS:-}" "${DOMAIN}"; then
        warnings+=("ALLOWED_HOSTS should include DOMAIN ($DOMAIN)")
      fi
      if ! csv_contains_value "${CSRF_TRUSTED_ORIGINS:-}" "https://${DOMAIN}"; then
        warnings+=("CSRF_TRUSTED_ORIGINS should include https://$DOMAIN")
      fi
    fi
  fi

  local spam_enabled=0
  local key
  for key in \
    AMOCRM_BASE_URL AMOCRM_ACCESS_TOKEN \
    YANDEX_METRIKA_TOKEN YANDEX_METRIKA_COUNTER_ID YANDEX_METRIKA_OFFLINE_GOAL_ID \
    AMOCRM_SPAM_CLIENT_ID_FIELD_IDS AMOCRM_SPAM_CLIENT_ID_FIELD_CODES AMOCRM_SPAM_CLIENT_ID_FIELD_NAMES; do
    if [[ -n "${!key:-}" ]]; then
      spam_enabled=1
      break
    fi
  done

  if [[ "$spam_enabled" == "1" ]]; then
    require_nonempty "AMOCRM_BASE_URL"
    require_nonempty "AMOCRM_ACCESS_TOKEN"
    require_nonempty "YANDEX_METRIKA_TOKEN"
    require_nonempty "YANDEX_METRIKA_COUNTER_ID"
    require_nonempty "YANDEX_METRIKA_OFFLINE_GOAL_ID"

    check_not_placeholder "AMOCRM_BASE_URL"
    check_not_placeholder "AMOCRM_ACCESS_TOKEN"
    check_not_placeholder "YANDEX_METRIKA_TOKEN"

    if [[ -z "${AMOCRM_SPAM_CLIENT_ID_FIELD_IDS:-}" && -z "${AMOCRM_SPAM_CLIENT_ID_FIELD_CODES:-}" && -z "${AMOCRM_SPAM_CLIENT_ID_FIELD_NAMES:-}" ]]; then
      errors+=("Set at least one mapping variable: AMOCRM_SPAM_CLIENT_ID_FIELD_IDS / _CODES / _NAMES")
    fi
  else
    warnings+=("Spam lead sync integration is not configured")
  fi

  if [[ ${#errors[@]} -gt 0 ]]; then
    echo "[FAIL] Preflight errors:"
    local err
    for err in "${errors[@]}"; do
      echo "  - $err"
    done
    if [[ ${#warnings[@]} -gt 0 ]]; then
      echo ""
      echo "[WARN] Additional warnings:"
      local wrn
      for wrn in "${warnings[@]}"; do
        echo "  - $wrn"
      done
    fi
    exit 1
  fi

  if [[ ${#warnings[@]} -gt 0 ]]; then
    echo "[WARN] Preflight warnings:"
    local warn_msg
    for warn_msg in "${warnings[@]}"; do
      echo "  - $warn_msg"
    done
    if [[ "$strict" == "1" ]]; then
      die "PREFLIGHT_STRICT=1: warnings treated as errors"
    fi
  fi

  echo "[OK] Preflight checks passed ($env_file)"
}

assert_service_running() {
  local service_name="$1"
  if ! compose_cmd ps --status running "$service_name" 2>/dev/null | grep -q "$service_name"; then
    compose_cmd ps || true
    die "Сервис не запущен: $service_name"
  fi
}

resolve_healthcheck_host() {
  if [[ -n "${HEALTHCHECK_HOST:-}" ]]; then
    echo "$HEALTHCHECK_HOST"
    return 0
  fi

  if [[ -n "${DOMAIN:-}" ]]; then
    echo "$DOMAIN"
    return 0
  fi

  local first_allowed="${ALLOWED_HOSTS%%,*}"
  first_allowed="${first_allowed// /}"
  if [[ -n "$first_allowed" && "$first_allowed" != "*" ]]; then
    echo "$first_allowed"
    return 0
  fi

  echo "localhost"
}

log "Деплой $(date '+%Y-%m-%d %H:%M:%S') — $ROOT_DIR"
run_preflight "$ENV_FILE" "$PREFLIGHT_STRICT"
HEALTHCHECK_HOST="$(resolve_healthcheck_host)"

if [[ "$PREFLIGHT_ONLY" == "1" ]]; then
  log "Preflight-only режим: проверки завершены, выходим."
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  log "Docker не найден — устанавливаю..."
  if ! command -v curl >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y curl
  fi
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi
docker info >/dev/null 2>&1 || die "Docker daemon не запущен. Запустите: systemctl start docker"

if ! command -v git >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y git
fi

if [[ "$SKIP_PULL" != "1" && -d .git ]]; then
  git fetch --all --prune -q
  git pull --ff-only -q || die "git pull завершился с ошибкой"
  log "Коммит: $(git log -1 --oneline)"
fi

if [[ "$NO_BACKUP" != "1" ]]; then
  if compose_cmd ps --status running "$DB_SERVICE_NAME" 2>/dev/null | grep -q "$DB_SERVICE_NAME"; then
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/pre-deploy-$(date '+%Y%m%d_%H%M%S').sql.gz"
    compose_cmd exec -T "$DB_SERVICE_NAME" \
      pg_dump -U "$DB_CONTAINER_USER" "$DB_CONTAINER_NAME" \
      | gzip -9 > "$BACKUP_FILE" \
      && log "Бэкап: $(du -sh "$BACKUP_FILE" | cut -f1)" \
      || warn "Не удалось создать резервную копию (продолжаем)"
    (cd "$BACKUP_DIR" && ls -t pre-deploy-*.sql.gz 2>/dev/null | tail -n +"$(( BACKUP_KEEP + 1 ))" | xargs -r rm --)
  fi
fi

if [[ "$SKIP_BUILD" != "1" ]]; then
  docker system prune -f --filter "until=24h" || true
  log "Сборка образов (место: $(df -h / | awk 'NR==2{print $4}'))"
  DOCKER_BUILDKIT=0 compose_cmd build 2>&1 \
    | tee /tmp/docker-build.log \
    | grep -vE "^(Step [0-9]+/[0-9]+ :| ---> |Removing intermediate container |Successfully built |Successfully tagged )" \
    ; [[ "${PIPESTATUS[0]}" -eq 0 ]] || { tail -30 /tmp/docker-build.log; die "Сборка образов завершилась с ошибкой"; }
fi

compose_cmd up -d --remove-orphans

MAX_RETRIES=30
for i in $(seq 1 $MAX_RETRIES); do
  if compose_cmd exec -T "$DB_SERVICE_NAME" pg_isready -U "$DB_CONTAINER_USER" -q 2>/dev/null; then
    break
  fi
  if [[ $i -eq $MAX_RETRIES ]]; then
    die "База данных не стала доступна за ${MAX_RETRIES} попыток"
  fi
  sleep 2
done

compose_cmd exec -T web python manage.py migrate --noinput || die "migrate завершился с ошибкой"
compose_cmd exec -T web python manage.py collectstatic --noinput || die "collectstatic завершился с ошибкой"
compose_cmd exec -T web python manage.py check --deploy || die "manage.py check --deploy завершился с ошибкой"

assert_service_running "web"
assert_service_running "$DB_SERVICE_NAME"
assert_service_running "redis"
assert_service_running "celery_worker"
assert_service_running "celery_beat"

MAX_HEALTH_RETRIES=20
for i in $(seq 1 "$MAX_HEALTH_RETRIES"); do
  if compose_cmd exec -T web python -c "import json,sys,urllib.request; req=urllib.request.Request('$HEALTHCHECK_URL', headers={'Host':'$HEALTHCHECK_HOST','X-Forwarded-Proto':'https'}); body=urllib.request.urlopen(req,timeout=5).read().decode('utf-8'); data=json.loads(body); sys.exit(0 if data.get('status')=='ok' else 1)" >/dev/null 2>&1; then
    break
  fi
  if [[ $i -eq $MAX_HEALTH_RETRIES ]]; then
    die "Healthcheck не прошёл: $HEALTHCHECK_URL (Host: $HEALTHCHECK_HOST)"
  fi
  sleep 2
done

log "Деплой завершён — $(date '+%H:%M:%S')"
compose_cmd ps
log "Деплой завершён: $(date '+%Y-%m-%d %H:%M:%S')"
