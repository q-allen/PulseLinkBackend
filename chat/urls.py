from django.urls import path
from .views import ConversationListView, MessageListView, MarkMessageReadView

urlpatterns = [
    path("",                                ConversationListView.as_view(), name="conversation-list"),
    path("<int:conv_id>/messages/",         MessageListView.as_view(),      name="message-list"),
    path("messages/<int:msg_id>/read/",     MarkMessageReadView.as_view(),  name="message-mark-read"),
]
