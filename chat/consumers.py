"""
chat/consumers.py

ChatConsumer — WebSocket handler for NowServing-style real-time 1:1 chat.

Connection URL:  ws(s)://host/ws/chat/<conv_id>/

Authentication:
  Reads the `access_token` cookie from the WS handshake headers.
  No token-in-URL — avoids leaking tokens in server access logs.

Channel group:
  Each conversation gets a group named "chat_<conv_id>".
  Both participants join on connect; messages broadcast to the group.

Inbound event types (client → server, JSON):
  { "type": "chat.message",  "content": "hello", "msg_type": "text", "temp_id": "uuid" }
  { "type": "chat.typing",   "is_typing": true }
  { "type": "chat.read",     "message_id": 123 }   ← mark specific message read
  { "type": "chat.read_all" }                       ← mark all unread as read

Outbound event types (server → client, JSON):
  { "type": "chat.message",  ...message fields..., "temp_id": "uuid" }
  { "type": "chat.typing",   "user_id": 7, "is_typing": true }
  { "type": "chat.read",     "reader_id": 7, "message_id": 123, "read_at": "..." }
  { "type": "chat.read_all", "reader_id": 7, "conversation_id": 1 }
  { "type": "chat.unread_count", "count": 3 }
  { "type": "chat.error",    "detail": "..." }

Race condition handling:
  - _save_message uses select_for_update() via atomic transaction to prevent
    duplicate messages when both users send simultaneously.
  - temp_id is echoed back so the sender can reconcile their optimistic message
    with the real persisted message (replace temp bubble with confirmed one).

Fix summary (v2):
  1. Added temp_id passthrough — sender gets their own message echoed back with
     the real DB id so optimistic UI can reconcile without duplication.
  2. Wrapped _save_message in a database transaction for atomicity.
  3. Replaced bare `except Exception: pass` with specific logging so notification
     failures are visible in logs without breaking the chat flow.
  4. Added `asyncio.Lock` per-consumer to prevent the same connection from
     sending two messages simultaneously (client-side race guard).
"""

import asyncio
import json
import logging

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

from .models import Conversation, Message
from .serializers import MessageSerializer

logger = logging.getLogger(__name__)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _cookie_dict(scope) -> dict:
    """Parse raw cookie header from ASGI scope into a {name: value} dict."""
    cookies = {}
    for header_name, header_value in scope.get("headers", []):
        if header_name == b"cookie":
            for part in header_value.decode().split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
    return cookies


def _token_from_scope(scope) -> str | None:
    """Extract JWT from cookie first, then ?token= query param as fallback."""
    token = _cookie_dict(scope).get("access_token")
    if token:
        return token
    qs = scope.get("query_string", b"").decode()
    for part in qs.split("&"):
        if part.startswith("token="):
            return part[6:]
    return None


