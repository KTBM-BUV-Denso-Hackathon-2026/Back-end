"""Model của app ``rag``.

Hai bảng, cùng nằm trong PostgreSQL duy nhất của hệ thống (xem
``DATABASES`` trong ``config/settings/base.py``):

- ``rag_rawdata``   : tài liệu gốc do người dùng tải lên + nội dung đã trích xuất.
- ``rag_chunkdata`` : từng chunk kèm vector embedding (pgvector) và cột full-text.

Vì sao không tách "vector DB" riêng: ``RawData.user`` là FK tới ``core_users``
và ``RagChunkData.raw_data`` là FK tới ``rag_rawdata``; PostgreSQL không cho
phép khoá ngoại xuyên database, nên tách DB khiến migration không chạy được.

Tên bảng/cột ở đây là hợp đồng dữ liệu với ``llm_api`` (truy hồi) và
``rag_worker`` (nạp dữ liệu) — đổi tên sẽ làm hai service kia hỏng.
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField

from apps.core.models import UpdateTimestamp
from apps.rag.validators import validate_document_extension, validate_document_size

#: Số chiều vector embedding. PHẢI khớp cả ba nơi:
#: cột ``vector`` dưới đây, ``EMBEDDING_DIM`` của ``llm_api``,
#: và ``EMBEDDING_DIM`` của ``rag_worker``.
RAG_EMBEDDING_DIM = getattr(settings, "RAG_EMBEDDING_DIM", 768)


class IngestionStatus(models.TextChoices):
    """Trạng thái nạp một tài liệu vào vector DB."""

    PENDING = "pending", "Chờ xử lý"
    PROCESSING = "processing", "Đang xử lý"
    DONE = "done", "Hoàn tất"
    FAILED = "failed", "Lỗi"


class RawData(UpdateTimestamp):
    """Tài liệu gốc (file người dùng tải lên) và nội dung đã bóc tách."""

    title = models.TextField()
    summary = models.TextField(blank=True, default="")
    symptoms = models.TextField(null=True, blank=True)
    root = models.TextField(null=True, blank=True)
    solution = models.TextField(null=True, blank=True)
    content = models.TextField(blank=True, default="")
    file = models.FileField(
        upload_to="rag_files/",
        validators=[validate_document_extension, validate_document_size],
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="raw_data",
    )
    status = models.CharField(
        max_length=20,
        choices=IngestionStatus.choices,
        default=IngestionStatus.PENDING,
    )
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "rag_rawdata"
        ordering = ["-created_at"]

    def __str__(self):
        return f"RawData {self.id}: {self.title[:30]}"


class RagChunkData(UpdateTimestamp):
    """Một chunk của ``RawData`` kèm vector embedding."""

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)

    raw_data = models.ForeignKey(
        RawData, on_delete=models.CASCADE, related_name="chunks"
    )

    # Nội dung của riêng chunk này.
    chunk_content = models.TextField()

    # Thứ tự chunk trong văn bản gốc (0, 1, 2, ...).
    chunk_index = models.IntegerField(default=0)

    # Metadata riêng của chunk (ví dụ: source, char_count).
    metadata = models.JSONField(default=dict, blank=True)

    # Vector embedding của chunk (pgvector, cosine distance).
    vector = VectorField(dimensions=RAG_EMBEDDING_DIM, null=True, blank=True)

    # Full-text search (để bật hybrid search sau này).
    fts = SearchVectorField(null=True, blank=True)

    class Meta:
        db_table = "rag_chunkdata"
        ordering = ["raw_data", "chunk_index"]
        indexes = [
            GinIndex(fields=["fts"], name="chunk_fts_gin_idx"),
            GinIndex(fields=["metadata"], name="chunk_metadata_gin_idx"),
            HnswIndex(
                name="chunk_vector_hnsw_idx",
                fields=["vector"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} of RawData {self.raw_data_id}"
