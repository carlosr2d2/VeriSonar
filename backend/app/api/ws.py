from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.config import settings
from app.core.logging import get_logger
from app.core.metrics import ACTIVE_STREAMS
from app.database import SessionLocal
from app.models import User

logger = get_logger(__name__)
router = APIRouter(tags=["tiempo-real"])


def _user_from_token(token: str | None) -> User | None:
    if not token:
        return None
    db = SessionLocal()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return db.get(User, payload.get("sub"))
    except JWTError:
        return None
    finally:
        db.close()


class StreamHub:
    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}

    async def register(self, session_id: str, ws: WebSocket) -> None:
        self.connections[session_id] = ws
        ACTIVE_STREAMS.inc()

    async def drop(self, session_id: str) -> None:
        self.connections.pop(session_id, None)
        ACTIVE_STREAMS.dec()


hub = StreamHub()


@router.websocket("/ws/analyze/{session_id}")
async def analyze_stream(websocket: WebSocket, session_id: str) -> None:
    """Canal de audio en tiempo real (fase 2 / modo online).

    Protocolo JSON:
      {"type": "hello", "token": "<jwt>"}
      {"type": "chunk", "seq": 1} + frame binario
      {"type": "end"}
    """
    await websocket.accept()
    if settings.is_offline:
        await websocket.send_json(
            {
                "type": "mode",
                "processing_mode": "offline",
                "message": (
                    "El modo online (WebRTC / streaming) está diseñado para la fase 2. "
                    "En esta fase suba un archivo a POST /analyze."
                ),
            }
        )

    token = websocket.query_params.get("token")
    user = _user_from_token(token)
    buffer = bytearray()
    try:
        await hub.register(session_id, websocket)
        while True:
            message = await websocket.receive()
            if message.get("text"):
                payload = json.loads(message["text"])
                kind = payload.get("type")
                if kind == "hello":
                    user = _user_from_token(payload.get("token"))
                    if not user:
                        await websocket.send_json({"type": "error", "detail": "No autorizado"})
                        await websocket.close(code=4401)
                        return
                    await websocket.send_json(
                        {
                            "type": "ready",
                            "session_id": session_id,
                            "processing_mode": settings.processing_mode,
                            "max_concurrent_hint": 50,
                        }
                    )
                elif kind == "end":
                    await websocket.send_json(
                        {
                            "type": "partial",
                            "bytes_received": len(buffer),
                            "message": "Chunk final recibido. El análisis batch sigue siendo la vía de producción en fase 1.",
                        }
                    )
                elif kind == "chunk":
                    await websocket.send_json({"type": "ack", "seq": payload.get("seq")})
            elif message.get("bytes"):
                buffer.extend(message["bytes"])
                if len(buffer) > 8_000_000:
                    await websocket.send_json({"type": "error", "detail": "Buffer excesivo"})
                    break
    except WebSocketDisconnect:
        logger.info("ws_disconnected", session_id=session_id)
    finally:
        await hub.drop(session_id)


async def notify_result(user: User, report_id: str) -> None:
    """Empuja el resultado a un socket abierto si existe."""
    ws = hub.connections.get(str(getattr(user, "id", "")))
    if not ws:
        return
    try:
        await ws.send_json({"type": "report_ready", "report_id": report_id})
    except Exception:
        logger.info("ws_notify_failed", report_id=report_id)
