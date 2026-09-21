from rest_framework import serializers
from apps.chat.models import Chat
from rest_framework.permissions import IsAuthenticated

class ChatListSerializer(serializers.ListSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = Chat
        fields = ['title']
    # queryset = Chat.objects.all()  # Replace with your actual queryset
    # serializer_class = ChatSerializer  # Replace with your actual serializer

class ChatSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = Chat
        fields = ['id', 'owner', 'message']

