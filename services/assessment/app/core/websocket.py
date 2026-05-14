import json
import uuid
from datetime import datetime

from fastapi import WebSocket
import structlog

logger = structlog.get_logger()


class ConnectionManager:
    """
    Управляет WebSocket соединениями для realtime обновлений.

    Когда AI Worker завершает оценку, он публикует результат.
    Assessment Service получает его и пушит через WebSocket
    всем клиентам, подключённым к данной сессии.

    Структура: {session_id: [ws1, ws2, ...]}
    Несколько соединений на сессию — кандидат + интервьюер.
    """

    def __init__(self) -> None:
        # session_id -> список активных соединений
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: uuid.UUID) -> None:
        await websocket.accept()
        key = str(session_id)
        if key not in self._connections:
            self._connections[key] = []
        self._connections[key].append(websocket)
        logger.info("WebSocket connected", session_id=key, total=len(self._connections[key]))

    def disconnect(self, websocket: WebSocket, session_id: uuid.UUID) -> None:
        key = str(session_id)
        if key in self._connections:
            self._connections[key] = [
                ws for ws in self._connections[key] if ws != websocket
            ]
            if not self._connections[key]:
                del self._connections[key]
        logger.info("WebSocket disconnected", session_id=key)

    async def broadcast_to_session(self, session_id: uuid.UUID, message: dict) -> None:
        """
        Отправляем сообщение всем клиентам в сессии.
        Используется когда AI Worker завершил оценку.
        """
        key = str(session_id)
        if key not in self._connections:
            return

        dead_connections = []
        payload = json.dumps(message, default=str)

        for websocket in self._connections[key]:
            try:
                await websocket.send_text(payload)
            except Exception:
                dead_connections.append(websocket)

        # Чистим упавшие соединения
        for ws in dead_connections:
            self._connections[key].remove(ws)

    async def send_to_connection(self, websocket: WebSocket, message: dict) -> None:
        """Отправить сообщение конкретному соединению."""
        await websocket.send_text(json.dumps(message, default=str))

    def get_session_connections_count(self, session_id: uuid.UUID) -> int:
        return len(self._connections.get(str(session_id), []))


# Singleton
ws_manager = ConnectionManager()
