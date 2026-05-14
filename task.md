# Задача: Генерация договоров в Bitrix24 (аналог amoCRM)

## Контекст

В amoCRM уже работает генерация PDF-договоров: данные берутся из полей сделки/контакта/компании, заполняются в HTML-шаблон, рендерятся через WeasyPrint, PDF загружается обратно в сделку и отправляется по email.

Нужно реализовать аналогичный функционал для Bitrix24 с улучшенным UX — через встроенное iframe-приложение с формой предпросмотра и редактирования данных перед генерацией.

## Scope (этап 1)

1. **Iframe-приложение в карточке сделки** — вкладка "Договор" в карточке сделки Bitrix24
2. **Предзаполнение данных** — автоматически подтягивать данные из сделки, контакта, компании через BX24 JS SDK
3. **Форма редактирования** — менеджер может скорректировать любое поле перед генерацией
4. **Генерация PDF** — по кнопке "Сформировать договор" рендерить PDF через WeasyPrint (те же шаблоны)
5. **Загрузка в сделку** — сохранять PDF в файловое поле сделки Bitrix24
6. **Отправка по email** — отправлять договор на email клиента

**Не входит в этап 1:** онлайн-подписание, доп. соглашения, работа с юр. лицами.

## Приёмочные критерии

1. В карточке сделки Bitrix24 есть вкладка "Договор"
2. При открытии форма автоматически заполняется данными из сделки и контакта
3. Менеджер может отредактировать любое поле
4. По кнопке генерируется PDF (тот же шаблон, что и в amoCRM)
5. PDF загружается в файловое поле сделки Bitrix24
6. PDF отправляется на email клиента
7. Всё работает в Docker, проходит `manage.py check` и тесты

## Статус: in-progress

---

## Пошаговый план реализации

### Шаг 1: Рефакторинг ContractRenderer — отделение контекста от amoCRM

**Файл:** `apps/crm/services/contract_renderer.py`

**Что сделать:**
- Выделить `build_context_from_data(data: dict) -> dict` — метод, который принимает словарь с готовыми полями и возвращает контекст для шаблона
- Входной словарь `data` — единый формат, независимый от amoCRM/Bitrix24
- Оставить `_build_context()` как обёртку, которая вызывает amoCRM → маппит поля → вызывает `build_context_from_data()`
- Вынести `_calculate_payment_parts`, `_build_destination`, форматтеры — они уже отдельные функции, ок

**Результат:** `ContractRenderer` может генерировать контекст из любого источника данных.

---

### Шаг 2: Маппинг полей Bitrix24 → формат контекста договора

**Файл:** `apps/integrations/services/bitrix24_contract_service.py` (новый)

**Что сделать:**
- Создать сервис `Bitrix24ContractService` с методом `build_context_from_deal(deal: dict, contact: dict, company: dict) -> dict`
- Маппинг полей Bitrix24 (`UF_CRM_*`) в формат контекста договора
- Использовать `Bitrix24Client.from_portal()` для получения данных из Bitrix24 REST API (fallback, если данных нет в POST)
- Учесть что в Bitrix24 поля сделки/контакта приходят в другом формате, чем amoCRM:
  - amoCRM: `custom_fields_values` → `[{field_id, field_name, values: [{value}]}]`
  - Bitrix24: поля верхнего уровня `UF_CRM_*` + вложенные `PHONE`, `EMAIL` и т.д.

**Маппинг полей (предварительный):**

| Контекст договора | Поле Bitrix24 (сделка) | Поле Bitrix24 (контакт) |
|---|---|---|
| `number` | `ID` | — |
| `contract_date` | — | — (текущая дата) |
| `price` | `OPPORTUNITY` | — |
| `marina` | UF_CRM_* (настроить) | — |
| `boat_type` | UF_CRM_* | — |
| `cabins` | UF_CRM_* | — |
| `clients` | UF_CRM_* | — |
| `client_country` | UF_CRM_* | — |
| `trip_start` | UF_CRM_* | — |
| `trip_end` | UF_CRM_* | — |
| `cruise_type` | UF_CRM_* | — |
| `client_fullname` | — | `NAME` + `LAST_NAME` |
| `email` | — | `EMAIL[0].VALUE` |
| `phone` | — | `PHONE[0].VALUE` |
| `client_bdate` | — | UF_CRM_* |
| `client_passport_number` | — | UF_CRM_* |
| `client_passport_date` | — | UF_CRM_* |
| `client_passport_text` | — | UF_CRM_* |
| `client_passport_bplace` | — | UF_CRM_* |
| `payment` | UF_CRM_* | — |
| `extra` | UF_CRM_* | — |

