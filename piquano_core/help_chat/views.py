"""
Help-Chat Proxy — läuft in jeder App, leitet an den Hub weiter.

Jede App bindet diesen View per URL-Include ein. Das JS-Widget
ruft /help-chat/ask/ auf der eigenen Domain auf (kein CORS nötig).
Der Proxy ergänzt App-Key und Token und leitet an den Hub weiter.
"""

import json
import logging
import os

import requests as http_requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
@login_required
def help_chat_proxy(request):
    """Proxy: nimmt Frage entgegen, leitet an Hub weiter."""
    hub_url = os.getenv("HELP_CHAT_HUB_URL", "http://127.0.0.1:5005/api/v1/help-chat/")
    token = os.getenv("HELP_CHAT_TOKEN", "")
    app_key = os.getenv("HELP_CHAT_APP_KEY", "")

    if not token or not app_key:
        return JsonResponse(
            {"error": "Help-Chat ist nicht konfiguriert."},
            status=503,
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Ungültiges JSON."}, status=400)

    question = (data.get("question") or "").strip()
    if not question:
        return JsonResponse({"error": "Keine Frage gestellt."}, status=400)

    payload = {
        "app": app_key,
        "url": (data.get("url") or "").strip(),
        "title": (data.get("title") or "").strip(),
        "question": question,
    }

    try:
        resp = http_requests.post(
            hub_url,
            json=payload,
            headers={
                "X-Help-Chat-Token": token,
                "X-Forwarded-Proto": "https",
            },
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except http_requests.Timeout:
        return JsonResponse(
            {"error": "Die Antwort hat zu lange gedauert. Bitte versuch es nochmal."},
            status=504,
        )
    except Exception:
        logger.exception("Help-Chat Proxy Fehler")
        return JsonResponse(
            {"error": "Verbindung zum Hilfe-Service fehlgeschlagen."},
            status=502,
        )
