"""
backend/asgi.py

ASGI entrypoint — routes HTTP to Django and WebSocket to Channels.
Run with:  daphne backend.asgi:application
       or: uvicorn backend.asgi:application  (if uvicorn is installed)
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

# Django setup must happen before importing consumers / routing
import django
django.setup()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.conf import settings
from django.core.asgi import get_asgi_application

from chat.routing import websocket_urlpatterns
from appointments.consumers import AppointmentConsumer, DoctorQueueConsumer
from notifications.consumers import NotificationConsumer
from django.urls import re_path

all_websocket_urlpatterns = websocket_urlpatterns + [
    re_path(r"^ws/appointments/(?P<apt_id>\d+)/$", AppointmentConsumer.as_asgi()),
    re_path(r"^ws/queue/doctor/(?P<doctor_id>\d+)/$", DoctorQueueConsumer.as_asgi()),
    re_path(r"^ws/notifications/$", NotificationConsumer.as_asgi()),
]

_ws_app = AuthMiddlewareStack(URLRouter(all_websocket_urlpatterns))
# In DEBUG, allow any Origin to ease local dev across hostnames/ports.
# In production, restrict to ALLOWED_HOSTS.
if not settings.DEBUG:
    _ws_app = AllowedHostsOriginValidator(_ws_app)

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": _ws_app,
})
