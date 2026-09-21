from django.shortcuts import render
from rest_framework import generics

from apps.chat.models import Chat
from apps.chat.serializers import ChatSerializer

# Create your views here.
class ChatListView(generics.ListCreateAPIView):
    queryset = Chat.objects.all()  # Replace with your actual queryset
    serializer_class = ChatSerializer  # Replace with your actual serializer

    def get(self, *args, **kwargs):
        # Filter the queryset based on the authenticated user
        user = self.request.user
        return Chat.objects.filter(owner=user)

    def post(self, request, *args, **kwargs):
        # Filter the queryset based on the authenticated user
        user = self.request.user

        prompt = request.data.get('prompt')
        if prompt:
            pass


class ChatDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Chat.objects.all()  # Replace with your actual queryset
    serializer_class = ChatSerializer  # Replace with your actual serializer

    def get(self, id, *args, **kwargs):
        # Filter the queryset based on the authenticated user
        user = self.request.user
        q = Chat.objects.filter(id=id, owner=user)

        return q

    def post(self, id, request, *args, **kwargs):
        # Filter the queryset based on the authenticated user
        user = self.request.user
        q = Chat.objects.filter(id=id, owner=user)

        prompt = request.data.get('prompt')
        if prompt:
            pass

        return q




    