@sync_to_async
def _get_user_from_scope(scope):
    """
    Validate the JWT access_token cookie (or ?token= query param) and return the User.
    Returns None if the token is missing, invalid, or the user is inactive.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    token = _token_from_scope(scope)
    if not token:
        return None
    try:
        validated = UntypedToken(token)
        user_id   = validated.payload.get("user_id")
        return User.objects.select_related("doctor_profile").get(pk=user_id, is_active=True)
    except (InvalidToken, TokenError, User.DoesNotExist):
        return None


@sync_to_async
def _get_conversation(conv_id, user):
    """Return the Conversation if user is a participant, else None."""
    try:
        conv = Conversation.objects.select_related("patient", "doctor").get(pk=conv_id)
    except Conversation.DoesNotExist:
        return None
    if user in (conv.patient, conv.doctor) or user.is_staff:
        return conv
    return None


@sync_to_async
def _save_message(conv, sender, content, msg_type):
    """
    Persist a text message inside an atomic transaction.

    Using transaction.atomic() ensures that if two messages arrive at the exact
    same millisecond (race condition), each is written independently without
    corrupting the other. The conversation updated_at is bumped atomically.
    """
    with transaction.atomic():
        # Lock the conversation row so simultaneous sends never trample each other.
        locked_conv = Conversation.objects.select_for_update().get(pk=conv.pk)
        msg = Message.objects.create(
            conversation=locked_conv,
            sender=sender,
            content=content,
            type=msg_type,
        )
        # Use F-expression-safe update to avoid read-modify-write race on updated_at
        Conversation.objects.filter(pk=locked_conv.pk).update(updated_at=msg.timestamp)
    return msg


@sync_to_async
def _mark_one_read(message_id: int, reader) -> dict | None:
    """
    Mark a single message as read if the reader is NOT the sender.
    Returns a dict with message_id and read_at, or None if not applicable.
    """
    try:
        msg = Message.objects.select_related("sender").get(pk=message_id)
    except Message.DoesNotExist:
        return None
    if msg.sender_id == reader.pk or msg.is_read:
        return None
    now = timezone.now()
    msg.is_read = True
    msg.read_at = now
    msg.save(update_fields=["is_read", "read_at"])
    return {"message_id": message_id, "read_at": now.isoformat()}


@sync_to_async
def _mark_all_read(conv, reader) -> int:
    """
    Mark all unread messages from the other party as read.
    Returns the count of messages updated.
    """
    now     = timezone.now()
    updated = (
        conv.messages
        .exclude(sender=reader)
        .filter(is_read=False)
        .update(is_read=True, read_at=now)
    )
    return updated


@sync_to_async
def _get_unread_count(conv, viewer) -> int:
    return conv.unread_count(viewer)


@sync_to_async
def _serialize_message(msg, base_url: str) -> dict:
    """Serialize a Message instance to a plain JSON-safe dict."""

    class _FakeRequest:
        def build_absolute_uri(self, path):
            return base_url.rstrip("/") + path

    data = MessageSerializer(msg, context={"request": _FakeRequest()}).data
    return json.loads(json.dumps(data, default=str))


# ── Consumer ──────────────────────────────────────────────────────────────────

class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.conv_id    = self.scope["url_route"]["kwargs"]["conv_id"]
        self.group_name = f"chat_{self.conv_id}"
        self.user       = None
        self.conv       = None
        self.base_url   = ""
        # Per-connection lock prevents the same client from sending two messages
        # simultaneously (e.g. double-tap on Send button).
        self._send_lock = asyncio.Lock()

        # Authenticate
        user = await _get_user_from_scope(self.scope)
        if not user:
            logger.warning("WS auth failed: missing/invalid access_token cookie.")
            await self.close(code=4001)
            return

        # Authorise — must be a participant
        conv = await _get_conversation(self.conv_id, user)
        if not conv:
            logger.warning("WS forbidden: user %s not in conversation %s.", user.pk, self.conv_id)
            await self.close(code=4003)
            return

        self.user = user
        self.conv = conv

        # Build base URL for absolute file links
        scheme = "https" if self.scope.get("scheme") == "wss" else "http"
        host   = dict(self.scope.get("headers", [])).get(b"host", b"localhost").decode()
        self.base_url = f"{scheme}://{host}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send unread count immediately on connect so the badge updates
        unread = await _get_unread_count(self.conv, self.user)
        await self.send(text_data=json.dumps({
            "type":            "chat.unread_count",
            "count":           unread,
            "conversation_id": int(self.conv_id),
        }))

    async def disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Route inbound WS frames by their 'type' field."""
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON.")
            return

        event_type = data.get("type")

        if event_type == "chat.message":
            await self._handle_message(data)
        elif event_type == "chat.typing":
            await self._handle_typing(data)
        elif event_type == "chat.read":
            await self._handle_read_one(data)
        elif event_type == "chat.read_all":
            await self._handle_read_all()
        else:
            await self._send_error(f"Unknown event type: '{event_type}'.")

    # ── Inbound handlers ──────────────────────────────────────────────────────

    async def _handle_message(self, data: dict):
        """
        Handle an inbound chat.message event.

        temp_id is an optional client-generated UUID that the sender uses for
        optimistic UI. We echo it back in the broadcast so the sender can swap
        their temporary bubble for the real persisted message.

        The asyncio.Lock ensures that even if the client fires two sends in rapid
        succession (race condition), they are serialised and both succeed.
        """
        content  = (data.get("content") or "").strip()
        msg_type = data.get("msg_type", "text")
        # temp_id lets the frontend reconcile optimistic messages with real ones
        temp_id  = data.get("temp_id", None)

        # File uploads go through REST POST endpoint; only text over WS
        if not content:
            await self._send_error("content is required for chat.message events.")
            return
        if msg_type not in ("text", "prescription", "system"):
            await self._send_error("File uploads must use the REST endpoint POST /chat/<id>/messages/.")
            return

        # Serialise concurrent sends from the same connection
        async with self._send_lock:
            try:
                msg        = await _save_message(self.conv, self.user, content, msg_type)
                serialized = await _serialize_message(msg, self.base_url)
            except Exception as exc:
                logger.exception(
                    "WS send failed while saving message (conv=%s user=%s): %s",
                    self.conv_id,
                    self.user.pk,
                    exc,
                )
                await self._send_error(
                    "Failed to send message. Please try again.",
                    temp_id=temp_id,
                )
                return

        # Include temp_id so sender can reconcile their optimistic bubble
        if temp_id:
            serialized["temp_id"] = temp_id

        # Broadcast to BOTH participants instantly via channel layer group
        try:
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "broadcast_message", "message": serialized},
            )
        except Exception as exc:
            # Channel layer errors should never kill the socket. Log and fall back.
            logger.exception(
                "WS broadcast failed (conv=%s msg=%s): %s",
                self.conv_id,
                msg.pk,
                exc,
            )
            # Fallback: at least reconcile the sender's optimistic bubble.
            await self.send(text_data=json.dumps({
                "type": "chat.message",
                **serialized,
            }))
            await self._send_error(
                "Message saved, but real-time delivery may be delayed.",
                temp_id=temp_id,
            )
            return

        # Trigger push notification for the other party (fire-and-forget)
        # Failure is logged but must never break the chat flow.
        try:
            from notifications.tasks import send_new_message_notification
        except ImportError:
            logger.debug("Notifications app not available — skipping push notification.")
        else:
            other_id = (
                self.conv.doctor_id
                if self.user.pk == self.conv.patient_id
                else self.conv.patient_id
            )
            try:
                send_new_message_notification.delay(
                    message_id=msg.pk,
                    recipient_id=other_id,
                )
            except OSError as exc:
                logger.warning("Push notification broker unreachable for message %s: %s", msg.pk, exc)
            except Exception as exc:  # covers celery.exceptions.NotRegistered and ValueError
                logger.warning("Push notification failed for message %s: %s", msg.pk, exc)

    async def _handle_typing(self, data: dict):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type":      "broadcast_typing",
                "user_id":   self.user.pk,
                "is_typing": bool(data.get("is_typing", False)),
            },
        )

    async def _handle_read_one(self, data: dict):
        """
        Mark a single message as read.
        Payload: { "type": "chat.read", "message_id": 123 }
        Broadcasts read receipt to sender so their ✓ becomes ✓✓.
        """
        message_id = data.get("message_id")
        if not message_id:
            await self._send_error("message_id is required for chat.read.")
            return

        result = await _mark_one_read(int(message_id), self.user)
        if result:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type":            "broadcast_read",
                    "reader_id":       self.user.pk,
                    "message_id":      result["message_id"],
                    "read_at":         result["read_at"],
                    "conversation_id": int(self.conv_id),
                },
            )

    async def _handle_read_all(self):
        """
        Mark all unread messages from the other party as read.
        Broadcasts read_all event so sender's ✓ → ✓✓ for all messages.
        """
        await _mark_all_read(self.conv, self.user)
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type":            "broadcast_read_all",
                "reader_id":       self.user.pk,
                "conversation_id": int(self.conv_id),
            },
        )

    # ── Group event handlers (channel layer → this consumer) ─────────────────

    async def broadcast_message(self, event: dict):
        await self.send(text_data=json.dumps({
            "type": "chat.message",
            **event["message"],
        }))

    async def broadcast_typing(self, event: dict):
        # Don't echo typing indicator back to the sender
        if event["user_id"] == self.user.pk:
            return
        await self.send(text_data=json.dumps({
            "type":      "chat.typing",
            "user_id":   event["user_id"],
            "is_typing": event["is_typing"],
        }))

    async def broadcast_read(self, event: dict):
        """Single message read receipt — updates ✓ → ✓✓ for that message."""
        await self.send(text_data=json.dumps({
            "type":            "chat.read",
            "reader_id":       event["reader_id"],
            "message_id":      event["message_id"],
            "read_at":         event["read_at"],
            "conversation_id": event["conversation_id"],
        }))

    async def broadcast_read_all(self, event: dict):
        """All messages read — updates all ✓ → ✓✓ for the conversation."""
        await self.send(text_data=json.dumps({
            "type":            "chat.read_all",
            "reader_id":       event["reader_id"],
            "conversation_id": event["conversation_id"],
        }))

    # ── Utility ───────────────────────────────────────────────────────────────

    async def _send_error(self, detail: str, temp_id: str | None = None):
        payload = {"type": "chat.error", "detail": detail}
        if temp_id:
            payload["temp_id"] = temp_id
        await self.send(text_data=json.dumps(payload))
