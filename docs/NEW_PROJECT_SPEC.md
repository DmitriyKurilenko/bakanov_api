# Спецификация нового проекта: Универсальная CRM-платформа

> Этот файл — полная спецификация для старта проекта с нуля в новой директории.
> Содержит архитектуру, модели данных, бизнес-логику, стек и порядок реализации.

---

## 1. Назначение

SaaS-платформа для организаций, интегрируемая с Битрикс24 и amoCRM.

**Первоначальный функционал:**
- Создание договоров из настраиваемых шаблонов и подписание онлайн (OTP)
- Распределение заявок между менеджерами по настраиваемым правилам
- Мульти-тенантность: каждая организация — изолированный клиент платформы
- Личный кабинет организации: управление интеграциями, менеджерами, шаблонами, настройками
- Настраиваемые подписки: админ платформы определяет тарифы и доступные функции per-план
- Аудит-лог: полная история действий пользователей (кто, когда, что изменил)
- Уведомления: email + in-app + Telegram, настраиваемые per-tenant
- Онбординг-визард: пошаговая настройка организации после регистрации
- Мессенджеры → CRM: двусторонний мост Telegram/WhatsApp/MAX ↔ amoCRM/Битрикс24 (клиент пишет в мессенджер, менеджер отвечает в CRM)
- Встроенная телефония (FreeSWITCH): входящие/исходящие звонки, WebRTC из браузера, SIP-транки, запись разговоров, IVR, интеграция с CRM

---

## 2. Стек технологий

| Компонент | Технология | Версия | Примечание |
|-----------|-----------|--------|------------|
| Backend | Django LTS | 5.2.* | Последний LTS (поддержка до апреля 2028) |
| Язык | Python | 3.13 | Docker: `python:3.13-slim` |
| БД | PostgreSQL | 17 | Docker: `postgres:17`, schema-based мульти-тенантность |
| Кэш / брокер | Redis | 7.4 | Docker: `redis:7.4-alpine`, Celery broker + cache |
| Очереди | Celery + Beat | 5.6 | Tenant-aware задачи |
| API | django-ninja | 1.6 | OpenAPI из коробки |
| Мульти-тенант | django-tenants | 3.10 | Schema per tenant |
| PDF | WeasyPrint | 68 | Генерация договоров |
| БД-адаптер | psycopg | 3.3 | Заменяет psycopg2 |
| Шифрование | django-fernet-encrypted-fields | 0.3 | Шифрование credentials CRM |
| HTTP-клиент | requests | 2.33 | Вызовы API CRM |
| ASGI-сервер | uvicorn + gunicorn | 0.34 / 25 | uvicorn — ASGI worker; gunicorn — process manager (`-k uvicorn.workers.UvicornWorker`) |
| Real-time | Django Channels + channels-redis | 4.2 / 4.2 | WebSocket: уведомления, статус звонков, Kanban live-sync |
| Фронтенд | Vue 3 + Vite | 3.5 / 6.x | SPA, отдельное приложение `frontend/` |
| UI-компоненты | PrimeVue | 4.x | DataTable, TreeSelect, Stepper, Chart, Dialog |
| CSS | Tailwind CSS | 4 | Собирается Vite, не CDN |
| State management | Pinia | 3.x | Сторы: auth, calls, notifications, crm |
| Маршрутизация | Vue Router | 4.x | Клиентская навигация |
| WebRTC | SIP.js | 0.21 | Звонки из браузера через FreeSWITCH WSS |
| Иконки | PrimeIcons + Font Awesome | CDN | |
| Node.js | Node.js LTS | 24 | Docker: `node:24-alpine` (билд + dev server) |
| Телефония | FreeSWITCH | 1.10 | Docker: `signalwire/freeswitch-public`, ESL + WebRTC |
| SIP-транки | Провайдеры | — | Zadarma, MCN Telecom, Ростелеком и др. |
| Деплой | Docker / docker-compose | — | Единственная среда разработки и деплоя |

**Критично:**
- Docker-only разработка. Никаких `pip install`, `brew install`, `npm install -g` на хосте
- Все команды через `docker compose exec` / `docker compose run --rm`
- Frontend (Vue SPA) и Backend (Django API) — раздельные приложения. Django не рендерит HTML для ЛК (Django templates только для публичных страниц: /sign/{token}/, /admin/)

---

## 3. Структура приложений

```
project_root/
├── config/
│   ├── settings.py          # Django settings, django-tenants config
│   ├── urls.py               # URL routing (public + tenant)
│   ├── api.py                # django-ninja API root
│   ├── celery.py             # Celery config (tenant-aware)
│   ├── routing.py            # Django Channels WebSocket routing
│   ├── wsgi.py
│   └── asgi.py               # ASGI entrypoint (HTTP + WebSocket)
├── apps/
│   ├── tenants/              # Организации, домены
│   ├── billing/              # Тарифы, подписки, feature-gating
│   ├── users/                # Пользователи, роли, членство, приглашения
│   ├── contracts/            # Шаблоны договоров, генерация PDF, подписание OTP
│   ├── distribution/         # Правила распределения заявок, стратегии
│   ├── integrations/         # CRM-адаптеры (Amo, Bitrix24), вебхуки
│   ├── channels/             # Мессенджер-каналы (Telegram/WhatsApp/MAX → CRM мост)
│   ├── telephony/            # Встроенная телефония (FreeSWITCH), SIP-транки, WebRTC
│   ├── crm/                  # Встроенный CRM: воронки, сделки, контакты, активности
│   ├── audit/                # Аудит-лог действий пользователей
│   ├── notifications/        # Уведомления (email, in-app, Telegram)
│   └── core/                 # Утилиты: EncryptedJSONField (fields.py). Не Django-app, не в INSTALLED_APPS
├── templates/                    # Только публичные страницы: /sign/{token}/, email-шаблоны
├── frontend/                     # Vue 3 SPA (ЛК организации)
│   ├── src/
│   │   ├── views/            # Страницы: Dashboard, CRM, Integrations, Telephony, ...
│   │   ├── components/       # UI-компоненты: SoftPhone, IvrBuilder, KanbanBoard, ...
│   │   ├── composables/      # useSIPPhone(), useNotifications(), useAuth(), useFeatureGate()
│   │   ├── stores/           # Pinia: auth, tenant, calls, notifications, crm
│   │   ├── api/              # HTTP-клиент к Django API (axios/ofetch)
│   │   ├── router/           # Vue Router (клиентский routing)
│   │   ├── layouts/          # На базе Sakai (sidebar + header + breadcrumbs + dark mode)
│   │   └── App.vue
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
├── docs/
├── Dockerfile
├── Dockerfile.frontend           # Мультистейдж: node build + nginx serve
├── docker-compose.yml
├── requirements.txt
└── manage.py
```

---

## 4. Мульти-тенантность (django-tenants)

### Принцип
- Каждая организация = отдельная PostgreSQL schema
- `public` schema — shared таблицы (тенанты, пользователи, тарифы)
- Tenant schema — бизнес-данные (договоры, правила, CRM-подключения, менеджеры)
- Роутинг по домену: `company.platform.ru` → schema `company`

### settings.py ключевые настройки

```python
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        # ...PostgreSQL connection
    }
}

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',
    # ... остальные
]

SHARED_APPS = [
    'django_tenants',
    'apps.tenants',
    'apps.billing',
    'apps.users',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'ninja_jwt',                   # JWT auth (ninja-нативный, без DRF)
    'ninja_jwt.token_blacklist',    # для BLACKLIST_AFTER_ROTATION
    'corsheaders',
    'channels',                     # Django Channels (ASGI + WebSocket)
]

TENANT_APPS = [
    'apps.contracts',
    'apps.distribution',
    'apps.integrations',
    'apps.channels',
    'apps.telephony',
    'apps.crm',
    'apps.audit',
    'apps.notifications',
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

TENANT_MODEL = 'tenants.Tenant'
TENANT_DOMAIN_MODEL = 'tenants.Domain'

AUTH_USER_MODEL = 'users.User'

# --- ASGI + Django Channels ---
ASGI_APPLICATION = 'config.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [env('REDIS_URL', default='redis://redis:6379/0')],
        },
    },
}
```

---

## 5. Модели данных

### 5.1 `apps/tenants/models.py` (shared schema)

```python
from django_tenants.models import TenantMixin, DomainMixin

class Tenant(TenantMixin):
    name = models.CharField(max_length=200)             # "ООО Ромашка"
    slug = models.SlugField(unique=True)                 # "romashka" → schema name
    plan = models.ForeignKey(
        'billing.Plan', on_delete=models.PROTECT,
        related_name='tenants',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Настройки ЛК организации
    logo = models.ImageField(upload_to='tenants/logos/', blank=True)
    brand_color = models.CharField(max_length=7, default='#570DF8')  # HEX
    timezone = models.CharField(max_length=50, default='Europe/Moscow')
    language = models.CharField(max_length=5, default='ru')

    # CRM-режим
    crm_mode = models.CharField(
        max_length=20,
        choices=[('builtin', 'Встроенный CRM'), ('bitrix24', 'Битрикс24'), ('amocrm', 'amoCRM')],
        default='builtin',
    )

    # Онбординг
    onboarding_step = models.PositiveIntegerField(default=0)  # 0=не начат, 5=завершён

    auto_create_schema = True

class Domain(DomainMixin):
    pass  # tenant FK + domain + is_primary (из DomainMixin)
```

### 5.1b `apps/billing/models.py` (shared schema)

```python
class Feature(models.Model):
    """Атомарная функция платформы. Создаётся и управляется только админом платформы."""
    code = models.CharField(max_length=50, unique=True)        # Машинное имя
    # Коды функций (зашиты в код, проверяются декоратором):
    #   'distribution'           — распределение заявок
    #   'contracts'              — создание договоров
    #   'contract_signing'       — онлайн-подписание (OTP)
    #   'crm_bitrix24'           — интеграция с Битрикс24
    #   'crm_amocrm'             — интеграция с amoCRM
    #   'analytics'              — дашборд и аналитика
    #   'export_pdf'             — экспорт отчётов в PDF
    #   'export_excel'           — экспорт отчётов в Excel
    #   'custom_contract_templates' — собственные шаблоны договоров (иначе — только встроенные)
    #   'api_access'             — доступ к API для внешних интеграций
    #   'messenger_channels'     — мессенджер-каналы (Telegram/WhatsApp/MAX → CRM)
    #   'telephony'              — телефония (АТС → CRM, записи звонков)
    #   'crm_builtin'            — встроенный CRM (воронки, сделки, контакты, Kanban)
    name = models.CharField(max_length=200)                    # Человекочитаемое: "Распределение заявок"
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Plan(models.Model):
    """Тарифный план. Определяет набор доступных функций и лимиты."""
    name = models.CharField(max_length=100)                    # "Простая", "Базовая", "СРМ"
    slug = models.SlugField(unique=True)                       # "simple", "basic", "crm"
    features = models.ManyToManyField(Feature, related_name='plans', blank=True)
    # Лимиты (null = безлимит)
    max_managers = models.PositiveIntegerField(null=True, blank=True)   # Макс. менеджеров
    max_contracts_per_month = models.PositiveIntegerField(null=True, blank=True)
    max_crm_connections = models.PositiveIntegerField(null=True, blank=True, default=1)
    max_pipelines = models.PositiveIntegerField(null=True, blank=True, default=1)     # Воронки во встроенном CRM
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)              # Можно скрыть устаревший план
    sort_order = models.PositiveIntegerField(default=0)        # Порядок отображения
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return self.name

    def has_feature(self, feature_code: str) -> bool:
        """Проверка доступности функции в плане."""
        return self.features.filter(code=feature_code).exists()
```

**Пример конфигурации планов (создаётся админом через Django Admin):**

| План | Функции | Лимиты |
|------|---------|--------|
| Простая | `distribution`, `contracts`, `crm_bitrix24`, `crm_amocrm` | 5 менеджеров, 1 CRM-подключение, 50 договоров/мес |
| Базовая | всё из Простой + `contract_signing`, `messenger_channels`, `telephony`, `analytics` | 15 менеджеров, 2 CRM-подключения, 200 договоров/мес |
| СРМ | всё из Базовой + `crm_builtin`, `custom_contract_templates`, `export_pdf`, `export_excel`, `api_access` | Безлимит менеджеров, 5 CRM-подключений, 10 воронок, безлимит договоров |

