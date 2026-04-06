"""
chat/views.py

ConversationListView  GET/POST  /chat/
MessageListView       GET/POST  /chat/<conv_id>/messages/
MarkMessageReadView   POST      /chat/messages/<msg_id>/read/

NowServing alignment:
- GET /chat/<conv_id>/messages/ auto-marks all unread as read (REST polling pattern)
  AND broadcasts chat.read_all over WS so the sender's ✓ → ✓✓ immediately.
- POST /chat/messages/<msg_id>/read/ for explicit single-message read receipt
  (used by IntersectionObserver in frontend).
- Message list limited to 50 most recent; older messages paginated via ?before=<id>.
- File uploads broadcast over WS so file messages appear in real-time.
"""

import json
import logging
import os

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone
from rest_framework import status
import redis

logger = logging.getLogger(__name__)
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer

PAGE_SIZE = 50  # NowServing loads 50 messages initially, paginates older ones


def _infer_type(file_obj, explicit_type: str) -> str:
    """Determine message type from explicit param or file MIME type."""
    if explicit_type and explicit_type != "text":
        return explicit_type
    if not file_obj:
        return "text"
    mime = getattr(file_obj, "content_type", "") or ""
    if mime.startswith("image/"):
        return "image"
    return "file"


def _to_ws_payload(event_type: str, payload: dict) -> dict | None:
    if event_type == "broadcast_message":
        message = payload.get("message") or {}
        return {"type": "chat.message", **message}
    if event_type == "broadcast_read":
        return {"type": "chat.read", **payload}
    if event_type == "broadcast_read_all":
        return {"type": "chat.read_all", **payload}
    return None


def _publish_redis(conv_id: int, payload: dict) -> None:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return
    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.publish(f"chat:{conv_id}", json.dumps({"conv_id": conv_id, "payload": payload}))
    except Exception as exc:
        logger.warning("Redis publish failed for conv %s: %s", conv_id, exc)


def _broadcast(conv_id: int, event_type: str, payload: dict):
    """
    Push an event to the conversation's WS channel group and Redis pubsub.
    Channel layer is kept for Django Channels; Redis enables FastAPI WS relay.
    """
    try:
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(
                f"chat_{conv_id}",
                {"type": event_type, **payload},
            )
    except (RuntimeError, OSError, AttributeError, ValueError) as exc:
        logger.warning("_broadcast failed for conv %s event %s: %s", conv_id, event_type, exc)

    ws_payload = _to_ws_payload(event_type, payload)
    if ws_payload:
        _publish_redis(conv_id, ws_payload)


