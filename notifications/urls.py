from django.urls import path
from .views import NotificationDeleteView, NotificationListView, NotificationMarkAllReadView, NotificationMarkReadView, NotificationUnreadCountView

urlpatterns = [
    path("",                   NotificationListView.as_view(),        name="notification-list"),
    path("unread-count",       NotificationUnreadCountView.as_view(), name="notification-unread-count"),
    path("mark-all-read",      NotificationMarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("<int:pk>/mark-read", NotificationMarkReadView.as_view(),    name="notification-mark-read"),
    path("<int:pk>/",          NotificationDeleteView.as_view(),      name="notification-delete"),
]