**Feature-gating (проверка доступа к функции):**

```python
# apps/billing/guards.py
from django.http import HttpResponseForbidden
from functools import wraps

def require_feature(feature_code: str):
    """Декоратор для view/API. Проверяет, что функция доступна в плане тенанта."""
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            tenant = request.tenant
            if not tenant.plan.has_feature(feature_code):
                return HttpResponseForbidden(
                    f'Функция "{feature_code}" недоступна в вашем тарифе. '
                    f'Текущий план: {tenant.plan.name}.'
                )
            return func(request, *args, **kwargs)
        return wrapper
    return decorator

def check_limit(tenant, limit_field: str, current_count: int) -> bool:
    """Проверка лимитов плана. None = безлимит."""
    limit = getattr(tenant.plan, limit_field)
    if limit is None:
        return True
    return current_count < limit
```

**Использование в API:**
```python
@api.post('/contracts/generate')
@require_feature('contracts')
def generate_contract(request, payload: ContractGenerateSchema):
    ...

@api.post('/contracts/{id}/send-for-signing/')
@require_feature('contract_signing')
def send_for_signing(request, id: int):
    ...

@api.post('/distribution/rules/')
@require_feature('distribution')
def create_distribution_rule(request, payload: DistributionRuleSchema):
    ...
```

### 5.2 `apps/users/models.py` (shared schema)

```python
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    """Пользователь платформы. Один аккаунт — доступ к нескольким организациям."""
    email = models.EmailField(unique=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

class Membership(models.Model):
    """Связь пользователя с тенантом. Shared schema — виден из любого контекста."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(
        max_length=20,
        choices=[
            ('owner', 'Owner'),
            ('admin', 'Admin'),
            ('manager', 'Manager'),
            ('viewer', 'Viewer'),
        ],
    )
    is_active = models.BooleanField(default=True)
    invite_token = models.UUIDField(null=True, blank=True)
    invited_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'tenant')
```

**Важно:** `Membership` — shared модель (в `SHARED_APPS`), потому что пользователю нужен доступ к списку своих организаций до выбора тенанта.

### 5.3 `apps/integrations/models.py` (tenant schema)

```python
class CRMConnection(models.Model):
    """Подключение к внешней CRM. Один тенант может иметь несколько подключений."""
    CRM_TYPES = [('amocrm', 'amoCRM'), ('bitrix24', 'Битрикс24')]

    crm_type = models.CharField(max_length=20, choices=CRM_TYPES)
    name = models.CharField(max_length=200)                    # "Основной amoCRM"
    credentials = EncryptedJSONField()                       # Зашифровано (Fernet, ключ в FIELD_ENCRYPTION_KEY)
    # Для amoCRM: {"base_url": "https://x.amocrm.ru/api/v4", "access_token": "...", "refresh_token": "...", "client_id": "...", "client_secret": "...", "redirect_uri": "..."}
    # Для Bitrix24 webhook: {"webhook_url": "https://x.bitrix24.ru/rest/1/abc/"}
    # Для Bitrix24 OAuth: {"member_id": "...", "access_token": "...", "refresh_token": "...", "domain": "x.bitrix24.ru", "app_id": "...", "app_secret": "..."}
    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

class WebhookEndpoint(models.Model):
    """Входящий вебхук от CRM. URL генерируется автоматически."""
    crm_connection = models.ForeignKey(CRMConnection, on_delete=models.CASCADE, related_name='webhooks')
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)  # unique=True уже создаёт индекс
    event_type = models.CharField(max_length=100)              # "lead.add", "deal.update"
    secret_token = models.CharField(max_length=64)             # Для верификации
    is_active = models.BooleanField(default=True)
    # URL: /wh/{tenant_slug}/{webhook.uuid}/

class ManagerProfile(models.Model):
    """Профиль менеджера в контексте тенанта. Связь с CRM-пользователем (внешним) или автономный (встроенный CRM)."""
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='+')
    crm_connection = models.ForeignKey(
        CRMConnection, on_delete=models.SET_NULL,
        related_name='managers', null=True, blank=True,
    )  # null при crm_mode='builtin' или после удаления CRM-подключения
    crm_user_id = models.CharField(max_length=100, blank=True)  # ID менеджера в внешней CRM (пусто для builtin)
    crm_user_name = models.CharField(max_length=200)
    max_active_deals = models.PositiveIntegerField(default=10)
    schedule = models.JSONField(default=dict)
    # {"mon": true, "tue": true, "wed": true, "thu": true, "fri": true, "sat": false, "sun": false}
    is_active = models.BooleanField(default=True)

class ManagerDayOff(models.Model):
    manager = models.ForeignKey(ManagerProfile, on_delete=models.CASCADE, related_name='days_off')
    date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)
```

### 5.4 `apps/integrations/adapters.py` — CRM-адаптер (Protocol)

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass
class LeadData:
    id: str
    name: str
    price: int | None
    responsible_user_id: str | None
    contacts: list[dict]          # [{"id": "...", "name": "...", "phone": "...", "email": "..."}]
    custom_fields: dict            # Произвольные поля CRM
    created_at: str
    updated_at: str

@dataclass
class CRMUser:
    id: str
    name: str
    email: str | None
    is_active: bool

@runtime_checkable
class CRMAdapter(Protocol):
    """Единый интерфейс для работы с любой CRM."""

    def get_lead(self, lead_id: str) -> LeadData: ...
    def get_deal(self, deal_id: str) -> LeadData: ...
    def get_contact(self, contact_id: str) -> dict: ...
    def update_lead(self, lead_id: str, fields: dict) -> None: ...
    def upload_file(self, entity_type: str, entity_id: str, file: bytes, filename: str) -> str: ...
    def list_users(self) -> list[CRMUser]: ...
    def set_responsible(self, entity_type: str, entity_id: str, user_id: str) -> None: ...

    # --- Мессенджер-каналы (чат → CRM) ---
    def register_chat_channel(self, channel_id: str, channel_name: str, webhook_url: str) -> str: ...
    # amoCRM: регистрация через Chats API (amojo), Bitrix24: через Open Lines connector API
    # Возвращает scope_id / connector_id для маршрутизации
    def send_message_to_crm(self, scope_id: str, chat_id: str, sender: dict, text: str, attachments: list = None) -> str: ...
    # amoCRM: POST /api/v4/chats/{chat_id}/messages, Bitrix24: imopenlines.message.add
    # sender = {"id": "tg_12345", "name": "Иван Петров", "avatar": "..."}
    def receive_outgoing_message(self, payload: dict) -> dict: ...
    # Парсинг ответа менеджера из CRM → {"chat_id": ..., "text": ..., "attachments": [...]}

    # --- Телефония (звонки → CRM) ---
    def register_call(self, call_data: dict) -> str: ...
    # Создать запись о звонке в CRM: тип, направление, длительность, запись, контакт
    # amoCRM: POST /api/v4/calls, Bitrix24: telephony.externalcall.register + finish
    def attach_call_record(self, call_id: str, record_url: str) -> None: ...
    # Прикрепить запись разговора к звонку в CRM
```

Реализации: `AmoCRMAdapter(CRMAdapter)`, `Bitrix24Adapter(CRMAdapter)`, `BuiltinCRMAdapter(CRMAdapter)` — каждая в отдельном файле.

**BuiltinCRMAdapter** (`apps/crm/adapter.py`):
```python
class BuiltinCRMAdapter:
    """CRM-адаптер для встроенного CRM. Работает напрямую с ORM вместо HTTP-запросов."""

    def get_lead(self, lead_id: str) -> LeadData:
        deal = Deal.objects.select_related('contact', 'company').get(id=lead_id)
        return LeadData(
            id=str(deal.id), name=deal.name, price=deal.amount,
            responsible_user_id=str(deal.responsible_id) if deal.responsible else None,
            contacts=[_contact_to_dict(deal.contact)] if deal.contact else [],
            custom_fields=deal.custom_fields,
            created_at=deal.created_at.isoformat(),
            updated_at=deal.updated_at.isoformat(),
        )

    def set_responsible(self, entity_type, entity_id, user_id):
        model = Deal if entity_type in ('lead', 'deal') else Contact
        model.objects.filter(id=entity_id).update(responsible_id=user_id)

    def register_call(self, call_data):
        """Создать Activity типа 'call' привязанную к сделке/контакту."""
        activity = Activity.objects.create(
            activity_type='call', deal_id=call_data.get('deal_id'),
            contact_id=call_data.get('contact_id'),
            title=call_data.get('title', 'Звонок'),
            related_call_id=call_data.get('call_record_id'),
        )
        return str(activity.id)

    def send_message_to_crm(self, scope_id, chat_id, sender, text, attachments=None):
        """Создать Activity типа 'message' привязанную к контакту/сделке."""
        activity = Activity.objects.create(
            activity_type='message', contact_id=scope_id,
            title=f'Сообщение от {sender["name"]}', body=text,
        )
        return str(activity.id)

    # ... остальные методы протокола
```

**Примечание:** `BuiltinCRMAdapter` реализует весь `CRMAdapterProtocol`, но некоторые методы
работают локально (не HTTP), а некоторые — no-op:
- `register_chat_channel` → no-op (каналы уже в системе)
- `receive_outgoing_message` → no-op (ответы уходят напрямую в мессенджер)
- `attach_call_record` → обновляет Activity.related_call
- `upload_file` → сохраняет в Django FileField

**Фабрика:**
```python
def get_adapter(connection: CRMConnection) -> CRMAdapter:
    adapters = {
        'amocrm': AmoCRMAdapter,
        'bitrix24': Bitrix24Adapter,
    }
    cls = adapters[connection.crm_type]
    return cls(connection.credentials)

def get_adapter_for_tenant(tenant) -> CRMAdapter:
    """Получить адаптер с учётом crm_mode тенанта."""
    if tenant.crm_mode == 'builtin':
        return BuiltinCRMAdapter()
    connection = CRMConnection.objects.filter(
        crm_type=tenant.crm_mode, is_active=True
    ).first()
    if not connection:
        raise ValueError(f'No active {tenant.crm_mode} connection')
    return get_adapter(connection)
```

### 5.5 `apps/contracts/models.py` (tenant schema)

```python
class ContractTemplate(models.Model):
    """Шаблон договора. HTML с Django template-переменными."""
    name = models.CharField(max_length=200)                    # "Основной договор"
    version = models.PositiveIntegerField(default=1)
    html_body = models.TextField()                             # Django template: {{ client_name }}, {{ price }}
    variable_schema = models.JSONField(default=list)
    # [
    #   {"key": "client_name", "label": "ФИО клиента", "type": "string", "required": true},
    #   {"key": "price", "label": "Сумма", "type": "number", "required": true},
    #   {"key": "start_date", "label": "Дата начала", "type": "date", "required": true},
    #   {"key": "passport_series", "label": "Серия паспорта", "type": "string", "required": false},
    # ]
    # Маппинг на CRM-поля делается в UI: пользователь связывает variable_schema[].key с полями CRM
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class FieldMapping(models.Model):
    """Маппинг переменных шаблона на поля CRM. При crm_mode='builtin' crm_connection=null — маппинг не используется."""
    template = models.ForeignKey(ContractTemplate, on_delete=models.CASCADE, related_name='field_mappings')
    crm_connection = models.ForeignKey(
        'integrations.CRMConnection', on_delete=models.CASCADE,
        null=True, blank=True,
    )  # null при crm_mode='builtin' — данные берутся из встроенного CRM напрямую
    variable_key = models.CharField(max_length=100)            # "client_name"
    crm_field_path = models.CharField(max_length=200)          # "contacts[0].name" или "custom_fields.123456"
    # При генерации: система берёт данные из CRM через адаптер, по crm_field_path достаёт значение,
    # подставляет в шаблон по variable_key

