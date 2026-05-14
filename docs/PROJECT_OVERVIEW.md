# Bakanov API — Полная документация проекта

> Документ актуален на 2026-05-14. При изменении архитектуры обновляйте этот файл.

---

## 1. Общее описание

**Bakanov API** — это бэкенд-система (MVP-стадия), объединяющая CRM-интеграции, генерацию документов, телефонию, аналитику и внутренний дашборд для компании по организации яхтенных чартеров. Система работает преимущественно с **amoCRM** и **Bitrix24**, а также с рядом внешних сервисов (Яндекс.Метрика, Telegram, Deepgram, Zadarma, Novofon, Google Forms).

---

## 2. Технологический стек

| Слой | Технология | Версия |
|------|-----------|--------|
| Backend | Django | 5.2 LTS |
| Python | Python | 3.13 |
| API | django-ninja | 1.6.2 |
| База данных | PostgreSQL | 18 (Alpine образ) |
| Кэш / брокер | Redis | 8 (Alpine образ) |
| Фоновые задачи | Celery + Beat + Flower | 5.6.3 |
| Генерация PDF | WeasyPrint + ReportLab | — |
| Шаблоны | Django Templates + DaisyUI + Tailwind CSS (CDN) |
| Интерактивность | Alpine.js + HTMX | CDN |
| Docker | docker / docker-compose | — |
| WSGI-сервер | Gunicorn | 25.3.0 |

---

## 3. Структура проекта

```
/
├── apps/
│   ├── users/               # Пользователи и роли
│   ├── crm/                 # amoCRM: договоры, менеджеры, лиды, звонки
│   ├── dashboard/           # Веб-интерфейс (личный кабинет, отчеты, аналитика)
│   └── integrations/        # Внешние интеграции (Bitrix24, телефония, AI, почта)
├── config/                  # Настройки Django, Celery, URLs, API root
├── docs/                    # Документация проекта
├── scripts/                 # Вспомогательные скрипты
├── templates/               # HTML-шаблоны Django
├── static/                  # Статика (vendor JS/CSS)
├── staticfiles/             # Собранная статика (collectstatic)
├── media/                   # Загруженные файлы (договора, звонки)
├── docker-compose.yml       # Локальная разработка
├── docker-compose.prod.yml  # Production
├── Dockerfile               # Образ приложения
├── manage.py
└── requirements.txt
```

---

## 4. Приложения Django

### 4.1 `apps.users` — Пользователи

**Модель:** `User` (наследник `AbstractUser`)

Поля:
- `role` — роль пользователя: `manager`, `head` (РОП), `admin`

**Роли и доступ:**
- `manager` — просмотр своих данных
- `head` — управление менеджерами, отчеты, аналитика
- `admin` — полный доступ

---

### 4.2 `apps.crm` — CRM Core

#### Модели

| Модель | Назначение |
|--------|-----------|
| `DealSnapshot` | Снимок сделки из amoCRM |
| `CallAnalysis` | Анализ телефонного звонка (STT + AI) |
| `AmoManagerProfile` | Профиль менеджера из amoCRM (график, нагрузка) |
| `ManagerWeekdaySchedule` | Рабочие/выходные дни недели для менеджера |
| `ManagerDayOff` | Конкретные выходные дни менеджера |
| `AmoLead` | Лид из amoCRM (локальная копия с назначенным менеджером) |
| `AmoLeadAssignmentEvent` | История назначения лидов менеджерам |
| `GoogleFormReport` | Отчеты из Google Forms (меню/круиз) |

#### Сервисы

| Сервис | Файл | Назначение |
|--------|------|-----------|
| `AmoCRMClient` | `services/amocrm.py` | HTTP-клиент для amoCRM API v4 (leads, contacts, companies, pipelines, upload файлов) |
| `ContractRenderer` | `services/contract_renderer.py` | Генерация PDF-договоров из HTML-шаблонов. Имеет source-agnostic метод `build_context_from_data(data)` для работы с любым источником данных (amoCRM, Bitrix24, ручной ввод) |
| `DealAssignmentService` | `services/manager_assignment.py` | Автоматическое распределение новых лидов по менеджерам с учетом нагрузки и графика |
| `AmoManagerSyncService` | `services/manager_assignment.py` | Синхронизация списка менеджеров из amoCRM |

**Генерация договоров (amoCRM):**
- Берет данные из amoCRM (lead, contact, company)
- Маппит поля amoCRM → нормализованный словарь → `build_context_from_data()`
- Рендерит в PDF через WeasyPrint
- Загружает файл обратно в amoCRM (поле `CONTRACT_FILE_FIELD_ID`)
- Отправляет PDF по email

