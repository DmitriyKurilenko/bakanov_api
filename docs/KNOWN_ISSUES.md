# Known Issues

Известные баги и ограничения. Обновлять при обнаружении или закрытии.

## Формат записи

```
### KI-NNN: Краткое описание
- **Статус:** open | closed | wontfix
- **Обнаружено:** YYYY-MM-DD
- **Закрыто:** YYYY-MM-DD (если применимо)
- **Описание:** Что происходит и при каких условиях.
- **Обходной путь:** Если есть.
```

---

### KI-001: NameError в bitrix24_spam_lead_service.py
- **Статус:** closed
- **Обнаружено:** 2026-05-13
- **Закрыто:** 2026-05-13
- **Описание:** В `bitrix24_spam_lead_service.py` отсутствовал `import logging` и `logger = logging.getLogger(__name__)`. Из-за этого метод `_fetch_entity` падал с `NameError` при попытке логирования, но ошибка тихо глоталась `except Exception`, и метод возвращал пустой dict. Сервис считал, что сущность в Bitrix24 не найдена.
- **Обходной путь:** Добавлен импорт logging и logger.

### KI-002: ModuleNotFoundError django_redis в спам-флоу Bitrix24
- **Статус:** closed
- **Обнаружено:** 2026-05-15
- **Закрыто:** 2026-05-15
- **Описание:** Коммит `0ceba61` добавил `from django_redis import get_redis_connection` в `process_bitrix24_spam_lead_webhook`, но `django-redis` не входит в стек (нет в `requirements.txt`, не установлен, `CACHES` не настроен — Redis используется только как брокер Celery через пакет `redis`). Каждый вызов задачи падал с `ModuleNotFoundError`. Это и есть причина «сработал 1-2 раза (до коммита дедупликации) и перестал».
- **Обходной путь:** Дедуп переведён на штатный `redis` через `apps/integrations/services/redis_client.py` (DEC-009). `django-redis` не вводится.

### KI-003: Падают тесты фичи генерации договоров Bitrix24
- **Статус:** open
- **Обнаружено:** 2026-05-15
- **Описание:** 5 тестов в `test_bitrix24_contract.py` и `test_bitrix24_views.py` падают (`test_get_returns_405` → 200, `test_post_unknown_portal_returns_404`, `test_post_success_generates_contract`). Относятся к незавершённой задаче #8 (генерация договоров, in-progress), не к спам-флоу. DEV_LOG 2026-05-14 прямо отмечал, что тесты договоров не запускались. Не регрессия от правок спам-флоу — затронутые модули (`views.py`, contract service) не менялись.
- **Обходной путь:** Нет. Чинить в рамках задачи #8.
