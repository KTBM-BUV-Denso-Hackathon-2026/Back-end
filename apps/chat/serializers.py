"""Serializer cho app ``chat``."""

from rest_framework import serializers

from apps.chat.models import Chat


class ChatSerializer(serializers.ModelSerializer):
    """Đọc/ghi một cuộc hội thoại.

    ``owner`` luôn lấy từ request (read-only) để không cho phép giả mạo.
    """

    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    message_count = serializers.IntegerField(read_only=True)
    # PHẢI khai báo tường minh: ``EncryptedJSONField`` là lớp con của ``TextField``
    # nên nếu để DRF tự suy luận, nó dùng ``CharField`` và trả về ``str(list)``
    # (client nhận chuỗi "[{'role': 'user', ...}]" thay vì mảng JSON).
    message = serializers.JSONField(required=False)

    class Meta:
        model = Chat
        fields = [
            "id",
            "owner",
            "title",
            "message",
            "message_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "message_count",
            "created_at",
            "updated_at",
        ]


class ChatListSerializer(serializers.ModelSerializer):
    """Serializer rút gọn cho danh sách hội thoại (không kèm toàn bộ message)."""

    class Meta:
        model = Chat
        fields = ["id", "title", "message_count", "created_at", "updated_at"]
        read_only_fields = fields


class AskRequestSerializer(serializers.Serializer):
    """Body của endpoint hỏi đáp."""

    question = serializers.CharField(
        allow_blank=False, trim_whitespace=True, max_length=8000
    )
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=50)
    temperature = serializers.FloatField(required=False, min_value=0.0, max_value=2.0)
    max_new_tokens = serializers.IntegerField(
        required=False, min_value=1, max_value=8192
    )
    stream = serializers.BooleanField(required=False, default=False)


class AskResponseSerializer(serializers.Serializer):
    """Kết quả trả về của endpoint hỏi đáp."""

    chat_id = serializers.CharField()
    answer = serializers.CharField()
    messages = serializers.ListField(child=serializers.DictField())
    contexts = serializers.ListField(child=serializers.CharField(), required=False)
