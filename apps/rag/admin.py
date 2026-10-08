"""Đăng ký model app ``rag`` vào Django admin.

Hữu ích nhất ở cột ``status``/``error``: khi upload thất bại (``failed``) thì
thông bố lỗi nằm ngay trong admin, không phải mở log tìm.
"""

from django.contrib import admin

from apps.rag.models import RagChunkData, RawData


@admin.register(RawData)
class RawDataAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "user",
        "chunk_total",
        "created_at",
        "updated_at",
    )
    list_filter = ("status",)
    list_select_related = ("user",)
    search_fields = ("title", "summary", "user__email")
    readonly_fields = ("status", "error", "content", "created_at", "updated_at")
    date_hierarchy = "created_at"

    @admin.display(description="Số chunk")
    def chunk_total(self, obj):
        return obj.chunks.count()


@admin.register(RagChunkData)
class RagChunkDataAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "raw_data",
        "chunk_index",
        "has_vector",
        "vector_dim",
        "created_at",
    )
    list_select_related = ("raw_data",)
    search_fields = ("chunk_content", "raw_data__title")
    # ``vector`` (768 phần tử) và ``fts`` quá lớn để hiển thị/sửa trong admin.
    readonly_fields = ("id", "raw_data", "chunk_content", "chunk_index", "vector", "fts", "created_at", "updated_at")
    date_hierarchy = "created_at"

    @admin.display(boolean=True, description="Có vector")
    def has_vector(self, obj):
        return obj.vector is not None

    @admin.display(description="Số chiều")
    def vector_dim(self, obj):
        if obj.vector is None:
            return None
        try:
            return len(obj.vector)
        except TypeError:  # pragma: no cover - phụ thuộc backend
            return None
