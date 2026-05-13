# Development Log

Хронологический журнал изменений. Новые записи — сверху.

## Формат записи

```
### YYYY-MM-DD — Краткое описание
- **Файлы:** список изменённых файлов
- **Что сделано:** описание
- **Валидация:** manage.py check, тесты, HTTP-проверка
- **Риски:** что может сломаться
```

---

### 2026-04-09 — Интеграция с Битрикс24

- **Файлы:**
  - `apps/integrations/services/bitrix24_service.py` — клиент REST API (outgoing webhooks)
  - `apps/integrations/services/bitrix24_webhook_handler.py` — обработчик входящих событий
  - `apps/integrations/api.py` — endpoint `POST /api/integrations/webhooks/bitrix24`
  - `apps/integrations/schemas.py` — схемы ответов
  - `apps/integrations/tasks.py` — Celery task `process_bitrix24_webhook`
  - `config/settings.py` — env-переменные `BITRIX24_*`
  - `.env.dev.example`, `.env.example`, `.env.prod.example` — шаблоны
  - `apps/integrations/tests/test_bitrix24_service.py` — 13 тестов клиента
  - `apps/integrations/tests/test_bitrix24_webhook_api.py` — 6 тестов API
  - `apps/integrations/tests/test_bitrix24_webhook_handler.py` — 15 тестов обработчика
- **Что сделано:** Полная интеграция с Bitrix24: outgoing (CRUD leads/deals/contacts/companies с пагинацией) + incoming (webhook с валидацией токена, диспатч в Celery).
- **Валидация:** `manage.py check` — OK. 66/66 тестов проходят. Нет регрессий.
- **Риски:** Нет. Новые зависимости не добавлены.

### 2026-04-09 — Создание структуры документации

- **Файлы:** docs/TASK_STATE.md, docs/DECISIONS.md, docs/KNOWN_ISSUES.md, docs/DEV_LOG.md, docs/RELEASE_NOTES.md, docs/VERSIONING.md, AGENTS.MD
- **Что сделано:** Создана директория `docs/` со всеми файлами, на которые ссылается AGENTS.MD. Зафиксированы начальные решения по стеку и процессам.
- **Валидация:** Нет изменений кода — валидация не требуется.
- **Риски:** Нет.