class Contract(models.Model):
    """Сгенерированный договор."""
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('sent', 'Отправлен'),
        ('viewed', 'Просмотрен'),
        ('signed', 'Подписан'),
        ('expired', 'Истёк'),
        ('cancelled', 'Отменён'),
    ]
    SIGNING_METHODS = [
        ('sms_otp', 'SMS-код'),
        ('email_otp', 'Email-код'),
    ]

    template = models.ForeignKey(ContractTemplate, on_delete=models.SET_NULL, null=True)
    template_version = models.PositiveIntegerField()           # Фиксируем версию на момент генерации

    crm_connection = models.ForeignKey('integrations.CRMConnection', on_delete=models.SET_NULL, null=True, blank=True)
    crm_entity_type = models.CharField(max_length=20)          # "lead", "deal"
    crm_entity_id = models.CharField(max_length=100)
    deal = models.ForeignKey(
        'crm.Deal', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contracts',
    )  # FK на встроенную сделку (при crm_mode='builtin'). Для внешних CRM — null.

    filled_data = models.JSONField()                           # {"client_name": "Иванов И.И.", "price": 50000, ...}
    pdf_file = models.FileField(upload_to='contracts/%Y/%m/')
    html_snapshot = models.TextField()                         # HTML на момент генерации (для воспроизводимости)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    signing_method = models.CharField(max_length=20, choices=SIGNING_METHODS, default='sms_otp')

    signed_at = models.DateTimeField(null=True, blank=True)
    signer_ip = models.GenericIPAddressField(null=True, blank=True)
    signer_user_agent = models.TextField(blank=True, default='')

    expires_at = models.DateTimeField(null=True, blank=True)   # Срок действия ссылки на подписание
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)

class SigningSession(models.Model):
    """Сессия подписания. Одна на попытку подписания."""
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='signing_sessions')
    token = models.UUIDField(default=uuid.uuid4, unique=True)  # Уникальная ссылка (unique уже создаёт индекс)
    otp_code_hash = models.CharField(max_length=128)           # Хэш OTP-кода (НИКОГДА не хранить plaintext)
    otp_sent_to = models.CharField(max_length=200)             # Телефон или email
    otp_sent_at = models.DateTimeField(auto_now_add=True)
    otp_expires_at = models.DateTimeField()                    # Обычно +10 минут
    attempts = models.PositiveIntegerField(default=0)          # Макс. 5, потом блокировка
    verified_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
```

### 5.6 `apps/distribution/models.py` (tenant schema)

```python
class DistributionRule(models.Model):
    """Правило распределения заявок."""
    TRIGGER_CHOICES = [
        ('new_lead', 'Новая заявка'),
        ('new_deal', 'Новая сделка'),
        ('stage_change', 'Смена стадии'),
    ]
    STRATEGY_CHOICES = [
        ('min_load', 'Минимальная нагрузка'),
        ('round_robin', 'По очереди'),
        ('weighted', 'Взвешенное'),
        ('manual_queue', 'Ручная очередь'),
    ]

    name = models.CharField(max_length=200)
    crm_connection = models.ForeignKey(
        'integrations.CRMConnection', on_delete=models.SET_NULL,
        null=True, blank=True,
    )  # null при crm_mode='builtin' или после удаления CRM-подключения

    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES)
    trigger_filter = models.JSONField(default=dict)
    # {"pipeline_id": "123", "status_id": "456"}
    # Пустой = все заявки этого типа

    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES, default='min_load')
    strategy_config = models.JSONField(default=dict)
    # Для weighted: {"manager_weights": {"profile_id_1": 30, "profile_id_2": 30, "profile_id_3": 40}}
    # Для round_robin: {"last_assigned_index": 2}
    # Для min_load: {"period_days": 7, "count_metric": "assigned"} — за какой период считать нагрузку

    managers = models.ManyToManyField('integrations.ManagerProfile', related_name='distribution_rules', blank=True)
    # Пул менеджеров для этого правила. Пустой = все активные.

    fallback_manager = models.ForeignKey(
        'integrations.ManagerProfile', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fallback_rules',
    )

    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=0)          # Выше число = выше приоритет
    created_at = models.DateTimeField(auto_now_add=True)

class DistributionLog(models.Model):
    """Лог распределения. Кому, когда, почему."""
    SOURCE_CHOICES = [
        ('crm_webhook', 'CRM-вебхук'),
        ('messenger', 'Мессенджер'),
        ('phone_call', 'Телефонный звонок'),
        ('manual', 'Ручное'),
    ]
    rule = models.ForeignKey(DistributionRule, on_delete=models.SET_NULL, null=True)
    crm_connection = models.ForeignKey('integrations.CRMConnection', on_delete=models.SET_NULL, null=True)
    crm_entity_type = models.CharField(max_length=20)
    crm_entity_id = models.CharField(max_length=100)
    assigned_to = models.ForeignKey('integrations.ManagerProfile', on_delete=models.SET_NULL, null=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='crm_webhook')
    strategy_used = models.CharField(max_length=20)
    reason = models.TextField()                                # "min_load: 3 active deals, lowest among 5 candidates"
    created_at = models.DateTimeField(auto_now_add=True)
```

### 5.7 `apps/channels/models.py` (tenant schema)

```python
class MessengerChannel(models.Model):
    """Мессенджер-канал, привязанный к CRM-подключению. Мост: мессенджер ↔ CRM."""
    CHANNEL_TYPE_CHOICES = [
        ('telegram', 'Telegram Bot'),
        ('whatsapp_business', 'WhatsApp Business API'),
        ('whatsapp', 'WhatsApp (через провайдера)'),
        ('max', 'MAX'),
    ]
    STATUS_CHOICES = [
        ('active', 'Активен'),
        ('error', 'Ошибка'),
        ('disabled', 'Отключён'),
    ]

    name = models.CharField(max_length=200)                    # "Основной бот", "WhatsApp #1"
    channel_type = models.CharField(max_length=20, choices=CHANNEL_TYPE_CHOICES)
    crm_connection = models.ForeignKey(
        'integrations.CRMConnection', on_delete=models.SET_NULL,
        related_name='messenger_channels',
        null=True, blank=True,
    )  # null при crm_mode='builtin' — канал работает без внешней CRM
    # Credentials (зашифрованы, как CRMConnection)
    credentials = EncryptedJSONField()
    # Telegram:           {"bot_token": "123456:ABC..."}
    # WhatsApp Business:  {"phone_number_id": "...", "access_token": "...", "verify_token": "..."}
    # WhatsApp (провайдер): {"provider": "wazzup|greenapi", "api_key": "...", "instance_id": "..."}
    # MAX:                {"bot_token": "...", "api_url": "https://..."}

    # ID канала в CRM (amoCRM scope_id, Bitrix24 connector_line_id)
    crm_channel_id = models.CharField(max_length=200, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    status_detail = models.TextField(blank=True)               # Текст ошибки если status='error'

    # Настройки
    auto_create_lead = models.BooleanField(default=True)       # Создавать лид при первом сообщении
    welcome_message = models.TextField(blank=True)             # Автоответ при первом сообщении

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class ChatSession(models.Model):
    """Сессия чата: связь между внешним чатом и сущностью CRM."""
    channel = models.ForeignKey(MessengerChannel, on_delete=models.CASCADE, related_name='chat_sessions')
    external_chat_id = models.CharField(max_length=200)        # Telegram: chat_id, WhatsApp: phone, MAX: user_id
    external_user_name = models.CharField(max_length=200, blank=True)

    # Привязка к CRM
    crm_contact_id = models.CharField(max_length=100, blank=True)
    crm_chat_id = models.CharField(max_length=200, blank=True)     # ID чата в CRM (amojo chat_id)
    crm_lead_id = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['channel', 'external_chat_id']

class MessageLog(models.Model):
    """Лог сообщений. Для отладки и аудита, НЕ как основной инбокс."""
    DIRECTION_CHOICES = [
        ('in', 'Входящее (клиент → CRM)'),
        ('out', 'Исходящее (CRM → клиент)'),
    ]
    chat_session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    text = models.TextField(blank=True)
    attachments = models.JSONField(default=list)               # [{"type": "photo", "url": "..."}]
    external_message_id = models.CharField(max_length=200, blank=True)
    crm_message_id = models.CharField(max_length=200, blank=True)
    delivered = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
```

**Поддерживаемые мессенджеры:**

| Мессенджер | Способ подключения | Особенности |
|-----------|-------------------|-------------|
| **Telegram** | Bot Token (бесплатно) | Webhook от Telegram, python-telegram-bot |
| **WhatsApp Business** | Meta Cloud API (официальный, платный) | Верификация бизнеса в Meta, шаблонные сообщения |
| **WhatsApp** | Провайдер (Wazzup, Green API) | Проще настройка, без верификации Meta |
| **MAX** | Bot API | Бот-токен, webhook, аналогично Telegram |

### 5.8 `apps/telephony/models.py` (tenant schema)

```python
class SIPTrunk(models.Model):
    """Подключение SIP-транка к оператору связи."""
    TRUNK_TYPE_CHOICES = [
        ('zadarma', 'Zadarma'),
        ('mcn', 'MCN Telecom'),
        ('rostelecom', 'Ростелеком'),
        ('custom_sip', 'Произвольный SIP'),
    ]
    STATUS_CHOICES = [
        ('active', 'Активен'),
        ('registering', 'Регистрация...'),
        ('error', 'Ошибка'),
        ('disabled', 'Отключён'),
    ]

    name = models.CharField(max_length=200)                    # "Основной транк Zadarma"
    trunk_type = models.CharField(max_length=20, choices=TRUNK_TYPE_CHOICES)
    crm_connection = models.ForeignKey(
        'integrations.CRMConnection', on_delete=models.SET_NULL,
        related_name='sip_trunks', null=True, blank=True,
    )  # null: транк работает и без внешней CRM (при builtin)
    # SIP-регистрация (зашифровано)
    credentials = EncryptedJSONField()
    # {
    #   "sip_server": "sip.zadarma.com",
    #   "sip_username": "100001",
    #   "sip_password": "...",
    #   "proxy": "sip.zadarma.com:5060",       # опционально
    #   "transport": "udp",                      # udp / tcp / tls
    #   "callerid": "+74951234567",              # исходящий Caller ID
    # }

    # Номера, принадлежащие этому транку (для маршрутизации входящих)
    inbound_numbers = models.JSONField(default=list)           # ["+74951234567", "+74951234568"]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='registering')
    status_detail = models.TextField(blank=True)               # Текст ошибки регистрации
    last_registration_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class PhoneExtension(models.Model):
    """Внутренний номер (extension) менеджера в телефонии."""
    manager = models.OneToOneField(
        'integrations.ManagerProfile', on_delete=models.CASCADE,
        related_name='phone_extension',
    )
    extension = models.CharField(max_length=10)                # "101", "102"
    sip_password = EncryptedCharField(max_length=100)          # Зашифровано (Fernet)
    webrtc_enabled = models.BooleanField(default=True)         # Может звонить из браузера
    voicemail_enabled = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['extension'], name='unique_extension_per_tenant'),
        ]

class IVRMenu(models.Model):
    """Голосовое меню (IVR). Многоуровневое."""
    name = models.CharField(max_length=200)                    # "Главное меню"
    greeting_audio = models.FileField(upload_to='telephony/ivr/', blank=True)
    greeting_tts = models.TextField(blank=True)                # TTS-текст (если нет аудио)
    options = models.JSONField(default=list)
    # [
    #   {"digit": "1", "action": "queue", "target": "sales"},
    #   {"digit": "2", "action": "extension", "target": "101"},
    #   {"digit": "0", "action": "ivr", "target": 2},           # подменю
    #   {"digit": "timeout", "action": "queue", "target": "default"},
    # ]
    timeout = models.PositiveIntegerField(default=10)          # Секунды ожидания ввода
    is_active = models.BooleanField(default=True)

class CallQueue(models.Model):
    """Очередь звонков. Распределение входящих между менеджерами."""
    STRATEGY_CHOICES = [
        ('ring_all', 'Звонок всем'),
        ('round_robin', 'По очереди'),
        ('least_recent', 'Наименее недавний'),
        ('random', 'Случайный'),
    ]

    name = models.CharField(max_length=200)                    # "sales", "support"
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES, default='ring_all')
    members = models.ManyToManyField('integrations.ManagerProfile', related_name='call_queues', blank=True)
    ring_timeout = models.PositiveIntegerField(default=20)     # Секунды на одного агента
    max_wait_time = models.PositiveIntegerField(default=120)   # Макс. ожидание в очереди
    hold_music = models.FileField(upload_to='telephony/hold/', blank=True)
    announce_position = models.BooleanField(default=True)      # "Вы 2-й в очереди"
    is_active = models.BooleanField(default=True)

