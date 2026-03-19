from pathlib import Path
import os
import sys

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me")
DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "*").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
# Trust reverse proxy HTTPS header (nginx sets X-Forwarded-Proto).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Keep API tests independent from server HTTPS redirects.
if "test" in sys.argv:
    SECURE_SSL_REDIRECT = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.users",
    "apps.dashboard",
    "apps.crm",
    "apps.integrations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "bakanov"),
        "USER": os.getenv("POSTGRES_USER", "bakanov"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "bakanov"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"

CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "daily-new-deals-report": {
        "task": "apps.crm.tasks.send_daily_deals_report",
        "schedule": 60 * 60 * 24,
    },
    "daily-telegram-post": {
        "task": "apps.integrations.tasks.publish_evening_telegram_post",
        "schedule": 60 * 60 * 24,
    },
}

AMOCRM_BASE_URL = os.getenv("AMOCRM_BASE_URL", "")
AMOCRM_ACCESS_TOKEN = os.getenv("AMOCRM_ACCESS_TOKEN", "")
AMOCRM_REDIRECT_URI = os.getenv("AMOCRM_REDIRECT_URI", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("SMTP_HOST", "")
EMAIL_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_HOST_USER = os.getenv("SMTP_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.getenv("EMAIL_FROM", "noreply@example.com")
DOCUMENTS_EMAIL_TO = os.getenv("DOCUMENTS_EMAIL_TO", "")

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_MODEL_URI = os.getenv("YANDEX_MODEL_URI", "")
YANDEX_METRIKA_TOKEN = os.getenv("YANDEX_METRIKA_TOKEN", "")
YANDEX_METRIKA_COUNTER_ID = int(os.getenv("YANDEX_METRIKA_COUNTER_ID", "0") or 0)
YANDEX_METRIKA_OFFLINE_GOAL_ID = os.getenv("YANDEX_METRIKA_OFFLINE_GOAL_ID", "")
YANDEX_METRIKA_UPLOAD_TYPE = os.getenv("YANDEX_METRIKA_UPLOAD_TYPE", "BASIC")
STT_PROVIDER = os.getenv("STT_PROVIDER", "deepgram")

CONTRACT_HTML_TEMPLATE = os.getenv("CONTRACT_HTML_TEMPLATE", "contracts/contract.html")
CONTRACT_HTML_TEMPLATE_U = os.getenv("CONTRACT_HTML_TEMPLATE_U", "contracts/contract_u.html")
EXTRA_CONTRACT_HTML_TEMPLATE = os.getenv("EXTRA_CONTRACT_HTML_TEMPLATE", "contracts/extra_contract.html")
CONTRACT_EUR_RATE = float(os.getenv("CONTRACT_EUR_RATE", "100"))
CONTRACT_FILE_FIELD_ID = int(os.getenv("CONTRACT_FILE_FIELD_ID", "0"))
EXTRA_CONTRACT_FILE_FIELD_ID = int(os.getenv("EXTRA_CONTRACT_FILE_FIELD_ID", "0"))
REPORT_META_CACHE_TTL = int(os.getenv("REPORT_META_CACHE_TTL", "172800"))
AMOCRM_DASHBOARD_TIMEOUT = int(os.getenv("AMOCRM_DASHBOARD_TIMEOUT", "6"))

GOOGLE_FORMS_WEBHOOK_SECRET = os.getenv("GOOGLE_FORMS_WEBHOOK_SECRET", "")
GOOGLE_FORMS_TEST_LEAD_ID = int(os.getenv("GOOGLE_FORMS_TEST_LEAD_ID", "0") or 0)
AMOCRM_SPAM_CLIENT_ID_FIELD_IDS = os.getenv("AMOCRM_SPAM_CLIENT_ID_FIELD_IDS", "")
AMOCRM_SPAM_CLIENT_ID_FIELD_CODES = os.getenv("AMOCRM_SPAM_CLIENT_ID_FIELD_CODES", "")
AMOCRM_SPAM_CLIENT_ID_FIELD_NAMES = os.getenv("AMOCRM_SPAM_CLIENT_ID_FIELD_NAMES", "")
