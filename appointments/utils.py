"""
appointments/utils.py

Jitsi Meet room helpers.
Uses the public Jitsi Meet instance (meet.jit.si) by default.
Set JITSI_HOST in .env to use a self-hosted instance.
"""

import uuid
from django.conf import settings

JITSI_HOST = getattr(settings, "JITSI_HOST", "https://meet.jit.si")


def create_jitsi_room(prefix: str = "careconnect") -> tuple[str, str]:
    """
    Generate a unique Jitsi room.
    Returns (room_id, video_link).

    room_id   — stored on Appointment.video_room_id
    video_link — full URL for iframe embed / direct join
    """
    room_id = f"{prefix}-{uuid.uuid4().hex[:16]}"
    video_link = f"{JITSI_HOST}/{room_id}"
    return room_id, video_link


def jitsi_iframe_html(room_id: str, width: str = "100%", height: str = "600px") -> str:
    """
    Return an HTML iframe snippet for embedding Jitsi in a web page.
    Frontend can use this directly or construct its own embed.
    """
    url = f"{JITSI_HOST}/{room_id}"
    return (
        f'<iframe src="{url}" '
        f'width="{width}" height="{height}" '
        f'allow="camera; microphone; fullscreen; display-capture" '
        f'style="border:0;"></iframe>'
    )
