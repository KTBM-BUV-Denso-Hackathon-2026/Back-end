from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import UpdateTimestamp, BaseModel
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from pgvector.django import VectorField, HnswIndex
import uuid
# Create your models here.

Users = get_user_model()

class RawData(UpdateTimestamp, BaseModel):
    title = models.TextField()
    summary = models.TextField()
    symptoms = models.TextField(null=True, blank=True)
    root = models.TextField(null=True, blank=True)
    solution = models.TextField(null=True, blank=True)
    content = models.TextField()
    file = models.FileField(upload_to='rag_files/')
    chunks = models.JSONField(default=list, blank=True)  # Lưu trữ danh sách các chunk
    user = models.ForeignKey(Users, on_delete=models.CASCADE)

    class Meta:
        db_table = 'rag_rawdata'
        ordering = ['-created_at']

    def __str__(self):
        return f"RawData {self.id}: {self.title[:30]}"


class RagChunkData(UpdateTimestamp):
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=True)

    # Mỗi chunk sẽ thuộc về 1 RawData
    raw_data = models.ForeignKey(RawData, on_delete=models.CASCADE, related_name='chunks')
    
    # Nội dung của riêng CHUNK này
    chunk_content = models.TextField()
    
    # Thứ tự của chunk trong văn bản gốc (0, 1, 2,...)
    chunk_index = models.IntegerField(default=0)
    
    # Metadata riêng của chunk (ví dụ: page_number, start_char, end_char)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Vector embedding của RIÊNG CHUNK NÀY (mô hình 1536 chiều như text-embedding-3-small)
    vector = VectorField(dimensions=1536, null=True, blank=True)
    
    # Full-text search (FTS) cho riêng chunk này (cho Hybrid Search)
    fts = SearchVectorField(null=True, blank=True)

    class Meta:
        db_table = 'rag_chunkdata'
        ordering = ['raw_data', 'chunk_index']
        indexes = [
            GinIndex(fields=['fts']),
            GinIndex(fields=['metadata']),
            # Index HNSW giúp tìm kiếm vector siêu nhanh
            HnswIndex(
                name='chunk_vector_hnsw_idx',
                fields=['vector'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops']
            ),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} of RawData {self.raw_data_id}"