class CallRecord(models.Model):
    """Запись о звонке."""
    DIRECTION_CHOICES = [
        ('inbound', 'Входящий'),
        ('outbound', 'Исходящий'),
        ('internal', 'Внутренний'),
    ]
    RESULT_CHOICES = [
        ('answered', 'Отвечен'),
        ('missed', 'Пропущен'),
        ('busy', 'Занято'),
        ('voicemail', 'Голосовая почта'),
        ('ivr_only', 'Только IVR'),
    ]

    sip_trunk = models.ForeignKey(SIPTrunk, on_delete=models.SET_NULL, null=True, related_name='calls')
    freeswitch_uuid = models.CharField(max_length=200, unique=True)  # UUID звонка в FreeSWITCH

    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    caller_number = models.CharField(max_length=50)            # +79161234567
    called_number = models.CharField(max_length=50)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    duration = models.PositiveIntegerField(default=0)          # Секунды разговора
    wait_time = models.PositiveIntegerField(default=0)         # Секунды в очереди

    queue = models.ForeignKey(CallQueue, on_delete=models.SET_NULL, null=True, blank=True)
    manager = models.ForeignKey(
        'integrations.ManagerProfile', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='calls',
    )

    # Привязка к CRM
    crm_call_id = models.CharField(max_length=200, blank=True)
    crm_contact_id = models.CharField(max_length=100, blank=True)
    crm_lead_id = models.CharField(max_length=100, blank=True)

    # Запись разговора
    record_file = models.FileField(upload_to='calls/%Y/%m/', blank=True)
    record_uploaded_to_crm = models.BooleanField(default=False)

    started_at = models.DateTimeField()
    answered_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['-started_at']),
            models.Index(fields=['caller_number']),
            models.Index(fields=['manager', '-started_at']),
        ]
```

**Архитектура телефонии (FreeSWITCH + Django):**
```
[Телефонная сеть] ↔ [SIP-транк провайдера] ↔ [FreeSWITCH в Docker]
                                                       ↕ ESL (Event Socket)
                                                 [Django платформа]
                                                       ↕
                                                 [CRM через адаптер]

[Браузер менеджера] ↔ WebRTC (WSS) ↔ [FreeSWITCH]
```

**Взаимодействие Django ↔ FreeSWITCH:**
- **ESL (Event Socket Library)** — Django подключается к FreeSWITCH через TCP (inbound ESL)
- **При создании/изменении SIPTrunk** → Django генерирует XML-конфиг и отправляет `reloadxml` через ESL
- **Входящий звонок** → FreeSWITCH делает HTTP-запрос на Django (mod_httapi) → Django определяет тенант по номеру, возвращает диалплан (IVR/очередь/extension)
- **WebRTC** — браузер менеджера подключается к FreeSWITCH через WSS (verto или SIP.js)
- **Записи** хранятся в shared volume между FreeSWITCH и Django
- Python-библиотека: `greenswitch` (для ESL)

**Флоу входящего звонка:**
```
Звонок на номер провайдера
    → SIP-провайдер → FreeSWITCH (входящий SIP)
    → FreeSWITCH: mod_httapi → POST /telephony/dialplan/
    → Django: найти SIPTrunk по called_number → определить tenant
    → Django: вернуть диалплан XML:
        → IVR (если настроен) → очередь / extension
        → или сразу в очередь CallQueue
    → FreeSWITCH: звонок менеджеру (через WebRTC или SIP-телефон)
    → FreeSWITCH: ESL event → Django создаёт CallRecord
    → Django: adapter.register_call() → звонок в CRM
    → При завершении: сохранить запись, загрузить в CRM
    → Если пропущен + auto_create_lead:
        → Создать лид через CRM adapter
        → Распределить по правилам (source='phone_call')
```

**Флоу исходящего звонка (click-to-call из ЛК):**
```
Менеджер нажимает "Позвонить" в ЛК
    → POST /api/telephony/call/originate
    → Django: ESL команда originate в FreeSWITCH
    → FreeSWITCH звонит менеджеру (WebRTC), после ответа — клиенту через SIP-транк
    → Остальное аналогично входящему
```

### 5.9 `apps/crm/models.py` (tenant schema) — Встроенный CRM

```python
class Contact(models.Model):
    """Контакт (физлицо). Привязывается к сделкам и компаниям."""
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    messenger_id = models.CharField(max_length=200, blank=True)  # telegram:12345, whatsapp:+7...
    position = models.CharField(max_length=200, blank=True)
    company = models.ForeignKey('Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='contacts')
    custom_fields = models.JSONField(default=dict)               # Произвольные поля (настраиваемые тенантом)
    source = models.CharField(max_length=50, blank=True)         # "website", "phone", "telegram", "manual"
    responsible = models.ForeignKey(
        'integrations.ManagerProfile', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contacts',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return f'{self.first_name} {self.last_name}'.strip()

class Company(models.Model):
    """Компания (юрлицо). Может иметь несколько контактов."""
    name = models.CharField(max_length=300)
    inn = models.CharField(max_length=12, blank=True, db_index=True)  # ИНН
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    website = models.URLField(blank=True)
    custom_fields = models.JSONField(default=dict)
    responsible = models.ForeignKey(
        'integrations.ManagerProfile', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='companies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'companies'

class Pipeline(models.Model):
    """Воронка продаж. У тенанта может быть несколько воронок."""
    name = models.CharField(max_length=200)                    # "Основная", "Партнёрская"
    is_default = models.BooleanField(default=False)            # Воронка по умолчанию для новых сделок
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order']

class Stage(models.Model):
    """Стадия воронки. Порядок определяет положение на Kanban-доске."""
    STAGE_TYPE_CHOICES = [
        ('open', 'В работе'),
        ('won', 'Успешно завершена'),
        ('lost', 'Проиграна'),
    ]
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name='stages')
    name = models.CharField(max_length=200)                    # "Новая", "Квалификация", "Договор", "Оплата"
    stage_type = models.CharField(max_length=10, choices=STAGE_TYPE_CHOICES, default='open')
    color = models.CharField(max_length=7, default='#3B82F6')  # HEX для Kanban-карточки
    sort_order = models.PositiveIntegerField(default=0)
    # Автодействие при переходе в эту стадию (опционально)
    auto_action = models.JSONField(default=dict, blank=True)
    # Примеры auto_action:
    # {"type": "create_contract", "template_id": 5}           — создать договор из шаблона
    # {"type": "send_notification", "event": "deal_stage_changed"}
    # {"type": "create_task", "title": "Позвонить клиенту", "days_offset": 1}
    # {} — нет автодействия

    class Meta:
        ordering = ['sort_order']
        # НЕ используем unique_together на sort_order — это делает reorder операцию
        # невозможной без временных значений. Уникальность порядка обеспечивается
        # на уровне приложения (endpoint POST /crm/pipelines/{id}/stages/reorder/).

class Deal(models.Model):
    """Сделка — основная бизнес-сущность CRM."""
    name = models.CharField(max_length=300)                    # "Продажа CRM для ООО Ромашка"
    pipeline = models.ForeignKey(Pipeline, on_delete=models.PROTECT, related_name='deals')
    stage = models.ForeignKey(Stage, on_delete=models.PROTECT, related_name='deals')
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='deals')
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='deals')
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='RUB')
    responsible = models.ForeignKey(
        'integrations.ManagerProfile', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deals',
    )
    expected_close_date = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    loss_reason = models.CharField(max_length=300, blank=True)
    custom_fields = models.JSONField(default=dict)
    source = models.CharField(max_length=50, blank=True)       # "phone", "telegram", "website", "distribution"
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['stage', '-updated_at']),
            models.Index(fields=['responsible', '-updated_at']),
            models.Index(fields=['contact']),
        ]

class Activity(models.Model):
    """Активность — любое событие в таймлайне сделки/контакта."""
    ACTIVITY_TYPE_CHOICES = [
        ('call', 'Звонок'),
        ('message', 'Сообщение'),
        ('task', 'Задача'),
        ('note', 'Заметка'),
        ('email', 'Email'),
        ('contract', 'Договор'),
        ('stage_change', 'Смена стадии'),
        ('system', 'Системное'),
    ]
    STATUS_CHOICES = [
        ('planned', 'Запланировано'),
        ('done', 'Выполнено'),
        ('overdue', 'Просрочено'),
    ]

    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPE_CHOICES)
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, null=True, blank=True, related_name='activities')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, null=True, blank=True, related_name='activities')
    responsible = models.ForeignKey(
        'integrations.ManagerProfile', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activities',
    )
    title = models.CharField(max_length=300)                   # "Входящий звонок +7916...", "Задача: перезвонить"
    body = models.TextField(blank=True)                        # Содержание заметки / текст сообщения
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='done')
    due_date = models.DateTimeField(null=True, blank=True)     # Дедлайн для задач

    # Связь с другими объектами (опционально)
    related_call = models.ForeignKey(
        'telephony.CallRecord', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activities',
    )
    related_contract = models.ForeignKey(
        'contracts.Contract', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activities',
    )
    related_message = models.ForeignKey(
        'channels.MessageLog', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activities',
    )

    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['deal', '-created_at']),
            models.Index(fields=['contact', '-created_at']),
            models.Index(fields=['responsible', 'status', '-due_date']),
        ]
        verbose_name_plural = 'activities'
```

**Архитектура: CRM-режимы тенанта (`Tenant.crm_mode`):**

```
crm_mode = 'builtin':
  → Все данные хранятся в apps/crm (Contact, Deal, Pipeline, Activity)
  → BuiltinCRMAdapter реализует CRMAdapterProtocol
  → Телефония, мессенджеры, договоры, распределение — работают через тот же адаптер
  → Карточка сделки с единым таймлайном (звонки + чаты + договоры)

crm_mode = 'bitrix24' | 'amocrm':
  → Данные в внешней CRM (Битрикс24 / amoCRM)
  → Bitrix24Adapter / AmoCRMAdapter реализуют CRMAdapterProtocol
  → apps/crm не используется (модели пустые)
  → UI: только интеграции, без Kanban и карточек сделок
```

**Автодействия при смене стадии (Stage.auto_action):**
```python
# apps/crm/services/auto_actions.py
def process_stage_change(deal: Deal, old_stage: Stage, new_stage: Stage):
    """Вызывается при перемещении сделки между стадиями."""
    action = new_stage.auto_action
    if not action:
        return
    if action['type'] == 'create_contract':
        # Создать договор из шаблона, привязать к сделке
        template = ContractTemplate.objects.get(id=action['template_id'])
        create_contract_from_deal(deal, template)
    elif action['type'] == 'send_notification':
        # Тенант = текущая схема django-tenants (connection.tenant), НЕ deal.pipeline.tenant
        from django.db import connection as db_connection
        notify(db_connection.tenant, action['event'], {'deal': deal})
    elif action['type'] == 'create_task':
        Activity.objects.create(
            activity_type='task', deal=deal,
            responsible=deal.responsible,
            title=action['title'],
            status='planned',
            due_date=now() + timedelta(days=action.get('days_offset', 1)),
        )
```

### 5.10 `apps/audit/models.py` (tenant schema)

```python
class AuditEvent(models.Model):
    """Лог действий пользователей. Неизменяемая таблица (append-only)."""
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('invite', 'Invite'),
        ('sign', 'Sign'),
        ('distribute', 'Distribute'),
        ('sync', 'Sync'),
        ('export', 'Export'),
    ]

    user = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True,
        related_name='+',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)              # 'Contract', 'DistributionRule', ...
    object_id = models.CharField(max_length=100, blank=True)   # PK изменённого объекта
    object_repr = models.CharField(max_length=300, blank=True) # Строковое представление
    changes = models.JSONField(default=dict)                   # {"field": {"old": ..., "new": ...}}
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['user', '-created_at']),
        ]
