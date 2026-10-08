"""View cho app ``rag``.

- ``/rag/raw-data/``          : tải tài liệu lên (tự động nạp vào vector DB).
- ``/rag/raw-data/<uuid>/``   : xem / sửa / xoá tài liệu.
- ``/rag/chunks/``            : xem các chunk đã nạp (chỉ đọc).
- ``/rag/chunks/<uuid>/``     : xem chi tiết một chunk (chỉ đọc).

Quyền: mọi user đã đăng nhập được đọc; chỉ RAG manager (superuser hoặc
``level`` = senior engineer/admin) được ghi.
"""

import logging

from django.db.models import Count
from rest_framework import generics, status
from rest_framework.response import Response

from apps.core.permissions import IsRAGManager
from apps.rag import services
from apps.rag.models import RagChunkData, RawData
from apps.rag.serializers import (
    RagChunkDataSerializer,
    RawDataListSerializer,
    RawDataSerializer,
)

logger = logging.getLogger(__name__)


class RawDataListCreateView(generics.ListCreateAPIView):
    """Liệt kê tài liệu và upload tài liệu mới."""

    permission_classes = [IsRAGManager]
    filterset_fields = ["status", "user"]

    def get_queryset(self):
        # ``order_by`` tường minh: annotate() làm queryset mất thứ tự mặc định,
        # khi đó phân trang sẽ trả kết quả không ổn định.
        queryset = RawData.objects.annotate(
            chunk_count=Count("chunks", distinct=True)
        ).order_by("-created_at")
        user = self.request.user
        if user.is_superuser or getattr(user, "can_manage_rag", False):
            return queryset
        return queryset.filter(user=user)

    def get_serializer_class(self):
        return RawDataListSerializer if self.request.method == "GET" else RawDataSerializer

    def create(self, request, *args, **kwargs):
        """Tạo ``RawData`` rồi kích hoạt nạp dữ liệu sang ``rag_worker``.

        Nếu worker lỗi/không chạy, tài liệu vẫn được tạo nhưng ``status=failed``
        kèm thông báo trong ``error`` — client biết chính xác chuyện gì xảy ra.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_data = serializer.save(user=request.user)

        ingestion = None
        ingestion_error = None
        try:
            ingestion = services.enqueue_ingestion(raw_data, request=request)
        except services.IngestionError as exc:
            ingestion_error = str(exc)
            # Ghi lại trạng thái thất bại để client đọc được qua API.
            services.mark_failed(raw_data, ingestion_error)
            logger.warning("Nạp dữ liệu thất bại cho RawData %s: %s", raw_data.id, exc)

        raw_data.refresh_from_db()
        data = RawDataSerializer(raw_data).data
        data["ingestion"] = ingestion or {"status": "failed", "error": ingestion_error}
        headers = self.get_success_headers(serializer.data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)


class RawDataDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Xem / sửa / xoá một tài liệu."""

    serializer_class = RawDataSerializer
    permission_classes = [IsRAGManager]
    lookup_field = "id"

    def get_queryset(self):
        queryset = RawData.objects.annotate(
            chunk_count=Count("chunks", distinct=True)
        ).order_by("-created_at")
        user = self.request.user
        if user.is_superuser or getattr(user, "can_manage_rag", False):
            return queryset
        return queryset.filter(user=user)


class RagChunkListView(generics.ListAPIView):
    """Liệt kê chunk đã nạp (chỉ đọc).

    Hỗ trợ lọc bằng query param, ví dụ ``/rag/chunks/?raw_data=<uuid>``.
    Khai báo ``filterset_fields`` là bắt buộc khi đã bật ``DjangoFilterBackend``,
    nếu không sẽ 500. Còn nếu thiếu cả hai thì query param bị bỏ qua âm thầm và
    client tưởng đã lọc nhưng thực ra nhận toàn bộ.
    """

    serializer_class = RagChunkDataSerializer
    permission_classes = [IsRAGManager]
    filterset_fields = ["raw_data", "raw_data__user"]

    def get_queryset(self):
        queryset = RagChunkData.objects.select_related("raw_data")
        user = self.request.user
        if user.is_superuser or getattr(user, "can_manage_rag", False):
            return queryset
        return queryset.filter(raw_data__user=user)


class RagChunkDetailView(generics.RetrieveAPIView):
    """Xem chi tiết một chunk (chỉ đọc)."""

    serializer_class = RagChunkDataSerializer
    permission_classes = [IsRAGManager]
    lookup_field = "id"

    def get_queryset(self):
        queryset = RagChunkData.objects.select_related("raw_data")
        user = self.request.user
        if user.is_superuser or getattr(user, "can_manage_rag", False):
            return queryset
        return queryset.filter(raw_data__user=user)
