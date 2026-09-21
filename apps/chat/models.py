from django.db import models
from apps.core.models import EncryptedJSONField, UpdateTimestamp
from django.contrib.auth import get_user_model

Users = get_user_model()

# Create your models here.
class Chat(UpdateTimestamp):
    id = models.AutoField(primary_key=True)
    owner = models.ForeignKey(Users, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    message = EncryptedJSONField()

    def __str__(self):
        return f"Chat History {self.id} - User: {self.owner.email}"