```

**Запись в аудит-лог — вспомогательная функция:**
```python
# apps/audit/services.py
def log_event(request, action: str, instance=None, changes: dict = None, **kwargs):
    """Универсальная функция записи в аудит. Вызывается из view/service."""
    AuditEvent.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        model_name=instance.__class__.__name__ if instance else kwargs.get('model_name', ''),
        object_id=str(instance.pk) if instance else kwargs.get('object_id', ''),
        object_repr=str(instance)[:300] if instance else kwargs.get('object_repr', ''),
        changes=changes or {},
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )
```

### 5.11 `apps/notifications/models.py` (tenant schema)

```python
class NotificationChannel(models.TextChoices):
    EMAIL = 'email', 'Email'
    IN_APP = 'in_app', 'In-App'
    TELEGRAM = 'telegram', 'Telegram'

class NotificationEvent(models.TextChoices):
    CONTRACT_SIGNED = 'contract_signed', 'Договор подписан'
    LEAD_DISTRIBUTED = 'lead_distributed', 'Заявка распределена'
    CRM_CONNECTION_LOST = 'crm_connection_lost', 'CRM-соединение потеряно'
    CRM_CONNECTION_RESTORED = 'crm_connection_restored', 'CRM-соединение восстановлено'
    PLAN_LIMIT_WARNING = 'plan_limit_warning', 'Лимит плана на исходе (80%)'
    PLAN_LIMIT_REACHED = 'plan_limit_reached', 'Лимит плана достигнут'
    USER_INVITED = 'user_invited', 'Пользователь приглашён'
    MANAGER_SYNC_DONE = 'manager_sync_done', 'Синхронизация менеджеров завершена'
    SIGNING_EXPIRED = 'signing_expired', 'Срок подписания истёк'
    DEAL_STAGE_CHANGED = 'deal_stage_changed', 'Сделка перемещена'
    TASK_OVERDUE = 'task_overdue', 'Задача просрочена'
    NEW_DEAL_CREATED = 'new_deal_created', 'Новая сделка создана'

class NotificationPreference(models.Model):
    """Настройки уведомлений на уровне тенанта. Какие события → какие каналы."""
    event = models.CharField(max_length=50, choices=NotificationEvent.choices)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    is_enabled = models.BooleanField(default=True)
    # Получатели: роли, которым отправлять (пустой = owner+admin)
    recipient_roles = models.JSONField(
        default=list,
        help_text='["owner", "admin", "manager"]  — пустой список = owner+admin',
    )

    class Meta:
        unique_together = ['event', 'channel']

class Notification(models.Model):
    """Конкретное уведомление для пользователя.
    Важно: FK на User из tenant schema → public schema.
    django-tenants поддерживает это если User в SHARED_APPS.
    """
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='notifications')
    event = models.CharField(max_length=50, choices=NotificationEvent.choices)
    title = models.CharField(max_length=300)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)        # Ссылка на объект в ЛК
    is_read = models.BooleanField(default=False)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']

class TelegramBinding(models.Model):
    """Привязка Telegram-аккаунта к пользователю для уведомлений."""
    user = models.OneToOneField('users.User', on_delete=models.CASCADE, related_name='telegram')
    chat_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    linked_at = models.DateTimeField(auto_now_add=True)
```

**Отправка уведомлений — сервисный слой:**
```python
# apps/notifications/services.py
def notify(tenant, event: str, context: dict, instance=None):
    """Универсальная отправка. Проверяет настройки тенанта, рассылает по каналам."""
    prefs = NotificationPreference.objects.filter(event=event, is_enabled=True)
    for pref in prefs:
        roles = pref.recipient_roles or ['owner', 'admin']
        # get_users_by_roles: запрашивает Membership (shared schema) через
        # schema_context('public') → фильтрует по tenant + role → возвращает User queryset
        users = get_users_by_roles(tenant, roles)
        for user in users:
            if pref.channel == 'email':
                send_notification_email.delay(tenant.id, user.id, event, context)
            elif pref.channel == 'in_app':
                Notification.objects.create(
                    user=user, event=event,
                    title=render_title(event, context),
                    body=render_body(event, context),
                    link=context.get('link', ''),
                    channel='in_app',
                )
            elif pref.channel == 'telegram':
                send_telegram_notification.delay(tenant.id, user.id, event, context)
```

---

## 6. Стратегии распределения (plugin-registry)

```python
# apps/distribution/strategies.py

from typing import Protocol

class DistributionStrategy(Protocol):
    def choose_manager(
        self,
        candidates: list[ManagerProfile],
        context: dict,    # {"crm_entity": LeadData, "rule": DistributionRule}
        config: dict,     # strategy_config из DistributionRule
    ) -> tuple[ManagerProfile | None, str]:
        """Возвращает (менеджер, причина) или (None, причина)."""
        ...

class MinLoadStrategy:
    """Назначить менеджеру с наименьшей нагрузкой за период."""
    def choose_manager(self, candidates, context, config):
        period_days = config.get('period_days', 7)
        # Считаем назначения за period_days для каждого кандидата
        # Фильтруем по schedule и days_off
        # Нормализуем по рабочим дням
        # Возвращаем с минимальной нагрузкой
        ...

class RoundRobinStrategy:
    """Строго по очереди, циклически."""
    def choose_manager(self, candidates, context, config):
        last_index = config.get('last_assigned_index', -1)
        next_index = (last_index + 1) % len(available_candidates)
        # Обновить last_assigned_index в strategy_config
        ...

class WeightedStrategy:
    """Распределение пропорционально весам."""
    def choose_manager(self, candidates, context, config):
        weights = config.get('manager_weights', {})
        # Считаем фактическое распределение за период
        # Назначаем тому, кто больше всего "недополучил" от своей доли
        ...

class ManualQueueStrategy:
    """Заявки попадают в очередь, менеджеры берут сами."""
    def choose_manager(self, candidates, context, config):
        return None, "manual_queue: awaiting manual pickup"

# Registry
STRATEGIES: dict[str, type[DistributionStrategy]] = {
    'min_load': MinLoadStrategy,
    'round_robin': RoundRobinStrategy,
    'weighted': WeightedStrategy,
    'manual_queue': ManualQueueStrategy,
}
```

---

## 7. Флоу подписания договора

```
1. Менеджер в UI выбирает шаблон + сделку из CRM
2. Система через CRM-адаптер получает данные сущности
3. FieldMapping маппит CRM-поля → переменные шаблона
4. Менеджер видит превью, может подправить данные вручную
5. POST /api/contracts/generate → Contract (status=draft, PDF сгенерирован)
6. Менеджер нажимает "Отправить на подписание"
7. POST /api/contracts/{id}/send-for-signing
   → Создаётся SigningSession (token=UUID, OTP генерируется, хэшируется)
   → OTP отправляется клиенту (SMS или email, в зависимости от signing_method)
   → Contract.status = 'sent'
8. Клиент переходит по ссылке: /sign/{token}/
   → Публичная страница (без авторизации!)
   → Видит PDF, кнопку "Подписать"
   → Contract.status = 'viewed'
9. Клиент нажимает "Подписать" → вводит OTP-код
   → POST /sign/{token}/verify/ (rate-limited, макс. 5 попыток)
   → Проверка хэша, срока действия
   → Если OK: Contract.status = 'signed', фиксируем IP, UA, время
   → PDF штампуется отметкой о подписании (текст внизу или watermark)
   → Webhook в CRM: договор подписан, ссылка на подписанный PDF
10. Если OTP истёк → менеджер может отправить повторно (новая SigningSession)
```

**Публичная страница подписания** — отдельный URL-паттерн, доступный без auth, без привязки к тенанту (token глобально уникален). Минимальный дизайн: логотип организации, PDF-превью, поле OTP.

**Примечание по кросс-схемному поиску токена:** `SigningSession` находится в tenant schema, но публичная страница `/sign/{token}/` вызывается без контекста тенанта. Решение: добавить shared-модель `SigningTokenLookup(token=UUID, tenant=FK(Tenant))` в одно из shared-приложений (например, `apps.tenants`) или создать отдельную shared-таблицу. При создании `SigningSession` — записывать (token, tenant_id) в shared-таблицу; при обращении к `/sign/{token}/` — найти tenant через shared lookup, переключиться на его schema через `tenant_context(tenant)`.

---

## 8. Личный кабинет организации (Vue 3 SPA — `frontend/`)

Single Page Application на Vue 3. Взаимодействует с Django только через API (`/api/...`).
Статика раздаётся nginx (продакшн) или Vite dev server (разработка).

**UI-основа:** тема Aura (встроенный preset PrimeVue 4) + layout Sakai (бесплатный open-source шаблон от PrimeTek). Sakai даёт из коробки: sidebar с навигацией, header с профилем и уведомлениями, breadcrumbs, dark/light mode, responsive. Остаётся наполнить страницами и кастомизировать цвета через `definePreset()`.

### Стек фронтенда

| Компонент | Библиотека | Назначение |
|-----------|------------|------------|
| Фреймворк | Vue 3.5 (Composition API) | Реактивный UI |
| Сборщик | Vite 6.x | Hot reload, быстрый билд |
| UI-кит | PrimeVue 4 | DataTable, TreeSelect, Stepper, Chart, Dialog, Toast |
| Тема | Aura (preset) | Встроенная тема PrimeVue 4, light/dark mode, кастомизация через `definePreset()` |
| Layout | Sakai (PrimeTek) | Готовый open-source layout: sidebar, header, breadcrumbs, dark mode, responsive. Клонируется из `github.com/primefaces/sakai-vue` и адаптируется |
| CSS | Tailwind CSS 4 | Utility-first, собирается Vite |
| Стор | Pinia 3 | auth, tenant, calls, notifications, crm |
| Роутер | Vue Router 4 | Клиентский routing, guards по ролям/features |
| HTTP | ofetch / axios | Запросы к Django API, авто-refresh JWT |
| WebRTC | SIP.js 0.21 | Звонки из браузера (FreeSWITCH WSS) |
| Real-time | WebSocket (Django Channels) | Уведомления, статус звонков, Kanban live-sync |
| Иконки | PrimeIcons + Font Awesome  | |

### Ключевые composables (Vue)

```typescript
// composables/useAuth.ts      — JWT auth, refresh, logout, current user
// composables/useTenant.ts    — текущий тенант, план, лимиты
// composables/useFeatureGate.ts — hasFeature('contracts'), checkLimit('max_managers')
// composables/useSIPPhone.ts  — SIP.js: register, call, hangup, hold, transfer, status
// composables/useNotifications.ts — WebSocket: подписка, счётчик, mark as read
// composables/useCRM.ts       — CRUD сделок/контактов, Kanban state, фильтры
// composables/useAudit.ts     — логирование действий на фронте
```

### Ключевые компоненты

```
components/
  SoftPhone.vue              # WebRTC-софтфон: номеронабиратель, статус, hold, mute
  IvrBuilder.vue             # Визуальный конструктор IVR (PrimeVue TreeSelect + drag)
  KanbanBoard.vue            # Kanban-доска сделок (drag-and-drop между стадиями)
  DealCard.vue               # Карточка сделки на Kanban (summary: сумма, контакт, дедлайн)
  DealTimeline.vue           # Таймлайн активностей сделки (звонки, чаты, договоры, заметки)
  ContactCard.vue            # Карточка контакта (инфо + сделки + таймлайн)
  PipelineSettings.vue       # Настройка воронки: стадии, цвета, auto_action
  TaskList.vue               # Список задач менеджера (план/просроч/выполнено)
  OnboardingWizard.vue       # Пошаговый мастер (PrimeVue Stepper)
  FeatureGate.vue            # Slot-компонент: оборачивает секции, показывает upsell-модалку
  NotificationBell.vue       # Колокольчик в header, badge со счётчиком, dropdown
  AudioPlayer.vue            # Плеер записи звонка (стриминг с API)
  AuditDiff.vue              # Отображение old/new значений (diff)
