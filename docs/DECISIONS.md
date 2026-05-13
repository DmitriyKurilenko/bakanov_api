# Architecture Decisions

Решения по архитектуре и поведению системы. Каждая запись — факт, а не предложение.
Если решение отменено — пометить `[ОТМЕНЕНО]` и указать причину.

---

## DEC-001: Стек технологий (2026-04-09)

**Контекст:** Зафиксировать стек, чтобы агенты и разработчики не добавляли зависимости без согласования.

**Решение:**
- Django 5.2 LTS, Python 3.13
- PostgreSQL (через psycopg 3)
- Redis (брокер Celery + кэш)
- Celery 5 + Beat + Flower
- django-ninja (API)
- WeasyPrint + ReportLab (генерация документов)
- DaisyUI + Tailwind CSS (фронт, подключены через CDN)
- Alpine.js (интерактивность фронта)
- Font Awesome (иконки)
- Docker / docker-compose (единственная среда разработки и деплоя)

**Последствия:** Любое расширение стека требует явного одобрения владельца проекта.

---

## DEC-002: Docker-only разработка (2026-04-09)

**Контекст:** Исключить расхождение окружений host ↔ контейнер.

**Решение:** Все команды выполняются через `docker compose exec` / `docker compose run --rm`. Никаких `pip install`, `brew install`, `npm install -g` на хосте.

**Последствия:** CSS-билды через `docker run --rm -v "$(pwd)":/app -w /app node:18-alpine sh -c "npm install && npx tailwindcss ..."`.

---

## DEC-003: Роли пользователей (2026-04-09)

**Контекст:** Система разграничения доступа.

**Решение:** Три роли: `manager`, `head` (РОП), `admin`. Доступ контролируется на уровне view/API.

**Последствия:** Расширение ролей возможно, но требует обновления всех проверок доступа.

---

## DEC-004: Интеграция с Битрикс24 (2026-04-09)

**Контекст:** Добавить поддержку Bitrix24 CRM наравне с AmoCRM.

**Решение:**
- Outgoing webhooks: `Bitrix24Client` (dataclass + factory `from_settings()`) вызывает REST API Bitrix24 через webhook URL с токеном.
- Incoming webhooks: POST `/api/integrations/webhooks/bitrix24` принимает события CRM (lead/deal/contact add/update/delete), проверяет `BITRIX24_INBOUND_TOKEN`, диспатчит в Celery task.
- Конфигурация через env: `BITRIX24_WEBHOOK_URL`, `BITRIX24_INBOUND_TOKEN`, `BITRIX24_TIMEOUT`.
- Паттерн идентичен AmoCRM: service → task → API endpoint.

**Последствия:** Новые зависимости не добавлены. Используется только `requests` (уже в стеке).