**Генерация договоров (Bitrix24):**
- Данные подтягиваются из сделки/контакта через BX24 JS SDK (клиентская сторона)
- Менеджер редактирует поля в iframe-форме перед генерацией
- POST на сервер → `Bitrix24ContractService.render_contract()` → PDF
- PDF загружается в файловое поле сделки Bitrix24, отправляется по email

**Распределение лидов:**
1. Синхронизация менеджеров (`sync_amo_managers`)
2. Учет рабочих дней (`ManagerWeekdaySchedule`) и выходных (`ManagerDayOff`)
3. Расчет нагрузки: `weekly_deals / working_days`
4. Выбор менеджера с минимальной нагрузкой
5. Обновление ответственного в amoCRM
6. Уведомление в Telegram

---

### 4.3 `apps.dashboard` — Личный кабинет

Веб-интерфейс для руководителей и менеджеров.

#### URL-ы (роуты)

| URL | Назначение | Доступ |
|-----|-----------|--------|
| `/` | Главная страница дашборда | Авторизованные |
| `/analytics/` | Страница аналитики | Все роли |
| `/reports/` | Список доступных отчетов | head/admin |
| `/reports/rop-funnel/` | Отчет по воронке РОП | head/admin |
| `/managers/` | Управление менеджерами (график, выходные) | head/admin |
| `/settings/` | Настройки и статус интеграций | head/admin |

#### API дашборда

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/reports/api/<key>/` | GET | Данные отчета в JSON |
| `/reports/api/<key>/meta/` | GET | Метаданные отчета (воронки, менеджеры) |
| `/reports/api/<key>/export/<format>/` | GET | Экспорт отчета (pdf, xls, excel) |
| `/api/analytics/managers-deals/` | GET | График сделок по менеджерам |
| `/api/analytics/stages-deals/` | GET | График сделок по этапам |

#### Сервисы отчетов

- `local_analytics.py` — локальная аналитика из БД
- `report_catalog.py` — каталог отчетов, метаданные, кэширование
- `report_export.py` — экспорт в Excel/PDF
- `rop_report.py` — отчет РОП
- `stage_conversion_report.py` — отчет по конверсии этапов

---

### 4.4 `apps.integrations` — Внешние интеграции

#### Модели

| Модель | Назначение |
|--------|-----------|
| `Bitrix24Portal` | OAuth-токены подключенного портала Bitrix24 (member_id, domain, tokens) |

#### Сервисы

| Сервис | Файл | Назначение |
|--------|------|-----------|
| `AIAnalysisService` | `ai_service.py` | Анализ текста через Yandex GPT |
| `AmoCrmSpamLeadSyncService` | `amocrm_spam_lead_service.py` | Загрузка `client_id` спам-лидов в Яндекс.Метрику (offline conversions) |
| `Bitrix24SpamLeadSyncService` | `bitrix24_spam_lead_service.py` | Загрузка `client_id` спам-лидов/сделок Bitrix24 в Яндекс.Метрику |
| `Bitrix24Client` | `bitrix24_service.py` | REST API клиент Bitrix24 (outgoing webhooks / OAuth) |
| `Bitrix24ContractService` | `bitrix24_contract_service.py` | Генерация договоров из данных Bitrix24: маппинг UF_CRM_* полей, рендеринг PDF, загрузка в сделку |
| `Bitrix24WebhookProcessor` | `bitrix24_webhook_handler.py` | Обработчик входящих webhook-ов Bitrix24 |
| `Bitrix24OAuthService` | `bitrix24_oauth.py` | OAuth-авторизация и обновление токенов Bitrix24 |
| `EmailService` | `email_service.py` | Отправка email (договоры, отчеты) |
| `GoogleFormReportService` | `google_form_report_service.py` | Генерация PDF-отчетов из Google Forms |
| `MetrikaService` | `metrika_service.py` | Загрузка offline конверсий в Яндекс.Метрику |
| `PDFService` | `pdf_service.py` | Генерация PDF (билингвальные отчеты) |
| `STTService` | `stt_service.py` | Speech-to-Text (Deepgram / Yandex) |
| `TelegramService` | `telegram_service.py` | Отправка сообщений в Telegram |
| `TelephonyService` | `telephony_service.py` | Обработка звонков (Zadarma / Novofon) |
| `TelephonyWebhookProcessor` | `telephony_pipeline.py` | Pipeline обработки webhook-ов телефонии |
| `TranslationService` | `translation_service.py` | Перевод RU → EN (deep-translator) |

---

## 5. API Endpoints (django-ninja)

Все API начинаются с `/api/`.

### 5.1 CRM (`/api/crm/`)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/contract/generate` | POST | Сгенерировать договор по lead_id, отправить email, загрузить в amoCRM |
| `/contract/extra/generate` | POST | Сгенерировать доп. соглашение |
| `/lead/assign-min-load` | POST | Назначить lead на менеджера с минимальной нагрузкой |
| `/lead/new/telegram-notify` | POST | Уведомить в Telegram о новом лиде |
| `/amo/managers/sync` | POST | Запустить синхронизацию менеджеров (Celery) |
| `/amo/webhook/new-deals` | POST | Входящий webhook от amoCRM (новые сделки → распределение) |

