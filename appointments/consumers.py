"""
appointments/consumers.py

AppointmentConsumer  — ws(s)://host/ws/appointments/<appointment_id>/
DoctorQueueConsumer  — ws(s)://host/ws/queue/doctor/<doctor_id>/

Outbound event types (server → client, JSON):
  { "type": "video.started",        "appointment_id", "room_name", "password",
                                    "jitsi_domain", "video_room_url" }
  { "type": "status.changed",       "appointment_id", "status" }
  { "type": "consultation.ended",   "appointment_id", "duration_seconds", "duration_minutes" }
  { "type": "document.shared",      "appointment_id", "doc_type", "document_id",
                                    "title", "summary", "created_at" }
  { "type": "queue.update",         "appointment_id", "queue_position",
                                    "estimated_wait_minutes", "now_serving_id" }

NowServing alignment:
  - video.started   → patient browser auto-shows "Join Now" / loads Jitsi iframe
  - consultation.ended → patient Jitsi iframe closes, redirect to review page
  - document.shared → patient sees new prescription/cert/lab in real-time
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
    for header_name, header_value in scope.get("headers", []):
        if header_name == b"cookie":
            for part in header_value.decode().split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
    return cookies


def _bearer_token(scope) -> str | None:
    """Extract Bearer token from Authorization header (for non-cookie clients)."""
    for header_name, header_value in scope.get("headers", []):
        if header_name == b"authorization":
            val = header_value.decode()
            if val.startswith("Bearer "):
                return val[7:]
    return None


@sync_to_async
def _get_user_from_scope(scope):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Try cookie first (browser WebSocket), then Authorization header (mobile/test)
    token = _cookie_dict(scope).get("access_token") or _bearer_token(scope)
    if not token:
        return None
    try:
        validated = UntypedToken(token)
        user_id = validated.payload.get("user_id")
        return User.objects.get(pk=user_id, is_active=True)
    except (InvalidToken, TokenError, User.DoesNotExist):
        return None


@sync_to_async
def _get_appointment(apt_id, user):
    from appointments.models import Appointment
    try:
        apt = Appointment.objects.select_related("patient", "doctor").get(pk=apt_id)
    except Appointment.DoesNotExist:
        return None
    # Only the patient, doctor, or staff may subscribe
    if user in (apt.patient, apt.doctor) or user.is_staff:
        return apt
    return None


class AppointmentConsumer(AsyncWebsocketConsumer):
    """
    Per-appointment WebSocket channel.
    Both doctor and patient connect here to receive real-time events.
    Clients are read-only — all writes go through REST endpoints.
    """

    async def connect(self):
        self.apt_id     = self.scope["url_route"]["kwargs"]["apt_id"]
        self.group_name = f"appointment_{self.apt_id}"
        self.user       = None

        user = await _get_user_from_scope(self.scope)
        if not user:
            await self.close(code=4001)   # Unauthorized
            return

        apt = await _get_appointment(self.apt_id, user)
        if not apt:
            await self.close(code=4003)   # Forbidden / not found
            return

        self.user = user
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.debug("WS connected: user=%s apt=%s", user.pk, self.apt_id)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Clients are read-only on this socket; no inbound events processed.
        pass

    # ── Group event handlers ──────────────────────────────────────────────────
    # Each method name maps to the "type" field in the channel layer message,
    # with dots replaced by underscores (Django Channels convention).

    async def video_started(self, event: dict):
        """
        Fired by start_video_consultation view.
        Patient browser receives this and shows the Jitsi iframe / "Join Now" button.
        """
        await self.send(text_data=json.dumps({
            "type":           "video.started",
            "appointment_id": event["appointment_id"],
            "room_name":      event["room_name"],
            "password":       event["password"],
            "jitsi_domain":   event["jitsi_domain"],
            "video_room_url": event["video_room_url"],
        }))

    async def status_changed(self, event: dict):
        """Generic status transition (confirmed, in_progress, completed, cancelled)."""
        await self.send(text_data=json.dumps({
            "type":           "status.changed",
            "appointment_id": event["appointment_id"],
            "status":         event["status"],
        }))

    async def consultation_ended(self, event: dict):
        """
        Fired by complete view.
        Patient browser receives this → Jitsi iframe unmounts → redirect to review page.
        NowServing pattern: doctor ends the call, patient is gracefully ejected.
        """
        await self.send(text_data=json.dumps({
            "type":             "consultation.ended",
            "appointment_id":   event["appointment_id"],
            "duration_seconds": event.get("duration_seconds", 0),
            "duration_minutes": event.get("duration_minutes", 0),
        }))

    async def document_shared(self, event: dict):
        """
        Fired by share_document view.
        Patient sees new prescription / certificate / lab request in real-time.
        """
        await self.send(text_data=json.dumps({
            "type":           "document.shared",
            "appointment_id": event["appointment_id"],
            "doc_type":       event["doc_type"],
            "document_id":    event["document_id"],
            "title":          event.get("title"),
            "summary":        event.get("summary"),
            "created_at":     event.get("created_at"),
        }))

    async def queue_update(self, event: dict):
        """Per-appointment queue position update."""
        await self.send(text_data=json.dumps({
            "type":                   "queue.update",
            "appointment_id":         event["appointment_id"],
            "queue_position":         event.get("queue_position"),
            "estimated_wait_minutes": event.get("estimated_wait_minutes"),
            "now_serving_id":         event.get("now_serving_id"),
        }))


class DoctorQueueConsumer(AsyncWebsocketConsumer):
    """
    Doctor queue dashboard WebSocket.
    Connection URL: ws(s)://host/ws/queue/doctor/<doctor_id>/
    Receives full queue state whenever any appointment status changes.
    """

    async def connect(self):
        self.doctor_id  = self.scope["url_route"]["kwargs"]["doctor_id"]
        self.group_name = f"queue_doctor_{self.doctor_id}"

        user = await _get_user_from_scope(self.scope)
        if not user:
            await self.close(code=4001)
            return
        if user.role != "doctor" and not user.is_staff:
            await self.close(code=4003)
            return
        if str(user.id) != str(self.doctor_id) and not user.is_staff:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass

    async def queue_update(self, event: dict):
        """Broadcast full queue state to doctor dashboard."""
        await self.send(text_data=json.dumps({
            "type":        "queue.update",
            "doctor_id":   event.get("doctor_id"),
            "date":        event.get("date"),
            "now_serving": event.get("now_serving"),
            "waiting":     event.get("waiting", []),
        }))