class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == "patient":
            qs = Conversation.objects.filter(patient=user)
        elif user.role == "doctor":
            qs = Conversation.objects.filter(doctor=user)
        else:
            qs = Conversation.objects.all()

        qs = qs.select_related("patient", "doctor").prefetch_related("messages")
        serializer = ConversationSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        """
        Start or retrieve a 1:1 conversation between a patient and a doctor.

        NowServing alignment: both patients AND doctors can initiate a conversation.
        - Doctor initiates → supplies patient_id; the caller is the doctor.
        - Patient initiates → supplies doctor_id; the caller is the patient.
        - If a conversation already exists between the pair, return it (no duplicates).
        - unique_together on (patient, doctor) in the model enforces the 1:1 constraint.

        Returns 201 on creation, 200 if the conversation already existed.
        """
        role = request.user.role

        if role == "patient":
            # Patient-initiated: caller is the patient, must supply doctor_id
            doctor_id = request.data.get("doctor_id")
            if not doctor_id:
                return Response({"detail": "doctor_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                doctor = User.objects.get(pk=doctor_id, role="doctor", is_active=True)
            except User.DoesNotExist:
                return Response({"detail": "Doctor not found."}, status=status.HTTP_404_NOT_FOUND)
            patient = request.user

        elif role == "doctor":
            # Doctor-initiated: caller is the doctor, must supply patient_id
            patient_id = request.data.get("patient_id")
            if not patient_id:
                return Response({"detail": "patient_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                patient = User.objects.get(pk=patient_id, role="patient", is_active=True)
            except User.DoesNotExist:
                return Response({"detail": "Patient not found."}, status=status.HTTP_404_NOT_FOUND)
            doctor = request.user

        else:
            # Admin / staff: must supply both IDs explicitly
            doctor_id  = request.data.get("doctor_id")
            patient_id = request.data.get("patient_id")
            if not doctor_id or not patient_id:
                return Response(
                    {"detail": "doctor_id and patient_id are required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                doctor  = User.objects.get(pk=doctor_id,  role="doctor",  is_active=True)
                patient = User.objects.get(pk=patient_id, role="patient", is_active=True)
            except User.DoesNotExist:
                return Response({"detail": "Doctor or patient not found."}, status=status.HTTP_404_NOT_FOUND)

        conv, created = Conversation.objects.get_or_create(patient=patient, doctor=doctor)
        http_status   = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            ConversationSerializer(conv, context={"request": request}).data,
            status=http_status,
        )


class MessageListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def _get_conversation(self, conv_id, user):
        """Return conversation only if user is a participant (or staff)."""
        try:
            conv = Conversation.objects.select_related("patient", "doctor").get(pk=conv_id)
        except Conversation.DoesNotExist:
            return None
        if user.is_staff or user in (conv.patient, conv.doctor):
            return conv
        return None

    def get(self, request, conv_id):
        """
        Fetch messages in a conversation (50 most recent, paginate older via ?before=<id>).
        Auto-marks the other party's messages as read and broadcasts chat.read_all
        so the sender's ✓ → ✓✓ in real-time.
        """
        conv = self._get_conversation(conv_id, request.user)
        if not conv:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = conv.messages.select_related("sender").order_by("-timestamp")

        # Pagination: ?before=<message_id> for loading older messages
        before_id = request.query_params.get("before")
        if before_id:
            try:
                qs = qs.filter(pk__lt=int(before_id))
            except (ValueError, TypeError):
                pass

        messages = list(reversed(qs[:PAGE_SIZE]))

        # Auto-mark unread messages from the other party as read
        now     = timezone.now()
        updated = (
            conv.messages
            .exclude(sender=request.user)
            .filter(is_read=False)
            .update(is_read=True, read_at=now)
        )

        # Broadcast read_all over WS so sender's ✓ → ✓✓ immediately
        if updated > 0:
            _broadcast(
                conv.pk,
                "broadcast_read_all",
                {
                    "reader_id":       request.user.pk,
                    "conversation_id": conv.pk,
                },
            )

        return Response(
            MessageSerializer(messages, many=True, context={"request": request}).data
        )

    def post(self, request, conv_id):
        """
        Send a message — supports JSON (text) and multipart (file upload).
        File messages are broadcast over WS so they appear in real-time.
        """
        conv = self._get_conversation(conv_id, request.user)
        if not conv:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        content       = request.data.get("content", "").strip()
        explicit_type = request.data.get("type", "text")
        file_obj      = request.FILES.get("file")

        if not content and not file_obj:
            return Response(
                {"detail": "content or file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        msg_type  = _infer_type(file_obj, explicit_type)
        file_name = file_obj.name if file_obj else ""
        file_size = file_obj.size if file_obj else None

        msg = Message.objects.create(
            conversation=conv,
            sender=request.user,
            content=content,
            type=msg_type,
            file=file_obj,
            file_name=file_name,
            file_size=file_size,
        )

        Conversation.objects.filter(pk=conv.pk).update(updated_at=msg.timestamp)

        serialized = MessageSerializer(msg, context={"request": request}).data
        safe_data  = json.loads(json.dumps(serialized, default=str))

        # Broadcast file message over WS (text messages go via WS directly)
        _broadcast(conv.pk, "broadcast_message", {"message": safe_data})

        # Push notification for the other party
        try:
            from notifications.tasks import send_new_message_notification
            other_id = (
                conv.doctor_id if request.user.pk == conv.patient_id else conv.patient_id
            )
            send_new_message_notification.delay(
                message_id=msg.pk,
                recipient_id=other_id,
            )
        except ImportError as exc:
            logger.warning("Notification task not available for message %s: %s", msg.pk, exc)
        except OSError as exc:
            logger.warning("Notification broker unreachable for message %s: %s", msg.pk, exc)

        return Response(safe_data, status=status.HTTP_201_CREATED)


class MarkMessageReadView(APIView):
    """
    POST /chat/messages/<msg_id>/read/

    Explicit single-message read receipt endpoint.
    Called by the frontend IntersectionObserver when a message scrolls into view.
    Broadcasts chat.read over WS so the sender's ✓ → ✓✓ for that message.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, msg_id):
        try:
            msg = Message.objects.select_related("conversation__patient", "conversation__doctor").get(pk=msg_id)
        except Message.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        conv = msg.conversation
        # Only the receiver can mark a message as read
        if request.user not in (conv.patient, conv.doctor):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        if msg.sender_id == request.user.pk:
            return Response({"detail": "Cannot mark your own message as read."}, status=status.HTTP_400_BAD_REQUEST)

        if not msg.is_read:
            now      = timezone.now()
            msg.is_read = True
            msg.read_at = now
            msg.save(update_fields=["is_read", "read_at"])

            # Broadcast single read receipt over WS
            _broadcast(
                conv.pk,
                "broadcast_read",
                {
                    "reader_id":       request.user.pk,
                    "message_id":      msg.pk,
                    "read_at":         now.isoformat(),
                    "conversation_id": conv.pk,
                },
            )

        return Response({"id": msg.pk, "is_read": True, "read_at": msg.read_at})
