from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import UpdateTimestamp, BaseModel
from pgvector.django import VectorField
# Create your models here.

Users = get_user_model()

class RawData(UpdateTimestamp, BaseModel):
    title = models.TextField()
    description = models.TextField()
    datatype = models.CharField(
        max_length=20,
        choices=[('text', 'Text'), ('image', 'Image'), ('video', 'Video'), ('audio', 'Audio')],
        default='text',
    )
    file = models.FileField(upload_to='rag_files/')
    user = models.ForeignKey(Users, on_delete=models.CASCADE)

    def __str__(self):
        return f"RAG Data {self.id}"

class RagData(UpdateTimestamp, BaseModel):
    raw_data = models.ForeignKey(RawData, on_delete=models.CASCADE)
    vector = VectorField(dimensions=1536, null=True, blank=True)
    processed_data = models.TextField()

    def __str__(self):
        return f"Processed RAG Data {self.id}"