"""URL của app ``chat`` (được include dưới tiền tố ``/chat/``)."""

from django.urls import path

from apps.chat.views import ChatAskView, ChatDetailView, ChatListCreateView

urlpatterns = [
    path("chats/", ChatListCreateView.as_view(), name="chat-list-view"),
    path("chats/<int:pk>/", ChatDetailView.as_view(), name="chat-detail-view"),
    path("chats/<int:pk>/ask/", ChatAskView.as_view(), name="chat-ask-view"),
]