```

### Навигация ЛК (sidebar)

| Раздел | Роли | Feature-gate | Описание |
|--------|------|-------------|----------|
| **Главная** | все | — | Сводка: активные менеджеры, договоры за месяц, распределённые заявки |
| **Встроенный CRM** | owner, admin, manager | `crm_builtin` | Воронки, Kanban, сделки, контакты, компании, задачи, таймлайн |
| **Интеграции** | owner, admin | — | Подключение/отключение CRM, OAuth-флоу, статус синхронизации |
| **Мессенджеры** | owner, admin | `messenger_channels` | Подключение Telegram / WhatsApp / MAX, привязка к CRM, лог сообщений |
| **Телефония** | owner, admin | `telephony` | SIP-транки, номера, extensions, IVR, очереди, журнал, записи, WebRTC-звонки |
| **Менеджеры** | owner, admin | — | Список, расписание, выходные, синхронизация из CRM |
| **Распределение** | owner, admin | `distribution` | Правила, стратегии, лог распределений |
| **Шаблоны договоров** | owner, admin | `contracts` | CRUD шаблонов, маппинг полей на CRM |
| **Договоры** | owner, admin, manager | `contracts` | Список, генерация, отправка на подписание, статусы |
| **Аналитика** | owner, admin, manager | `analytics` | Графики, отчёты, экспорт |
| **Команда** | owner, admin | — | Пользователи организации, приглашения, роли |
| **Уведомления** | owner, admin | — | Настройка каналов per-событие, привязка Telegram |
| **Аудит** | owner, admin | — | Лог действий: фильтр по пользователю, действию, дате |
| **Настройки** | owner | — | Логотип, цвет, таймзона, язык |
| **Подписка** | owner | — | Текущий план, лимиты, использование |

### Ключевые страницы

**Главная (дашборд):**
- Карточки: менеджеров онлайн, договоров за месяц, заявок распределено сегодня, открытых сделок (если crm_builtin)
- Доступные функции подсвечены, недоступные — серые с пометкой «Доступно в плане ...»
- Быстрые действия: создать сделку, создать договор, синхронизировать менеджеров

**Интеграции:**
- Карточки подключённых CRM с индикатором статуса (зелёный/красный)
- Кнопка «Подключить amoCRM» → OAuth-флоу (redirect → callback → сохранение токенов)
- Кнопка «Подключить Битрикс24» → инструкция + webhook URL или OAuth
- Проверка `check_limit(tenant, 'max_crm_connections', current_count)` при добавлении

**Подписка:**
- Текущий план, дата окончания
- Использование лимитов: `3/5 менеджеров`, `12/50 договоров в месяц`
- Прогресс-бары для визуализации
- Список доступных планов с кнопкой «Сменить план» (пока без оплаты, запрос админу)

**Уведомления:**
- Таблица: событие × канал (email / in-app / Telegram), чекбоксы вкл/выкл
- Блок «Telegram-бот»: QR-код / ссылка для привязки, список привязанных пользователей
- Тест-кнопка: «Отправить тестовое уведомление»

**Аудит:**
- Таблица с фильтрами: дата, пользователь, действие, объект
- Клик по строке → детали: old/new значения (diff)
- Экспорт в CSV

### Онбординг-визард

Показывается при первом входе owner после регистрации. Компонент `OnboardingWizard.vue` (PrimeVue Stepper):

| Шаг | Содержание | Обязательный |
|-----|-----------|-------------|
| 1. Организация | Название, логотип, таймзона | Да |
| 2. CRM-режим | Выбор: «Встроенный CRM» / «Подключить amoCRM» / «Подключить Битрикс24». OAuth-флоу для внешних. Создание первой воронки для встроенного. | Да |
| 3. Менеджеры | Синхронизировать из CRM или добавить вручную | Нет |
| 4. Первое правило | Создать правило распределения (если `distribution` в плане) | Нет |
| 5. Готово | Сводка, ссылки на основные разделы ЛК | — |

- Прогресс сохраняется: `Tenant.onboarding_step = PositiveIntegerField(default=0)` (0 = не начат, 5 = завершён)
- Если owner закрыл визард — показывать баннер «Завершите настройку» на главной пока `onboarding_step < 5`
- Каждый шаг — отдельный POST в API, сохраняет данные + обновляет `onboarding_step`

### Feature-gating в UI (Vue)

Недоступные по плану разделы:
- Пункт меню отображается, но серый + иконка замка
- При клике — модалка (PrimeVue Dialog): «Функция доступна в плане {plan_name}. Обратитесь к администратору.»
- Composable `useFeatureGate()` + компонент-обёртка `<FeatureGate feature="contracts">`:

```vue
<template>
  <FeatureGate feature="contracts">
    <ContractsPage />
    <template #locked>
      <UpgradePrompt feature="contracts" />
    </template>
  </FeatureGate>
</template>
```

```typescript
// composables/useFeatureGate.ts
export function useFeatureGate() {
  const tenant = useTenantStore()
  const hasFeature = (code: string) => tenant.plan.features.includes(code)
  const checkLimit = (field: string, current: number) => {
    const limit = tenant.plan[field]
    return limit === null || current < limit
  }
  return { hasFeature, checkLimit }
}
```

Router guard для feature-gated роутов:
```typescript
// router/guards.ts
{ path: '/contracts', meta: { feature: 'contracts', roles: ['owner', 'admin', 'manager'] } }
// beforeEach: проверка hasFeature + role, redirect на /upgrade если недоступно
```

### Auth (JWT)

```
POST /api/auth/login  →  { access_token }  +  Set-Cookie: refresh_token (httpOnly, Secure, SameSite=Lax)
- access_token: хранится в памяти (Pinia), НЕ в localStorage, НЕ в cookie
- refresh_token: ТОЛЬКО httpOnly cookie (НЕ в теле ответа — иначе доступен JS, что убивает защиту)
- Авто-refresh через interceptor в HTTP-клиенте
- При загрузке приложения: POST /api/auth/refresh → новый access_token (refresh_token из cookie)
```

---

## 8b. Админ-панель платформы (Django Admin)

Платформенный админ (`is_superuser=True`) управляет через стандартный Django Admin:

| Модель | Действия |
|--------|----------|
| **Plan** | CRUD тарифных планов, назначение Feature, лимиты |
| **Feature** | CRUD функций (code + name + description) |
| **Tenant** | Просмотр организаций, смена плана, активация/деактивация |
| **User** | Просмотр пользователей, сброс пароля |
| **Membership** | Просмотр привязок пользователь↔организация |

Никакого отдельного UI для платформенного админа — Django Admin достаточно.

---

## 9. API-структура (django-ninja)

```
# Все эндпоинты ниже имеют префикс /api/, КРОМЕ:
#   /sign/{token}/       — публичная страница подписания (Django template, без JWT)
#   /wh/...              — входящие вебхуки от CRM (проверка secret_token)
#   /healthz             — health check
#   /telephony/dialplan/ — FreeSWITCH internal (shared secret)
#   /telephony/events/   — FreeSWITCH internal (shared secret)
#   /channels/webhook/{type}/{id}/ — входящий webhook от мессенджера (публичный, без JWT)
#   /ws/...               — WebSocket-эндпоинты (Django Channels, JWT через query param или first message)
# Эти эндпоинты регистрируются в urls.py / routing.py на корневом уровне, не через django-ninja /api/ router.

/api/
  # --- Auth (JWT) ---
  POST   /auth/login                           # Email + пароль → { access_token } + Set-Cookie: refresh_token
  POST   /auth/refresh                         # Refresh token (cookie) → новый access_token
  POST   /auth/logout                          # Инвалидировать refresh token
  POST   /auth/register                        # Регистрация организации + owner
  POST   /auth/invite/accept                   # Принять приглашение по токену
  GET    /auth/me                              # Текущий пользователь + role + tenant

  # --- Tenant ---
  GET    /tenant/                              # Текущая организация
  PATCH  /tenant/settings                      # Настройки (лого, цвет, TZ, язык)
  GET    /tenant/plan/                         # Текущий план + использование лимитов
  GET    /tenant/plans/                        # Доступные планы для смены

  # --- Users & Memberships ---
  GET    /users/                               # Список пользователей организации
  POST   /users/invite                         # Пригласить (email + role)
  PATCH  /users/{id}/role                      # Сменить роль
  DELETE /users/{id}                           # Деактивировать

  # --- CRM Connections --- (feature-gated: crm_bitrix24 / crm_amocrm)
  GET    /integrations/connections/             # Список подключений
  POST   /integrations/connections/             # Добавить CRM (+ проверка лимита)
  PATCH  /integrations/connections/{id}/        # Обновить credentials
  DELETE /integrations/connections/{id}/        # Удалить
  POST   /integrations/connections/{id}/sync-users/  # Синхронизировать менеджеров
  GET    /integrations/connections/{id}/managers/     # Список менеджеров из CRM

  # --- Webhooks (входящие от CRM) ---
  POST   /wh/{tenant_slug}/{webhook_uuid}/     # Универсальный вебхук-эндпоинт

  # --- Contract Templates --- (feature-gated: contracts)
  GET    /contracts/templates/                 # Список шаблонов
  POST   /contracts/templates/                 # Создать (+ custom_contract_templates)
  PATCH  /contracts/templates/{id}/            # Обновить
  GET    /contracts/templates/{id}/preview/    # Превью с тестовыми данными

  # --- Field Mappings ---
  GET    /contracts/templates/{id}/mappings/                    # Маппинг переменных → CRM
  PUT    /contracts/templates/{id}/mappings/{connection_id}/    # Сохранить маппинг

  # --- Contracts --- (feature-gated: contracts + contract_signing)
  GET    /contracts/                           # Список договоров
  POST   /contracts/generate                   # Сгенерировать (+ проверка лимита)
  GET    /contracts/{id}/                      # Детали
  GET    /contracts/{id}/pdf/                  # Скачать PDF
  POST   /contracts/{id}/send-for-signing/     # Отправить (feature: contract_signing)

  # --- Signing (публичное, без auth) ---
  GET    /sign/{token}/                        # Страница подписания (HTML)
  POST   /sign/{token}/verify/                 # Проверить OTP

  # --- Distribution Rules --- (feature-gated: distribution)
  GET    /distribution/rules/                  # Список правил
  POST   /distribution/rules/                  # Создать
  PATCH  /distribution/rules/{id}/             # Обновить
  DELETE /distribution/rules/{id}/             # Удалить
  GET    /distribution/log/                    # Лог распределений

  # --- Dashboard --- (feature-gated: analytics)
  GET    /dashboard/stats/                     # Агрегированная статистика
  GET    /dashboard/managers/                  # Нагрузка менеджеров

  # --- Встроенный CRM --- (feature-gated: crm_builtin, только при crm_mode='builtin')
  # Контакты
  GET    /crm/contacts/                        # Список (поиск, фильтры: ответственный, компания)
  POST   /crm/contacts/                        # Создать
  GET    /crm/contacts/{id}/                   # Детали + таймлайн активностей
  PATCH  /crm/contacts/{id}/                   # Обновить
  DELETE /crm/contacts/{id}/                   # Удалить
  # Компании
  GET    /crm/companies/                       # Список (поиск по названию, ИНН)
  POST   /crm/companies/                       # Создать
  GET    /crm/companies/{id}/                  # Детали + контакты + сделки
  PATCH  /crm/companies/{id}/                  # Обновить
  DELETE /crm/companies/{id}/                  # Удалить
  # Воронки
  GET    /crm/pipelines/                       # Список воронок
  POST   /crm/pipelines/                       # Создать воронку (+проверка лимита max_pipelines)
  PATCH  /crm/pipelines/{id}/                  # Обновить
  DELETE /crm/pipelines/{id}/                  # Удалить (если нет сделок)
  # Стадии
  GET    /crm/pipelines/{id}/stages/           # Стадии воронки (с порядком)
  POST   /crm/pipelines/{id}/stages/           # Создать стадию
  PATCH  /crm/stages/{id}/                     # Обновить (имя, цвет, auto_action, порядок)
  DELETE /crm/stages/{id}/                     # Удалить (если нет сделок)
  POST   /crm/pipelines/{id}/stages/reorder/   # Перестановка стадий (массовое обновление sort_order)
  # Сделки
  GET    /crm/deals/                           # Список (фильтры: pipeline, stage, responsible, дата)
  GET    /crm/deals/kanban/{pipeline_id}/      # Kanban-формат: сделки сгруппированы по стадиям
  POST   /crm/deals/                           # Создать сделку
  GET    /crm/deals/{id}/                      # Детали + таймлайн активностей
  PATCH  /crm/deals/{id}/                      # Обновить
  PATCH  /crm/deals/{id}/move/                 # Перемещение по стадиям (триггерит auto_action)
  DELETE /crm/deals/{id}/                      # Удалить
  # Активности
  GET    /crm/deals/{id}/activities/           # Таймлайн сделки
  GET    /crm/contacts/{id}/activities/        # Таймлайн контакта
  POST   /crm/activities/                      # Создать (заметка, задача)
  PATCH  /crm/activities/{id}/                 # Обновить (статус задачи: planned→done)
  DELETE /crm/activities/{id}/                 # Удалить
  GET    /crm/activities/tasks/                # Мои задачи (фильтр: planned/overdue, с дедлайнами)
  # Статистика CRM
  GET    /crm/stats/pipeline/{id}/             # Конверсия по стадиям воронки
  GET    /crm/stats/managers/                  # Сделки по менеджерам (сумма, кол-во, win rate)

  # --- Messenger Channels --- (feature-gated: messenger_channels)
  GET    /channels/                            # Список мессенджер-каналов
  POST   /channels/                            # Подключить канал (Telegram / WhatsApp / MAX)
  PATCH  /channels/{id}/                       # Обновить настройки
  DELETE /channels/{id}/                       # Отключить канал
  GET    /channels/{id}/stats/                 # Статистика: сообщений за период, активных чатов
  GET    /channels/{id}/chats/                 # Список чат-сессий
  GET    /channels/{id}/chats/{chat_id}/messages/  # Лог сообщений (для отладки)
  POST   /channels/webhook/{type}/{id}/        # Входящий webhook от мессенджера (публичный)

  # --- Telephony --- (feature-gated: telephony)
  # SIP-транки
  GET    /telephony/trunks/                    # Список SIP-транков
  POST   /telephony/trunks/                    # Подключить транк
  PATCH  /telephony/trunks/{id}/               # Обновить
  DELETE /telephony/trunks/{id}/               # Удалить
  POST   /telephony/trunks/{id}/test/          # Проверить регистрацию
  # Extensions
  GET    /telephony/extensions/                # Список внутренних номеров
  POST   /telephony/extensions/                # Создать extension
  PATCH  /telephony/extensions/{id}/           # Обновить
  DELETE /telephony/extensions/{id}/           # Удалить
  # IVR
  GET    /telephony/ivr/                       # Список IVR-меню
  POST   /telephony/ivr/                       # Создать
  PATCH  /telephony/ivr/{id}/                  # Обновить
  DELETE /telephony/ivr/{id}/                  # Удалить
  # Очереди
  GET    /telephony/queues/                    # Список очередей
  POST   /telephony/queues/                    # Создать
  PATCH  /telephony/queues/{id}/               # Обновить
  DELETE /telephony/queues/{id}/               # Удалить
  # Звонки
  GET    /telephony/calls/                     # Журнал звонков (фильтры: дата, менеджер, результат)
  GET    /telephony/calls/{id}/                # Детали звонка + плеер записи
  GET    /telephony/calls/{id}/record/         # Скачать/стримить запись
  GET    /telephony/stats/                     # Статистика: звонков, пропущенных, среднюю длительность
  # Звонки из браузера
  POST   /telephony/call/originate             # Click-to-call: инициировать звонок
  GET    /telephony/webrtc/credentials         # WSS endpoint + SIP credentials для WebRTC-клиента
  # --- Audit ---
  GET    /audit/events/                        # Лог событий (фильтры: user, action, date)
  GET    /audit/events/{id}/                   # Детали события (diff)
  GET    /audit/events/export/                 # Экспорт в CSV

  # --- Notifications ---
  GET    /notifications/                       # Список in-app уведомлений текущего юзера
  POST   /notifications/{id}/read/             # Пометить прочитанным
  POST   /notifications/read-all/              # Пометить все прочитанными
  GET    /notifications/preferences/           # Настройки уведомлений тенанта
  PUT    /notifications/preferences/           # Обновить настройки
  POST   /notifications/test/                  # Отправить тестовое уведомление
  POST   /notifications/telegram/link/         # Получить ссылку для привязки Telegram
  DELETE /notifications/telegram/unlink/       # Отвязать Telegram

  # --- Onboarding ---
  GET    /onboarding/status/                   # Текущий шаг
  POST   /onboarding/step/{step}/              # Сохранить данные шага
  POST   /onboarding/skip/                     # Пропустить (onboarding_step = 5)

