#!/usr/bin/env bash
# init.sh — первичная настройка сервера для Bakanov API
#
# Использование:
#   sudo ./init.sh
#
set -Eeuo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${GREEN}==>${RESET} ${BOLD}$*${RESET}"; }
warn() { echo -e "${YELLOW}[WARN]${RESET} $*" >&2; }
die()  { echo -e "${RED}[FAIL]${RESET} $*" >&2; exit 1; }
step() { echo -e "\n${BOLD}━━━  $* ${RESET}"; }

[[ "$EUID" -eq 0 ]] || die "Запустите от root: sudo ./init.sh"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env"
[[ -f "$ENV_FILE" ]] || die ".env не найден в $ROOT_DIR\nСоздайте его: cp .env.example .env && nano .env"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DOMAIN="${DOMAIN:-}"
WWW_DOMAIN="${WWW_DOMAIN:-}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
CERTBOT_WEBROOT="${CERTBOT_WEBROOT:-/var/www/certbot}"
APP_UPSTREAM="${APP_UPSTREAM:-127.0.0.1:8000}"
NGINX_CONF_PATH="${NGINX_CONF_PATH:-/etc/nginx/conf.d/bakanov_api.conf}"

errors=()
[[ -z "${DOMAIN}" ]] && errors+=("DOMAIN не задан")
[[ -z "${CERTBOT_EMAIL}" ]] && errors+=("CERTBOT_EMAIL не задан")
[[ -z "${SECRET_KEY:-}" ]] && errors+=("SECRET_KEY не задан")
[[ -z "${POSTGRES_PASSWORD:-}" ]] && errors+=("POSTGRES_PASSWORD не задан")
[[ -z "${POSTGRES_DB:-}" ]] && errors+=("POSTGRES_DB не задан")
[[ -z "${POSTGRES_USER:-}" ]] && errors+=("POSTGRES_USER не задан")

