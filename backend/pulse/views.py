import logging

from django.core.cache import cache
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from . import snapshot

logger = logging.getLogger(__name__)

CACHE_SECONDS = 60

@require_GET
def pulse(request):
    data = cache.get("pulse")
    if data is None:
        try:
            data = snapshot.build()
            cache.set("pulse", data, CACHE_SECONDS)
            cache.set("pulse:last_good", data, None)
        except DatabaseError:
            logger.exception("Building pulse failed")
            data = cache.get("pulse:last_good")
            if data is None:
                return JsonResponse({"error": "unavailable"}, status=503)
            data = {**data, "stale": True}
    return JsonResponse(data)
