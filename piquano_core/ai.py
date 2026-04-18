"""Rate-limit and usage logging for Anthropic API calls.

Usage in views:
    from piquano_core.ai import ai_rate_limit

    @login_required
    @ai_rate_limit          # 10 requests/min per user
    def my_ai_view(request):
        ...

    @login_required
    @ai_rate_limit(limit=5) # custom limit
    def expensive_view(request):
        ...
"""

import functools
import logging
import time

from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger("piquano.ai")

# Default: 10 AI requests per minute per user
DEFAULT_LIMIT = 10
DEFAULT_WINDOW = 60  # seconds


def ai_rate_limit(_func=None, *, limit=DEFAULT_LIMIT, window=DEFAULT_WINDOW):
    """Decorator that rate-limits AI endpoint calls per authenticated user.

    Returns 429 if the user exceeds `limit` requests within `window` seconds.
    Also logs every AI call for usage tracking.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            user_id = getattr(request.user, "pk", "anon")
            cache_key = f"ai_rl_{func.__module__}.{func.__name__}_{user_id}"

            hits = cache.get(cache_key, 0)
            if hits >= limit:
                logger.warning(
                    "AI rate-limit erreicht: user=%s endpoint=%s hits=%d",
                    user_id,
                    func.__name__,
                    hits,
                )
                return JsonResponse(
                    {"error": f"Rate-Limit erreicht ({limit} Aufrufe pro Minute). Bitte warten."},
                    status=429,
                )

            cache.set(cache_key, hits + 1, window)

            start = time.monotonic()
            response = func(request, *args, **kwargs)
            duration = time.monotonic() - start

            logger.info(
                "AI call: user=%s endpoint=%s duration=%.1fs status=%s",
                user_id,
                func.__name__,
                duration,
                getattr(response, "status_code", "?"),
            )

            return response

        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator
