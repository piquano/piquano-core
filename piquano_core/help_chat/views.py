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


@csrf_exempt
@require_POST
@login_required
def bug_report_proxy(request):
    """Proxy: Bug-Report aus dem Help-Chat-Widget an das Support-Backend weiterleiten."""
    token = os.getenv("HELP_CHAT_TOKEN", "")
    app_key = os.getenv("HELP_CHAT_APP_KEY", "")
    support_url = os.getenv("SUPPORT_BUG_API_URL", "")

    if not token or not support_url:
        return JsonResponse(
            {"error": "Bug-Report ist nicht konfiguriert."},
            status=503,
        )

    # FormData weiterleiten — Felder + Dateien + User-Infos ergänzen
    post_data = {
        "title": request.POST.get("title", ""),
        "url": request.POST.get("url", ""),
        "expected": request.POST.get("expected", ""),
        "actual": request.POST.get("actual", ""),
        "requester_email": request.user.email,
        "requester_name": request.user.get_full_name() or request.user.username,
    }

    # Meta-Daten vom Frontend + App-Key ergänzen
    meta_raw = request.POST.get("meta") or "{}"
    try:
        meta = json.loads(meta_raw)
    except (json.JSONDecodeError, ValueError):
        meta = {}
    meta["app"] = app_key
    post_data["meta"] = json.dumps(meta)

    # Dateien als Liste von Tuples für requests
    files_list = []
    for f in request.FILES.getlist("files"):
        files_list.append(("files", (f.name, f, f.content_type or "application/octet-stream")))

    try:
        resp = http_requests.post(
            support_url,
            data=post_data,
            files=files_list if files_list else None,
            headers={
                "X-Help-Chat-Token": token,
                "X-Forwarded-Proto": "https",
            },
            timeout=30,
        )
        return JsonResponse(resp.json(), status=resp.status_code)
    except http_requests.Timeout:
        return JsonResponse(
            {"error": "Die Übermittlung hat zu lange gedauert. Bitte versuch es nochmal."},
            status=504,
        )
    except Exception:
        logger.exception("Bug-Report Proxy Fehler")
        return JsonResponse(
            {"error": "Verbindung zum Support-Service fehlgeschlagen."},
            status=502,
        )