### 5.2 Integrations (`/api/integrations/`)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/webhooks/zadarma` | POST | Звонок от Zadarma |
| `/webhooks/novofon` | POST | Звонок от Novofon |
| `/webhooks/google-form` | POST | Универсальный webhook Google Form (PDF + email) |
| `/webhooks/google-form/menu` | POST | Форма "Меню" (генерация отчетов RU/EN) |
| `/webhooks/google-form/cruise` | POST | Форма "Круиз" (генерация отчетов RU/EN) |
| `/webhooks/amocrm/spam-lead` | POST | Спам-лид из amoCRM → загрузка client_id в Метрику |
| `/webhooks/bitrix24` | POST | События CRM Bitrix24 (lead/deal/contact) |
| `/webhooks/bitrix24/spam-lead` | POST | Спам-лид/сделка из Bitrix24 → загрузка client_id в Метрику |
| `/amocrm/oauth/callback` | GET | Callback для OAuth amoCRM |

### 5.3 Bitrix24 iframe-приложения

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/bitrix24/install/` | POST | Callback установки локального приложения |
| `/bitrix24/app/` | POST | Основное приложение (дашборд, статистика CRM) |
| `/bitrix24/contract/` | POST | Форма создания договора (placement в карточке сделки) |
| `/bitrix24/contract/generate/` | POST | API генерации PDF договора (JSON) |

### 5.4 Системные

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/healthz` | GET | Проверка работоспособности |

---

## 6. Фоновые задачи Celery

| Задача | Файл | Расписание / Триггер | Описание |
|--------|------|---------------------|----------|
| `send_daily_deals_report` | `apps.crm.tasks` | Раз в сутки (beat) | Отправка ежедневного отчета по email |
| `publish_evening_telegram_post` | `apps.integrations.tasks` | Раз в сутки (beat) | Вечерний пост в Telegram (заглушка) |
| `process_amo_new_deal_webhook` | `apps.crm.tasks` | Webhook → Celery | Распределение нового лида по менеджерам |
| `sync_amo_managers` | `apps.crm.tasks` | API или beat | Синхронизация списка менеджеров из amoCRM |
| `process_amocrm_spam_lead_webhook` | `apps.integrations.tasks` | Webhook → Celery | Загрузка client_id спам-лида в Яндекс.Метрику |
| `process_bitrix24_webhook` | `apps.integrations.tasks` | Webhook → Celery | Асинхронная обработка события Bitrix24 |
| `process_bitrix24_spam_lead_webhook` | `apps.integrations.tasks` | Webhook → Celery | Загрузка client_id спам-лида Bitrix24 в Яндекс.Метрику |

---

## 7. Ключевые бизнес-процессы

### 7.1 Генерация договора

```
POST /api/crm/contract/generate (lead_id)
  → AmoCRMClient.get_lead(lead_id)
  → ContractRenderer.render_for_lead()
    → get_contact + get_company
    → build_context (custom fields из amoCRM)
    → render_to_string(HTML template)
    → WeasyPrint → PDF
  → send_contract_email()
  → AmoCRMClient.upload_contract_link()
  → AmoCRMClient.upload_file_to_lead_field()
  → JSON response с file_url
```

### 7.2 Автоматическое распределение лидов

```
amoCRM webhook (new deal)
  → POST /api/crm/amo/webhook/new-deals
  → extract_webhook_lead_ids()
  → process_amo_new_deal_webhook.delay(lead_id) [Celery]
    → DealAssignmentService.handle_single_new_deal()
      → choose_manager() (по нагрузке и графику)
      → update_lead_responsible() в amoCRM
      → upsert_lead_from_payload() в локальную БД
      → send_telegram_message()
```

### 7.3 Спам-лиды в Яндекс.Метрику