**Решение по маппингу:** Хранить коды UF_CRM_* полей в `settings.py` (аналогично `CONTRACT_FILE_FIELD_ID`), чтобы не хардкодить.

---

### Шаг 3: View для iframe-приложения договора

**Файл:** `apps/integrations/views.py`

**Что сделать:**
- Добавить `bitrix24_contract_form(request)` — view, который рендерит шаблон формы договора
  - Принимает POST от Bitrix24 (аналогично `bitrix24_app`)
  - Проверяет портал по `member_id`
  - Рендерит `bitrix24/contract_form.html`
- Добавить `bitrix24_contract_generate(request)` — API endpoint для генерации PDF
  - Принимает POST с JSON (поля формы)
  - Вызывает `ContractRenderer.build_context_from_data()` → WeasyPrint → PDF
  - Загружает PDF в сделку через `Bitrix24Client.update_deal()` (файловое поле)
  - Отправляет email через `EmailService`
  - Возвращает JSON `{status, file_url}`

**URLs:**
- `POST /bitrix24/contract/` → `bitrix24_contract_form`
- `POST /bitrix24/contract/generate/` → `bitrix24_contract_generate`

---

### Шаг 4: HTML-шаблон формы договора

**Файл:** `templates/bitrix24/contract_form.html` (новый)

**Что сделать:**
- Шаблон на DaisyUI + Alpine.js (как `app.html`)
- BX24 JS SDK для получения данных из сделки
- `BX24.placement.info()` для получения `dealId` из контекста карточки
- `BX24.callBatch` для получения данных сделки + контакта + компании
- Автозаполнение формы из полученных данных
- Все поля редактируемые
- Кнопка "Сформировать договор" → fetch POST → получение PDF URL
- Статус: загрузка / успех / ошибка
- Превью: ссылка на скачивание PDF

**Структура UI:**
```
┌─────────────────────────────────────┐
│ Создание договора                   │
├─────────────────────────────────────┤
│ Сделка: #123 — "Аренда яхты"       │
├─────────────────────────────────────┤
│ ▸ Данные круиза                     │
│   Марина: [select]                  │
│   Тип яхты: [input]                 │
│   Кают: [number]                    │
│   Гостей: [number]                  │
│   Дата начала: [date]               │
│   Дата конца: [date]                │
│   Вид договора: [select]            │
│                                     │
│ ▸ Данные клиента                    │
│   ФИО: [input]                      │
│   Email: [input]                    │
│   Телефон: [input]                  │
│   Дата рождения: [date]             │
│   Паспорт серия/номер: [input]      │
│   Паспорт дата: [date]              │
│   Паспорт кем выдан: [input]        │
│   Место рождения: [input]           │
│                                     │
│ ▸ Финансы                           │
│   Сумма (EUR): [number]             │
│   Курс EUR: [number]                │
│   Реквизиты: [multi-select]         │
│   Доп. услуги: [textarea]           │
│                                     │
│ [Сформировать договор]              │
│                                     │
│ ✓ Договор создан: contract_123.pdf  │
│   [Скачать] [Отправлен на email]    │
└─────────────────────────────────────┘
```

---

### Шаг 5: Регистрация как placement-приложение в Bitrix24

**Контекст:** Чтобы приложение открывалось во вкладке карточки сделки, нужно зарегистрировать его как placement-приложение.

**Что сделать:**
- В `manifest.json` (или в настройках локального приложения в Bitrix24) добавить placement типа `CRM_DEAL_DETAIL_TAB`
- Указать URL: `https://domain/bitrix24/contract/`
- Приложение будет открываться как iframe внутри карточки сделки

**Примечание:** Для локальных приложений placement настраивается в коде установки или в manifest. Нужно проверить, как текущее приложение зарегистрировано, и добавить новый placement.

---

### Шаг 6: Настройки и переменные окружения

**Файлы:** `config/settings.py`, `.env.example`

