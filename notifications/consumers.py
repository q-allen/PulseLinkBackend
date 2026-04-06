"""
notifications/consumers.py
ws(s)://host/ws/notifications/
Pushes real-time notification events to the authenticated user.
"""
import json
import logging

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

logger = logging.getLogger(__name__)


def _cookie_dict(scope) -> dict:
    cookies = {}
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            for part in value.decode().split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
    return cookies


@sync_to_async
def _get_user(scope):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    token = _cookie_dict(scope).get("access_token")
    if not token:
        return None
    try:
        validated = UntypedToken(token)
        user_id = validated.payload.get("user_id")
        return User.objects.get(pk=user_id, is_active=True)
    except (InvalidToken, TokenError, User.DoesNotExist):
        return None


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = await _get_user(self.scope)
        if not user:
            await self.close(code=4001)
            return
        self.group_name = f"notifications_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass  # read-only channel

    async def notify(self, event: dict):
        await self.send(text_data=json.dumps({
            "type":       "notification",
            "id":         event["id"],
            "notif_type": event["notif_type"],
            "title":      event["title"],
            "message":    event["message"],
            "data":       event.get("data", {}),
            "created_at": event["created_at"],
        }))