```
amoCRM webhook (spam lead)
  → POST /api/integrations/webhooks/amocrm/spam-lead
  → process_amocrm_spam_lead_webhook.delay(lead_id) [Celery]
    → AmoCrmSpamLeadSyncService.sync_lead()
      → get_lead (сделка)
      → get_contact (контакт)
      → get_company (компания)
      → извлечение client_id из custom fields
      → MetrikaService.upload_offline_conversions()
```

### 7.4 Bitrix24 интеграция

**Outgoing (из нашей системы в Bitrix24):**
```
Bitrix24Client.from_settings() или from_portal()
  → REST API вызовы (leads, deals, contacts, companies)
```

**Incoming (из Bitrix24 в нашу систему):**
```
Bitrix24 → webhook → POST /api/integrations/webhooks/bitrix24
  → verify_inbound_token()
  → process_bitrix24_webhook.delay(event, entity_id) [Celery]
    → Bitrix24WebhookProcessor.process()
```

**Встроенное приложение (iframe):**
```
Bitrix24 → install → POST /bitrix24/install/ (BX24.installFinish)
Bitrix24 → iframe → POST /bitrix24/app/ (OAuth, UI DaisyUI)
```

**Генерация договора (Bitrix24):**
```
Bitrix24 → placement (CRM_DEAL_DETAIL_TAB) → POST /bitrix24/contract/
  → рендерит форму (DaisyUI + Alpine.js + BX24 JS SDK)
  → BX24.callBatch: crm.deal.get + crm.contact.get
  → автозаполнение полей формы

Менеджер редактирует → нажимает "Сформировать"
  → POST /bitrix24/contract/generate/ (JSON: member_id, deal_id, overrides)
    → Bitrix24ContractService.from_portal(portal)
    → render_contract(deal_id, overrides)
      → get_deal_data + get_contact_data + get_company_data
      → build_context_from_deal() → build_context_from_data()
      → WeasyPrint → PDF
    → crm.deal.update (загрузка PDF в файловое поле)
    → send_contract_email()
  → JSON response {status, file_url}
```

---

## 8. Переменные окружения (.env)

### Обязательные

| Переменная | Описание |
|-----------|----------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Режим отладки (`true`/`false`) |
| `ALLOWED_HOSTS` | Список разрешенных хостов |
| `POSTGRES_*` | Настройки PostgreSQL |
| `REDIS_URL` | URL Redis (`redis://redis:6379/0`) |

### amoCRM

| Переменная | Описание |
|-----------|----------|
| `AMOCRM_BASE_URL` | Базовый URL amoCRM |
| `AMOCRM_ACCESS_TOKEN` | OAuth access token |
| `AMOCRM_REDIRECT_URI` | URI для OAuth callback |
| `CONTRACT_FILE_FIELD_ID` | ID поля в amoCRM для загрузки договора |
| `EXTRA_CONTRACT_FILE_FIELD_ID` | ID поля для доп. соглашения |

### Bitrix24

| Переменная | Описание |
|-----------|----------|
| `BITRIX24_WEBHOOK_URL` | URL исходящего webhook |
| `BITRIX24_INBOUND_TOKEN` | Токен для валидации входящих webhook |
| `BITRIX24_APP_ID` | ID приложения Bitrix24 |
| `BITRIX24_APP_SECRET` | Секрет приложения Bitrix24 |
| `BITRIX24_SPAM_CLIENT_ID_FIELD_CODES` | Коды UF_CRM_ полей с client_id (через запятую) |
| `BITRIX24_SPAM_CLIENT_ID_FIELD_NAMES` | Названия полей с client_id (через запятую) |

### Bitrix24 — маппинг полей договоров

| Переменная | Описание |
|-----------|----------|
| `BITRIX24_CONTRACT_FIELD_MARINA` | UF_CRM_ код поля "Марина" в сделке |
| `BITRIX24_CONTRACT_FIELD_BOAT_TYPE` | UF_CRM_ код поля "Тип яхты" |
| `BITRIX24_CONTRACT_FIELD_CABINS` | UF_CRM_ код поля "Количество кают" |
| `BITRIX24_CONTRACT_FIELD_CLIENTS` | UF_CRM_ код поля "Количество человек" |
| `BITRIX24_CONTRACT_FIELD_CLIENT_COUNTRY` | UF_CRM_ код поля "Страна клиента" |
| `BITRIX24_CONTRACT_FIELD_TRIP_START` | UF_CRM_ код поля "Дата начала круиза" |
| `BITRIX24_CONTRACT_FIELD_TRIP_END` | UF_CRM_ код поля "Дата окончания круиза" |
| `BITRIX24_CONTRACT_FIELD_CRUISE_TYPE` | UF_CRM_ код поля "Вид договора" |
| `BITRIX24_CONTRACT_FIELD_EXTRA` | UF_CRM_ код поля "Доп. услуги" |
| `BITRIX24_CONTRACT_FIELD_TAX` | UF_CRM_ код поля "Налоги и сборы" |
| `BITRIX24_CONTRACT_FILE_FIELD_ID` | UF_CRM_ код файлового поля для загрузки PDF |
| `BITRIX24_CONTRACT_FIELD_BIRTHDATE` | UF_CRM_ код поля "Дата рождения" в контакте |
| `BITRIX24_CONTRACT_FIELD_PASSPORT_NUMBER` | UF_CRM_ код поля "Паспорт номер" |
| `BITRIX24_CONTRACT_FIELD_PASSPORT_DATE` | UF_CRM_ код поля "Паспорт дата выдачи" |
| `BITRIX24_CONTRACT_FIELD_PASSPORT_ISSUED` | UF_CRM_ код поля "Паспорт кем выдан" |
| `BITRIX24_CONTRACT_FIELD_PASSPORT_BPLACE` | UF_CRM_ код поля "Место рождения" |