# --- Корневые эндпоинты (не через /api/) ---
GET    /healthz                                # Проверка сервиса

# --- Корневые эндпоинты (FreeSWITCH → Django, не через /api/, shared secret + IP whitelist) ---
POST   /telephony/dialplan/                    # mod_httapi: динамический диалплан
POST   /telephony/events/                      # ESL events: CDR, hangup, DTMF
```

---

## 10. Безопасность

### Хранение CRM-credentials
`CRMConnection.credentials` — JSON с токенами. **Обязательно шифровать:**
```python
# Используется django-fernet-encrypted-fields: EncryptedCharField, EncryptedTextField
# Ключ шифрования — в env: FIELD_ENCRYPTION_KEY
# Примечание: django-fernet-encrypted-fields НЕ имеет EncryptedJSONField из коробки.
# Необходимо создать кастомное поле EncryptedJSONField на базе EncryptedTextField + json.dumps/loads.
# Файл: apps/core/fields.py (или utils/fields.py)
```

### OTP
- Хранить **только хэш** (SHA-256 или bcrypt)
- Срок жизни: 10 минут
- Макс. 5 попыток ввода, потом блокировка сессии
- Rate-limit: 3 OTP-отправки на один контракт в час

### Вебхуки
- Верификация `secret_token` при каждом входящем запросе
- Для Bitrix24: проверка `auth[application_token]`
- Для amoCRM: проверка по IP whitelist или HMAC (если доступно)

### JWT-аутентификация (для SPA)
```python
# settings.py (ninja_jwt, corsheaders уже в SHARED_APPS — см. секцию 4)
MIDDLEWARE = ['corsheaders.middleware.CorsMiddleware', ...existing...]

NINJA_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

# CORS — только для dev (Vite dev server)
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=['http://localhost:5173'])
CORS_ALLOW_CREDENTIALS = True  # для httpOnly refresh cookie
```

- `access_token` — short-lived (15 мин), хранится в памяти (Pinia store), **не в localStorage**
- `refresh_token` — httpOnly secure cookie, rotate on use
- Все API-эндпоинты (кроме `/auth/login`, `/auth/register`, `/auth/invite/accept`, `/auth/refresh`, `/sign/`, `/wh/`, `/channels/webhook/`, `/healthz`, `/telephony/dialplan/`, `/telephony/events/`) требуют Bearer токен
- WebSocket-эндпоинты (`/ws/...`) — JWT передаётся через query param `?token=...` при подключении (стандартная практика, т.к. WebSocket API не поддерживает кастомные заголовки)
- Vue interceptor: при 401 → POST `/api/auth/refresh` → повторить запрос

### Телефония (FreeSWITCH → Django)
- `/telephony/dialplan/` и `/telephony/events/` — внутренние эндпоинты, вызываемые FreeSWITCH, **не браузером**
- Аутентификация: shared secret через заголовок `X-FreeSWITCH-Token` (из env `FREESWITCH_ESL_PASSWORD`)
- Эти эндпоинты исключены из JWT-проверки, но защищены проверкой shared secret + IP whitelist (только docker-сеть)

### Общее
- CSRF для Django-rendered страниц (signing page, admin)
- SPA: CSRF не нужен (JWT Bearer auth, не cookies)
- `@csrf_exempt` + `@xframe_options_exempt` только для Bitrix24 iframe endpoints
- HTTPS обязателен в production
- `SECURE_SSL_REDIRECT = True`, `SESSION_COOKIE_SECURE = True`

---

## 11. Celery-задачи (tenant-aware)

```python
# Каждая задача оборачивается в tenant context:
from django_tenants.utils import tenant_context

@shared_task
def process_webhook(tenant_id: int, payload: dict):
    tenant = Tenant.objects.get(id=tenant_id)
    with tenant_context(tenant):
        # Здесь все ORM-запросы идут в schema тенанта
        connection = CRMConnection.objects.get(...)
        adapter = get_adapter(connection)
        ...
```

**Задачи:**
| Задача | Триггер | Описание |
|--------|---------|----------|
| `process_incoming_webhook` | Вебхук от CRM | Разобрать payload, найти правило распределения, назначить |
| `sync_crm_users` | Периодическая / ручная | Синхронизация менеджеров из CRM → ManagerProfile |
| `send_otp` | Отправка на подписание | Отправить SMS/email с OTP-кодом |
| `notify_contract_signed` | Подписание | Webhook в CRM: обновить поля сделки, загрузить PDF |
| `expire_signing_sessions` | Beat: каждые 30 мин | Пометить истёкшие сессии |
| `send_notification_email` | Событие | Отправить email-уведомление |
| `send_telegram_notification` | Событие | Отправить Telegram-уведомление через Bot API |
| `check_plan_limits` | Beat: каждый час | Проверить лимиты тенантов, отправить предупреждения (80%/100%) |
| `check_crm_connections_health` | Beat: каждые 15 мин | Проверить доступность CRM, уведомить при потере связи |
| `route_incoming_message` | Webhook мессенджера | Обработать входящее сообщение → отправить в CRM |
| `route_outgoing_message` | Webhook CRM (ответ) | Отправить ответ менеджера клиенту в мессенджер |
| `process_freeswitch_cdr` | ESL event (hangup) | Создать/обновить CallRecord, зарегистрировать звонок в CRM |
| `upload_call_record_to_crm` | Завершение звонка | Загрузить запись из FreeSWITCH volume в CRM |
| `create_lead_from_missed_call` | Пропущенный звонок | Создать лид в CRM + распределить по правилам |
| `sync_freeswitch_config` | Создание/изменение SIPTrunk | Сгенерировать XML-конфиг FreeSWITCH, отправить reloadxml через ESL |
| `check_sip_registrations` | Beat: каждые 5 мин | Проверить статус регистрации транков, обновить SIPTrunk.status |
| `process_stage_auto_action` | Перемещение сделки | Выполнить auto_action стадии (создать договор, задачу, уведомление) |
| `check_overdue_tasks` | Beat: каждый час | Пометить просроченные задачи (Activity.status planned→overdue), уведомить |
| `create_deal_from_source` | Входящий звонок/сообщение | Создать Deal + Contact во встроенном CRM при crm_mode=builtin |

---

## 12. Docker-compose (development)

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: platform_db
      POSTGRES_USER: platform
      POSTGRES_PASSWORD: platform_dev
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7.4-alpine
    ports:
      - "6379:6379"

  web:
    build: .
    command: uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --reload
    # Production: gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000
    volumes:
      - .:/app
      - call_recordings:/app/media/calls
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    env_file:
      - .env

  frontend:
    image: node:24-alpine
    working_dir: /app
    command: sh -c "npm install && npx vite --host 0.0.0.0"
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules   # Persist node_modules across restarts
    ports:
      - "5173:5173"            # Vite dev server
    environment:
      - VITE_API_URL=http://localhost:8000/api

  celery:
    build: .
    command: celery -A config worker -l info
    volumes:
      - .:/app
      - call_recordings:/app/media/calls   # Shared с web и freeswitch (для upload_call_record_to_crm)
    depends_on:
      - db
      - redis
    env_file:
      - .env

  celery-beat:
    build: .
    command: celery -A config beat -l info
    volumes:
      - .:/app
    depends_on:
      - db
      - redis
    env_file:
      - .env

  freeswitch:
    image: signalwire/freeswitch-public:1.10
    ports:
      - "5060:5060/udp"         # SIP UDP
      - "5060:5060/tcp"         # SIP TCP
      - "5061:5061/tcp"         # SIP TLS
      - "7443:7443/tcp"         # WSS (WebRTC signaling — verto/SIP.js)
      - "16384-16484:16384-16484/udp"  # RTP media (100 портов)
    volumes:
      - freeswitch_conf:/etc/freeswitch       # Конфиги (генерируются Django)
      - freeswitch_recordings:/var/lib/freeswitch/recordings   # Записи
      - call_recordings:/app/media/calls      # Shared с Django
    environment:
      - ESL_PASSWORD=${FREESWITCH_ESL_PASSWORD:-ClueCon}
    restart: unless-stopped

volumes:
  pgdata:
  freeswitch_conf:
  freeswitch_recordings:
  call_recordings:
  frontend_node_modules:
```

---

## 13. Требуемые зависимости (requirements.txt)

