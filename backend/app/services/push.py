from __future__ import annotations

import json

import httpx

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def notify_push(token: str | None, title: str, body: str, data: dict | None = None) -> bool:
    if not settings.push_enabled or not token or not settings.fcm_server_key:
        logger.info("push_skipped", reason="disabled_or_missing_token")
        return False
    payload = {
        "to": token,
        "notification": {"title": title, "body": body},
        "data": data or {},
        "priority": "high",
    }
    try:
        response = httpx.post(
            "https://fcm.googleapis.com/fcm/send",
            headers={
                "Authorization": f"key={settings.fcm_server_key}",
                "Content-Type": "application/json",
            },
            content=json.dumps(payload),
            timeout=8.0,
        )
        ok = response.status_code < 300
        logger.info("push_sent", ok=ok, status=response.status_code)
        return ok
    except Exception as exc:
        logger.warning("push_failed", error=str(exc))
        return False