### Телефония и AI

| Переменная | Описание |
|-----------|----------|
| `DEEPGRAM_API_KEY` | API ключ Deepgram (STT) |
| `YANDEX_API_KEY` | API ключ Yandex (GPT / STT) |
| `YANDEX_METRIKA_TOKEN` | Токен Яндекс.Метрики |
| `YANDEX_METRIKA_COUNTER_ID` | ID счетчика |
| `YANDEX_METRIKA_OFFLINE_GOAL_ID` | ID цели offline конверсии |

### Уведомления

| Переменная | Описание |
|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений |
| `SMTP_*` | Настройки SMTP |
| `DOCUMENTS_EMAIL_TO` | Email для отправки документов |

### Договоры

| Переменная | Описание |
|-----------|----------|
| `CONTRACT_HTML_TEMPLATE` | Шаблон договора (физлицо) |
| `CONTRACT_HTML_TEMPLATE_U` | Шаблон договора (юрлицо) |
| `EXTRA_CONTRACT_HTML_TEMPLATE` | Шаблон доп. соглашения |
| `CONTRACT_EUR_RATE` | Курс EUR/RUB для договоров |

---

## 9. Запуск и развёртывание

### Локальная разработка (Docker)

```bash
# 1. Скопировать окружение
cp .env.dev.example .env

# 2. Запустить
sudo docker compose up --build

# 3. Создать суперпользователя
docker compose exec web python manage.py createsuperuser
```

### Production

```bash
cp .env.prod.example .env
sudo docker compose -f docker-compose.prod.yml up -d --build
```

### Скрипты деплоя

| Скрипт | Назначение |
|--------|-----------|
| `init.sh` | Первичная настройка сервера (nginx, certbot, docker) |
| `deploy.sh` | Регулярный деплой |

---

## 10. Тестирование

Тесты находятся в `apps/<app>/tests/`.

```bash
# Запуск всех тестов
docker compose run --rm web python manage.py test

# Запуск конкретного модуля
docker compose run --rm web python manage.py test apps.integrations.tests.test_bitrix24_service
```

**Покрытие (на момент документации):**
- Bitrix24: 34 теста (service, webhook API, webhook handler)
- Bitrix24 iframe: 16 тестов (OAuth, views)
- Bitrix24 contract: тесты (views, service, helpers)

---

## 11. Важные файлы конфигурации

| Файл | Назначение |
|------|-----------|
| `config/settings.py` | Все настройки Django, env-переменные, Celery beat schedule |
| `config/urls.py` | Корневые URL: admin, api, bitrix24, dashboard, auth |
| `config/api.py` | Регистрация роутов django-ninja |
| `config/celery.py` | Конфигурация Celery app |
| `docker-compose.yml` | Локальная среда (web, db, redis, worker, beat, flower) |
| `docker-compose.prod.yml` | Production (без volume mounts, с restart policies) |
| `AGENTS.MD` | Протокол работы AI-агентов в репозитории |

---

## 12. Расширение проекта

Если нужно добавить новую интеграцию:
1. Создать сервис в `apps/integrations/services/`
2. Добавить endpoint в `apps/integrations/api.py`
3. Добавить модель (если нужно) в `apps/integrations/models.py`
4. Добавить тесты в `apps/integrations/tests/`
5. Обновить `.env.example` и `config/settings.py`
6. Обновить `docs/DECISIONS.md` и `docs/DEV_LOG.md`

---

*Документ создан автоматически на основе анализа кодовой базы. Обновляйте при значимых изменениях.*