**Добавить:**
```python
# Bitrix24 Contract Field Mapping
BITRIX24_CONTRACT_FIELD_MARINA = env("BITRIX24_CONTRACT_FIELD_MARINA", default="")
BITRIX24_CONTRACT_FIELD_BOAT_TYPE = env("BITRIX24_CONTRACT_FIELD_BOAT_TYPE", default="")
BITRIX24_CONTRACT_FIELD_CABINS = env("BITRIX24_CONTRACT_FIELD_CABINS", default="")
BITRIX24_CONTRACT_FIELD_CLIENTS = env("BITRIX24_CONTRACT_FIELD_CLIENTS", default="")
BITRIX24_CONTRACT_FIELD_CLIENT_COUNTRY = env("BITRIX24_CONTRACT_FIELD_CLIENT_COUNTRY", default="")
BITRIX24_CONTRACT_FIELD_TRIP_START = env("BITRIX24_CONTRACT_FIELD_TRIP_START", default="")
BITRIX24_CONTRACT_FIELD_TRIP_END = env("BITRIX24_CONTRACT_FIELD_TRIP_END", default="")
BITRIX24_CONTRACT_FIELD_CRUISE_TYPE = env("BITRIX24_CONTRACT_FIELD_CRUISE_TYPE", default="")
BITRIX24_CONTRACT_FIELD_PAYMENT = env("BITRIX24_CONTRACT_FIELD_PAYMENT", default="")
BITRIX24_CONTRACT_FIELD_EXTRA = env("BITRIX24_CONTRACT_FIELD_EXTRA", default="")
BITRIX24_CONTRACT_FIELD_TAX = env("BITRIX24_CONTRACT_FIELD_TAX", default="")
BITRIX24_CONTRACT_FILE_FIELD_ID = env("BITRIX24_CONTRACT_FILE_FIELD_ID", default="")
# Contact fields
BITRIX24_CONTRACT_FIELD_PASSPORT_NUMBER = env("BITRIX24_CONTRACT_FIELD_PASSPORT_NUMBER", default="")
BITRIX24_CONTRACT_FIELD_PASSPORT_DATE = env("BITRIX24_CONTRACT_FIELD_PASSPORT_DATE", default="")
BITRIX24_CONTRACT_FIELD_PASSPORT_ISSUED = env("BITRIX24_CONTRACT_FIELD_PASSPORT_ISSUED", default="")
BITRIX24_CONTRACT_FIELD_PASSPORT_BPLACE = env("BITRIX24_CONTRACT_FIELD_PASSPORT_BPLACE", default="")
BITRIX24_CONTRACT_FIELD_BIRTHDATE = env("BITRIX24_CONTRACT_FIELD_BIRTHDATE", default="")
```

---

### Шаг 7: Тесты

**Файл:** `apps/integrations/tests/test_bitrix24_contract.py` (новый)

**Что протестировать:**
1. `Bitrix24ContractService.build_context_from_deal()` — маппинг полей
2. View `bitrix24_contract_form` — рендеринг шаблона
3. View `bitrix24_contract_generate` — генерация PDF + загрузка в Bitrix24
4. Интеграция: `ContractRenderer.build_context_from_data()` → PDF

---

### Шаг 8: Обновление документации

**Файлы:**
- `docs/DECISIONS.md` — добавить DEC-008: генерация договоров в Bitrix24
- `docs/TASK_STATE.md` — обновить статус задачи
- `docs/DEV_LOG.md` — записать результат
- `docs/PROJECT_OVERVIEW.md` — добавить описание нового функционала

---

## Порядок выполнения

```
Шаг 1 (рефакторинг ContractRenderer)
    ↓
Шаг 2 (маппинг полей Bitrix24)
    ↓
Шаг 3 (views)  ← параллельно →  Шаг 4 (шаблон)
    ↓
Шаг 5 (placement)
    ↓
Шаг 6 (настройки)
    ↓
Шаг 7 (тесты)
    ↓
Шаг 8 (документация)
```

## Файлы для изменения/создания

| Действие | Файл |
|---|---|
| Изменить | `apps/crm/services/contract_renderer.py` — выделить `build_context_from_data()` |
| Создать | `apps/integrations/services/bitrix24_contract_service.py` — маппинг полей |
| Изменить | `apps/integrations/views.py` — добавить 2 view |
| Создать | `templates/bitrix24/contract_form.html` — UI формы |
| Изменить | `config/urls.py` — маршруты |
| Изменить | `config/settings.py` — переменные окружения |
| Создать | `apps/integrations/tests/test_bitrix24_contract.py` — тесты |
