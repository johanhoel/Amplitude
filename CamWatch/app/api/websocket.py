"""WebSocket connection manager for real-time event broadcasting."""
import json
import asyncio
from typing import Set
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.subscribers: dict = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        for channel in list(self.subscribers.keys()):
            if channel not in self.subscribers:
                self.subscribers[channel] = set()
            self.subscribers[channel].add(websocket)

    async def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        for channel in list(self.subscribers.keys()):
            self.subscribers[channel].discard(websocket)
            if not self.subscribers[channel]:
                del self.subscribers[channel]

    async def subscribe(self, websocket: WebSocket, channel: str):
        if channel not in self.subscribers:
            self.subscribers[channel] = set()
        self.subscribers[channel].add(websocket)

    async def unsubscribe(self, websocket: WebSocket, channel: str):
        if channel in self.subscribers:
            self.subscribers[channel].discard(websocket)
            if not self.subscribers[channel]:
                del self.subscribers[channel]

    async def broadcast(self, event_type: str, data: dict = None, channels: list = None):
        message = json.dumps({"type": event_type, "data": data or {}, "ts": asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0})
        targets = set(self.active_connections)
        if channels:
            for ch in channels:
                if ch in self.subscribers:
                    targets.update(self.subscribers[ch])
        disconnected = []
        for conn in targets:
            try:
                await conn.send_text(message)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            await self.disconnect(conn)

    async def handle_message(self, websocket: WebSocket, message: dict):
        msg_type = message.get("type", "")
        if msg_type == "subscribe":
            channel = message.get("channel", "all")
            await self.subscribe(websocket, channel)
        elif msg_type == "unsubscribe":
            channel = message.get("channel", "all")
            await self.unsubscribe(websocket, channel)
        elif msg_type == "ping":
            try:
                await websocket.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass


websocket_manager = WebSocketManager()
