import json
from django.db import models
import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from encrypted_model_fields.fields import EncryptedTextField

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

class Users(AbstractBaseUser, PermissionsMixin, BaseModel):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    level = models.CharField(max_length=30, default='worker')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = BaseUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.email

class UpdateTimestamp(BaseModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class EncryptedJSONField(EncryptedTextField):
    """
    A custom JSONField that encrypts the data before saving it to the database
    and decrypts it when retrieving it.
    """
    def from_db_value(self, value, expression, connection):
        value = super().from_db_value(value, expression, connection)
        if value is not None:
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                return value
        return value

    def get_prep_value(self, value):
        if value is None and not isinstance(value, str):
            value = json.dumps(value)
        encrypted_value = self.encrypt(value)
        return super().get_prep_value(encrypted_value)

    def encrypt(self, value):
        # Implement your encryption logic here
        return value  # Replace with actual encryption

    def decrypt(self, value):
        # Implement your decryption logic here
        return value  # Replace with actual decryption