if [[ ${#errors[@]} -gt 0 ]]; then
  echo -e "${RED}ОШИБКА: заполните в .env:${RESET}"
  for e in "${errors[@]}"; do echo "  • $e"; done
  exit 1
fi

PREFLIGHT_STRICT="${PREFLIGHT_STRICT:-1}"
PREFLIGHT_STRICT="$PREFLIGHT_STRICT" bash "$ROOT_DIR/deploy.sh" --preflight-only || die "Preflight проверки не пройдены"

if [[ "$DOMAIN" == "localhost" || "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  die "'$DOMAIN' не является реальным DNS-именем"
fi

if [[ -n "$WWW_DOMAIN" && "$WWW_DOMAIN" == "$DOMAIN" ]]; then
  WWW_DOMAIN=""
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║        ${DOMAIN} — Bakanov API / beta setup                 ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${RESET}"
echo "  Домен   : $DOMAIN${WWW_DOMAIN:+ / $WWW_DOMAIN}"
echo "  E-mail  : $CERTBOT_EMAIL"
echo "  Каталог : $ROOT_DIR"
echo ""

step "1/5  Системные зависимости"
apt-get update -qq

TOTAL_RAM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [[ $TOTAL_RAM_MB -lt 2048 ]] && ! swapon --show | grep -q /swapfile; then
  SWAP_SIZE="1G"
  log "RAM ${TOTAL_RAM_MB}MB < 2GB — создаю swapfile ${SWAP_SIZE}..."
  fallocate -l "$SWAP_SIZE" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl vm.swappiness=10
  echo 'vm.swappiness=10' >> /etc/sysctl.conf
  log "Swap ${SWAP_SIZE} активирован (swappiness=10)"
fi

if ! command -v curl >/dev/null 2>&1; then
  apt-get install -y curl
fi

if ! command -v git >/dev/null 2>&1; then
  log "Установка git..."
  apt-get install -y git
fi

if ! command -v nginx >/dev/null 2>&1; then
  log "Установка nginx (official repo)..."
  curl -fsSL https://nginx.org/keys/nginx_signing.key | gpg --dearmor -o /usr/share/keyrings/nginx.gpg
  echo "deb [signed-by=/usr/share/keyrings/nginx.gpg] https://nginx.org/packages/mainline/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) nginx" \
    > /etc/apt/sources.list.d/nginx.list
  apt-get update -qq && apt-get install -y nginx
fi

if ! command -v certbot >/dev/null 2>&1; then
  log "Установка certbot..."
  if command -v snap >/dev/null 2>&1; then
    snap install --classic certbot
    ln -sf /snap/bin/certbot /usr/bin/certbot
  else
    apt-get install -y certbot
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  log "Установка Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

docker info >/dev/null 2>&1 || die "Docker daemon не запущен"
log "Все зависимости установлены"

step "2/5  Подготовка"
mkdir -p \
  "${BACKUP_DIR:-$ROOT_DIR/backups}" \
  "$ROOT_DIR/staticfiles" \
  "$ROOT_DIR/media" \
  "$CERTBOT_WEBROOT/.well-known/acme-challenge"

if [[ -f /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

step "3/5  TLS-сертификат Let's Encrypt"
SERVER_NAMES="$DOMAIN"
if [[ -n "$WWW_DOMAIN" ]]; then
  SERVER_NAMES="$SERVER_NAMES $WWW_DOMAIN"
fi

# Временный HTTP-конфиг для ACME challenge (без остановки nginx).
mkdir -p "$(dirname "$NGINX_CONF_PATH")"
cat > "$NGINX_CONF_PATH" <<EOF
server {
    listen 80;
    server_name $SERVER_NAMES;

    location ^~ /.well-known/acme-challenge/ {
        alias $CERTBOT_WEBROOT/.well-known/acme-challenge/;
        default_type "text/plain";
        try_files \$uri =404;
    }

    location / {
        return 200 "ACME challenge endpoint";
        add_header Content-Type text/plain;
    }
}
EOF

nginx -t
systemctl enable --now nginx
systemctl reload nginx

CERTBOT_DOMAIN_ARGS=("-d" "$DOMAIN")
if [[ -n "$WWW_DOMAIN" ]]; then
  CERTBOT_DOMAIN_ARGS+=("-d" "$WWW_DOMAIN")
fi

certbot certonly \
  --webroot \
  -w "$CERTBOT_WEBROOT" \
  --non-interactive \
  --agree-tos \
  --email "$CERTBOT_EMAIL" \
  "${CERTBOT_DOMAIN_ARGS[@]}"

step "4/5  Nginx (HTTPS)"
mkdir -p "$(dirname "$NGINX_CONF_PATH")"
cat > "$NGINX_CONF_PATH" <<EOF
server {
    listen 80;
    server_name $SERVER_NAMES;

    location ^~ /.well-known/acme-challenge/ {
        alias $CERTBOT_WEBROOT/.well-known/acme-challenge/;
        default_type "text/plain";
        try_files \$uri =404;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name $SERVER_NAMES;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location /media/ {
        alias $ROOT_DIR/media/;
        access_log off;
        expires 7d;
    }

    location /static/ {
        alias $ROOT_DIR/staticfiles/;
        access_log off;
        expires 7d;
    }

    location / {
        proxy_pass http://$APP_UPSTREAM;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF

nginx -t
systemctl enable --now nginx
systemctl reload nginx

cat > /etc/systemd/system/certbot-renew.service <<EOF
[Unit]
Description=Certbot Renewal

[Service]
Type=oneshot
ExecStart=/bin/sh -lc '/usr/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx || true"'
WorkingDirectory=$ROOT_DIR
EOF

cat > /etc/systemd/system/certbot-renew.timer <<EOF
[Unit]
Description=Run certbot-renew twice daily

[Timer]
OnCalendar=*-*-* 03,15:00:00
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now certbot-renew.timer

step "5/5  Деплой"
bash "$ROOT_DIR/deploy.sh" --skip-pull --no-backup

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║  ✓  Установка завершена                                  ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════╝${RESET}"
echo -e "  Сайт   : ${BOLD}https://$DOMAIN${RESET}"
echo -e "  Логи   : docker compose logs -f"
echo -e "  Деплой : ./deploy.sh"
echo ""