```
# Версии зафиксированы на апрель 2026. Обновлять осознанно.
Django>=5.2,<5.3               # LTS до апреля 2028
django-ninja==1.6.2
django-tenants==3.10.1
psycopg[binary]==3.3.3
celery[redis]==5.6.3
redis==7.4.0
weasyprint==68.1
django-fernet-encrypted-fields==0.3.1
gunicorn==25.3.0
requests==2.33.1
python-telegram-bot==21.11.1   # Telegram Bot API для уведомлений + мессенджер-каналы
httpx==0.28.1                  # Async HTTP для WhatsApp провайдеров
greenswitch==0.3.3             # FreeSWITCH ESL (Event Socket Library) для Python
django-ninja-jwt==5.3.3        # JWT auth для django-ninja (ninja-нативный, без DRF)
django-cors-headers==4.7.0     # CORS для Vue dev server
django-environ==0.12.0         # Типизированный доступ к env-переменным (env.list, env.bool, ...)
channels==4.2.0                # Django Channels (ASGI + WebSocket)
channels-redis==4.2.1          # Redis channel layer для Django Channels
uvicorn[standard]==0.34.0      # ASGI-сервер (HTTP + WebSocket)
Pillow==11.2.1                 # ImageField (Tenant.logo)
```

### frontend/package.json (основные зависимости)

```json
{
  "dependencies": {
    "vue": "^3.5",
    "vue-router": "^4",
    "pinia": "^3",
    "primevue": "^4",
    "primeicons": "^7",
    "@primevue/themes": "^4",
    "ofetch": "^1",
    "sip.js": "^0.21"
  },
  "devDependencies": {
    "vite": "^6",
    "@vitejs/plugin-vue": "^5",
    "tailwindcss": "^4",
    "typescript": "^5.7"
  }
}
```

---

## 14. Порядок реализации

### Этап 1: Каркас (tenants + billing + users + auth)
- Django-проект с django-tenants
- Модели Tenant, Domain, User, Membership
- Модели Plan, Feature + базовые фикстуры (3 плана)
- `require_feature` декоратор + API эндпоинт /tenant/plan/ с фичами
- Регистрация организации (создание тенанта + owner + назначение плана)
- JWT auth (django-ninja-jwt), CORS (django-cors-headers)
- ASGI: uvicorn + Django Channels + channels-redis (WebSocket для уведомлений, звонков, Kanban)
- Логин, приглашение пользователей
- Django Admin: управление планами, функциями, тенантами

### Этап 1b: Frontend SPA (Vue 3)
- Клонировать Sakai template (`github.com/primefaces/sakai-vue`), настроить Aura preset + `definePreset()` для brand-цветов
- Vite + Vue 3 + PrimeVue + Tailwind + Pinia + Vue Router (Sakai уже включает большинство)
- Layout из Sakai: sidebar, header (NotificationBell, профиль), breadcrumbs, dark mode
- Pinia stores: auth, tenant
- Composables: useAuth, useTenant, useFeatureGate
- Router guards: auth + role + feature
- Страницы: логин, главная, команда, настройки, подписка
- FeatureGate.vue + серые пункты меню
- OnboardingWizard.vue (компонент, 5 шагов)
- Dockerfile.frontend (мультистейдж: node build → nginx)

### Этап 1c: Аудит + уведомления
- AuditEvent модель + log_event() + страница в ЛК
- Notification, NotificationPreference, TelegramBinding модели
- Email-уведомления (Django send_mail)
- In-app уведомления (колокольчик в header ЛК)
- Telegram-бот для уведомлений (привязка через /start токен)
- Настройки уведомлений в ЛК
- Celery: check_plan_limits, check_crm_connections_health

### Этап 2: CRM-интеграции + Встроенный CRM
- Models: CRMConnection, WebhookEndpoint, ManagerProfile, ManagerDayOff
- CRMAdapter protocol + AmoCRMAdapter + Bitrix24Adapter
- UI: подключение CRM (OAuth flow для Amo, webhook/OAuth для Bitrix)
- Синхронизация менеджеров
- Приём вебхуков
- **Встроенный CRM (apps/crm):**
  - Models: Contact, Company, Pipeline, Stage, Deal, Activity
  - BuiltinCRMAdapter (реализация CRMAdapterProtocol через ORM)
  - Tenant.crm_mode + переключение в UI (онбординг шаг 2)
  - API: CRUD контактов, компаний, воронок, стадий, сделок, активностей
  - Vue: KanbanBoard, DealCard, DealTimeline, ContactCard, PipelineSettings, TaskList
  - Kanban drag-and-drop (перемещение сделок между стадиями)  
  - Auto-action при смене стадии (создать договор, задачу, уведомление)
  - get_adapter_for_tenant() — единая точка получения адаптера по crm_mode

### Этап 3: Распределение заявок
- Models: DistributionRule, DistributionLog
- 4 стратегии: min_load, round_robin, weighted, manual_queue
- UI: настройка правил, просмотр лога
- Celery-задача: обработка вебхука → выбор правила → назначение → уведомление в CRM

### Этап 4: Договоры и подписание
- Models: ContractTemplate, FieldMapping, Contract, SigningSession
- Генерация PDF (WeasyPrint)
- UI: редактор шаблонов, маппинг полей, превью
- Публичная страница подписания
- OTP (SMS через внешний провайдер / email через Django send_mail)
- Webhook в CRM после подписания

### Этап 5: Мессенджер-каналы
- Models: MessengerChannel, ChatSession, MessageLog
- Telegram Bot: приём/отправка через python-telegram-bot
- WhatsApp Business: Meta Cloud API (официальный)
- WhatsApp: через провайдера (Wazzup / Green API)
- MAX: Bot API (аналогично Telegram)
- CRM мост: amoCRM Chats API (amojo), Bitrix24 Open Lines connector
- UI: подключение каналов, лог сообщений, статистика

### Этап 6: Телефония (FreeSWITCH)
- FreeSWITCH в Docker, ESL-подключение из Django (greenswitch)
- Models: SIPTrunk, PhoneExtension, IVRMenu, CallQueue, CallRecord
- Динамический диалплан: mod_httapi → Django API (per-tenant маршрутизация)
- SIP-транки: Zadarma, MCN Telecom, произвольный SIP
- WebRTC: звонки из браузера ЛК (SIP.js/verto + FreeSWITCH WSS)
- IVR-конструктор, очереди звонков
- Click-to-call из ЛК
- CRM мост: amoCRM Calls API, Bitrix24 telephony.externalcall
- Пропущенный → авто-лид + распределение
- Записи разговоров в shared volume, загрузка в CRM
- UI: SIP-транки, extensions, IVR-конструктор, очереди, журнал, плеер, WebRTC-софтфон
- Интеграция с встроенным CRM: звонок → Activity в таймлайне сделки

### Этап 7: Дашборд и аналитика
- Статистика по менеджерам, договорам, распределению, каналам, звонкам
- Экспорт в PDF/Excel

---

## 15. Ведение документации (AGENTS.md + docs/)

### Структура docs/

```
docs/
  TASK_STATE.md       # Текущие задачи: статус, блокеры
  DECISIONS.md        # Архитектурные решения (DEC-001, DEC-002, ...)
  KNOWN_ISSUES.md     # Известные баги и ограничения
  DEV_LOG.md          # Лог изменений: дата, файлы, валидация, риски
  RELEASE_NOTES.md    # Пользовательские изменения (на русском, без техдеталей)
  VERSIONING.md       # Правила версионирования и формат коммитов
```

### AGENTS.md (корень проекта)

Протокол для AI-агентов и разработчиков. Включить:

```markdown
# AGENTS: Protocol for This Repository

## Mandatory Read Order Before Any Code Change
1. docs/TASK_STATE.md
2. docs/DECISIONS.md
3. docs/KNOWN_ISSUES.md
4. docs/DEV_LOG.md (latest entries first)
5. Current task file (task.md when present)

If instructions conflict — STOP and ask user.

## Non-Negotiable Guardrails
- Stack: Django 5.2 LTS, Python 3.13, PostgreSQL, Redis, Celery,
  django-tenants, django-ninja, Django Channels, uvicorn, WeasyPrint, FreeSWITCH,
  Vue 3, Vite, PrimeVue, Tailwind CSS, Pinia, SIP.js, Docker
- Frontend: Vue 3 SPA в `frontend/`. Django НЕ рендерит HTML для ЛК.
- Docker-only development. No host installs.
- Do not remove production data without explicit approval.

## Update Ritual (After Non-Trivial Changes)
1. docs/DECISIONS.md — если изменилось поведение/инвариант
2. docs/TASK_STATE.md — обновить статус (done/in-progress/blocked)
3. docs/DEV_LOG.md — дата, файлы, валидация, риски
4. docs/KNOWN_ISSUES.md — если найден или закрыт баг
5. docs/RELEASE_NOTES.md — если изменение видно пользователю:
   - Язык: русский
   - Без технических деталей
   - Группировка по дате → «Новое», «Улучшения», «Исправления»

## Validation Baseline (Docker)
1. docker compose down
2. docker compose up -d --build
3. docker compose run --rm web python manage.py check
4. Targeted tests for changed modules
5. Manual HTTP check for affected pages

If any step fails — fix and rerun. Partial validation ≠ done.
```

### docs/DECISIONS.md — формат записей

```markdown
## DEC-NNN: Краткое название (YYYY-MM-DD)
**Контекст:** Почему принимали решение.
**Решение:** Что именно решили.
**Последствия:** Что это меняет, какие ограничения.
```

### docs/TASK_STATE.md — формат

```markdown
## Текущие задачи
| # | Задача | Статус | Заметки |
|---|--------|--------|---------|
| 1 | Каркас tenants + users | in-progress | ... |

## Завершённые задачи
| # | Задача | Дата | Заметки |
|---|--------|------|---------|
```

### docs/DEV_LOG.md — формат

```markdown
## YYYY-MM-DD — Краткое описание
- **Файлы:** apps/tenants/models.py, config/settings.py
- **Что сделано:** Добавлена модель Tenant с django-tenants
- **Валидация:** docker compose up --build ✓, manage.py check ✓, 12 tests ✓
- **Риски:** Нет
```

### docs/KNOWN_ISSUES.md — формат

```markdown
### KI-NNN: Краткое описание
- **Статус:** open | closed | wontfix
- **Обнаружено:** YYYY-MM-DD
- **Описание:** Что происходит и при каких условиях.
- **Обходной путь:** Если есть.
```

### docs/RELEASE_NOTES.md — формат

```markdown
## DD.MM.YYYY

### Новое
- Добавлена возможность подключения amoCRM

### Улучшения
- Ускорена загрузка списка договоров

### Исправления
- Исправлена ошибка при отправке OTP на email
```

---

## 16. Env-переменные (.env.example)

```bash
# Django
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=*

# Database
DATABASE_URL=postgres://platform:platform_dev@db:5432/platform_db

# Redis
REDIS_URL=redis://redis:6379/0

# Encryption
FIELD_ENCRYPTION_KEY=generate-32-byte-key-base64

# SMS provider (для OTP)
SMS_PROVIDER=stub          # stub | smsc | smsaero
SMS_API_KEY=
SMS_SENDER_NAME=Platform

# Email
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=noreply@platform.ru

# Bitrix24 App (для OAuth iframe-приложения)
BITRIX24_APP_ID=
BITRIX24_APP_SECRET=

# amoCRM App (для OAuth)
AMOCRM_CLIENT_ID=
AMOCRM_CLIENT_SECRET=
AMOCRM_REDIRECT_URI=

# Platform
PLATFORM_DOMAIN=localhost:8000
PLATFORM_PROTOCOL=http

# FreeSWITCH
FREESWITCH_ESL_HOST=freeswitch
FREESWITCH_ESL_PORT=8021
FREESWITCH_ESL_PASSWORD=ClueCon
FREESWITCH_WSS_URL=wss://localhost:7443

# Telegram Bot (платформенный бот для уведомлений — отдельный от мессенджер-каналов)
TELEGRAM_NOTIFICATION_BOT_TOKEN=

# Frontend (Vite)
VITE_API_URL=http://localhost:8000/api

# CORS (для dev — Vite dev server)
CORS_ALLOWED_ORIGINS=http://localhost:5173
```
