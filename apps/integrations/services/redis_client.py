"""Shared Redis client built on the ``redis`` package (Celery broker dep).

The project does **not** ship ``django-redis``; the only Redis client
available is the ``redis`` library used as the Celery broker.  Use this
helper for ad-hoc Redis access (e.g. webhook dedup locks) instead of
``django_redis.get_redis_connection`` — that import raises
``ModuleNotFoundError`` at runtime.
"""

from __future__ import annotations

import redis
from django.conf import settings


def get_redis_client() -> "redis.Redis":
    """Return a Redis client bound to ``settings.REDIS_URL``.

    ``decode_responses=True`` keeps return values as ``str`` so callers
    don't have to deal with bytes for simple flag/lock values.
    """
    return redis.Redis.from_url(
        getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
