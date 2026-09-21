from django.urls import path
from .views import ChatListView, ChatDetailView

urlpatterns = [
    path('chats/', ChatListView.as_view(), name='chat-list-view'),
    path('chats/<uuid:id>/', ChatDetailView.as_view(), name='chat-detail-view'),
]