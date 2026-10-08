"""Serializer cho app ``rag``."""

from typing import Optional

from rest_framework import serializers

from apps.rag.models import RagChunkData, RawData


class RawDataSerializer(serializers.ModelSerializer):
    """Tài liệu gốc: cho phép upload file và xem trạng thái nạp."""

    user = serializers.PrimaryKeyRelatedField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    chunk_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = RawData
        fields = [
            "id",
            "title",
            "summary",
            "symptoms",
            "root",
            "solution",
            "file",
            "user",
            "status",
            "status_display",
            "error",
            "chunk_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "status",
            "status_display",
            "error",
            "chunk_count",
            "created_at",
            "updated_at",
        ]


class RawDataListSerializer(serializers.ModelSerializer):
    """Bản rút gọn cho danh sách (không kèm nội dung file)."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    chunk_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = RawData
        fields = [
            "id",
            "title",
            "user",
            "status",
            "status_display",
            "chunk_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RagChunkDataSerializer(serializers.ModelSerializer):
    """Chunk đã nạp vào vector DB (chỉ đọc)."""

    #: Không trả vector đầy đủ (rất dài) — chỉ báo có/không và số chiều.
    has_vector = serializers.SerializerMethodField()
    vector_dim = serializers.SerializerMethodField()

    class Meta:
        model = RagChunkData
        fields = [
            "id",
            "raw_data",
            "chunk_index",
            "chunk_content",
            "metadata",
            "has_vector",
            "vector_dim",
            "created_at",
        ]
        read_only_fields = fields

    def get_has_vector(self, obj) -> bool:
        return obj.vector is not None

    def get_vector_dim(self, obj) -> Optional[int]:
        if obj.vector is None:
            return None
        try:
            return len(obj.vector)
        except TypeError:  # pragma: no cover - phụ thuộc backend
            return None
