"""Model dùng chung cho toàn bộ denso_backend.

Gồm:
- ``BaseModel``          : khoá chính UUID cho mọi model nghiệp vụ.
- ``UpdateTimestamp``    : thêm ``created_at`` / ``updated_at``.
- ``Users``              : user tuỳ biến, đăng nhập bằng email, có ``level``.
- ``EncryptedJSONField`` : JSON được mã hoá bằng Fernet (django-encrypted-model-fields).
"""

import json
import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from encrypted_model_fields.fields import EncryptedTextField
from jwt_allauth.roles import STAFF_CODE, SUPER_USER_CODE, USER_CODE


class BaseModel(models.Model):
    """Model trừu tượng: khoá chính UUID.

    Lưu ý: ``Chat`` cố ý ghi đè ``id`` thành ``AutoField`` để URL hội thoại
    ngắn (``/chat/chats/12/ask/`` thay vì một UUID dài 36 ký tự). Nên không phải
    model nghiệp vụ nào cũng dùng UUID — đừng viết code giả định điều đó.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class UpdateTimestamp(BaseModel):
    """Model trừu tượng: thêm mốc thời gian tạo/cập nhật."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserLevel(models.TextChoices):
    """Cấp bậc người dùng, dùng để phân quyền nghiệp vụ RAG."""

    WORKER = "worker", "Worker"
    SENIOR_ENGINEER = "senior engineer", "Senior engineer"
    ADMIN = "admin", "Admin"


# Các cấp bậc được phép nạp / sửa dữ liệu tri thức (RAG).
# Các cấp bậc được phép nạp / sửa dữ liệu tri thức (RAG).
# Dùng member của ``TextChoices`` (là subclass của ``str``) nên so sánh trực
# tiếp với ``user.level`` — thuộc tính kiểu ``str`` — vẫn đúng.
RAG_MANAGER_LEVELS = (UserLevel.SENIOR_ENGINEER, UserLevel.ADMIN)


# Mã vai trò số nguyên theo hợp đồng của jwt_allauth.
#
# ``jwt_allauth.tokens.tokens.RefreshToken.set_user_role`` đọc thẳng ``user.role``
# và ghi vào claim ``role`` của JWT; nếu model không có thuộc tính này thì MỌI lần
# đăng nhập đều nổ ``AttributeError`` (HTTP 500). Vì vậy ``Users`` bên dưới bắc cầu
# giữa ``level`` (khái niệm nghiệp vụ, dạng chuỗi) và ``role`` (mã số cho JWT).
ROLE_WORKER = USER_CODE  # 0
ROLE_SENIOR_ENGINEER = 500
ROLE_ADMIN = SUPER_USER_CODE  # 900
ROLE_STAFF = STAFF_CODE  # 1000

_ROLE_BY_LEVEL = {
    UserLevel.WORKER.value: ROLE_WORKER,
    UserLevel.SENIOR_ENGINEER.value: ROLE_SENIOR_ENGINEER,
    UserLevel.ADMIN.value: ROLE_ADMIN,
}


def sync_allauth_email(user):
    """Tạo/cập nhật bản ghi ``EmailAddress`` đã xác thực cho ``user``.

    ``jwt_allauth`` chỉ cho đăng nhập khi tồn tại ``EmailAddress(verified=True)``
    (xem ``jwt_allauth.utils.is_email_verified``). Người dùng tạo bằng
    ``createsuperuser`` hoặc ``create_user`` (script seed, fixture, test) không
    đi qua luồng đăng ký của allauth nên phải đồng bộ ở đây - nếu không họ sẽ
    không bao giờ đăng nhập được dù mật khẩu đúng.
    """

    try:
        from allauth.account.models import EmailAddress
    except Exception:  # pragma: no cover - allauth không nằm trong INSTALLED_APPS
        return

    try:
        # Email mới trở thành primary, hạ các email cũ xuống.
        EmailAddress.objects.filter(user=user).exclude(
            email__iexact=user.email
        ).update(primary=False)
        EmailAddress.objects.update_or_create(
            user=user,
            email=user.email,
            defaults={"primary": True, "verified": True},
        )
    except Exception:  # pragma: no cover - bảng chưa được migrate
        return


class UserManager(BaseUserManager):
    """Manager cho ``Users``: tạo user bằng email thay vì username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email là bắt buộc.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        sync_allauth_email(user)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("level", UserLevel.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser phải có is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser phải có is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class Users(AbstractBaseUser, PermissionsMixin, BaseModel):
    """Người dùng đăng nhập bằng email."""

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True, default="")
    last_name = models.CharField(max_length=30, blank=True, default="")
    level = models.CharField(
        max_length=30,
        choices=UserLevel.choices,
        default=UserLevel.WORKER,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "core_users"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self):
        return self.first_name or self.email

    @property
    def role(self) -> int:
        """Mã vai trò mà jwt_allauth ghi vào claim ``role`` của JWT.

        Suy ra từ ``is_staff`` / ``is_superuser`` / ``level`` nên không thể lệch
        pha với ``level`` - chỉ có một nguồn sự thật duy nhất là ``level``.
        """
        if self.is_staff:
            return ROLE_STAFF
        if self.is_superuser:
            return ROLE_ADMIN
        return _ROLE_BY_LEVEL.get(self.level, ROLE_WORKER)

    @role.setter
    def role(self, value):
        """Cho phép gán mã vai trò (jwt_allauth gán ``user.role = int(role)``).

        Giá trị lạ sẽ bị bỏ qua thay vì làm hỏng ``level``.
        """
        try:
            code = int(value)
        except (TypeError, ValueError):
            return
        if code == ROLE_STAFF:
            self.is_staff = True
            self.level = UserLevel.ADMIN
            return
        for level, mapped in _ROLE_BY_LEVEL.items():
            if mapped == code:
                self.level = level
                return

    @property
    def can_manage_rag(self) -> bool:
        """True nếu người dùng được phép nạp/sửa dữ liệu tri thức."""
        return bool(self.is_superuser or self.level in RAG_MANAGER_LEVELS)

    def __str__(self):
        return self.email


class EncryptedJSONField(EncryptedTextField):
    """Trường JSON được mã hoá trước khi ghi xuống DB.

    - Khi ghi: ``json.dumps`` -> Fernet encrypt (do ``EncryptedTextField`` lo).
    - Khi đọc: Fernet decrypt -> ``json.loads``.

    Nhờ vậy giá trị trả về luôn là list/dict Python, không phải chuỗi.
    """

    description = "JSON được mã hoá trong DB"

    def from_db_value(self, value, expression, connection):
        value = super().from_db_value(value, expression, connection)
        if value is None:
            return None
        if isinstance(value, (str, bytes)):
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                # Dữ liệu cũ không phải JSON: trả nguyên trạng thay vì crash.
                return value
        return value

    def get_prep_value(self, value):
        if value is None:
            return None
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        return super().get_prep_value(value)

    def value_to_string(self, obj):
        """Dùng cho ``dumpdata``: trả về chuỗi JSON dễ đọc."""
        value = self.value_from_object(obj)
        return json.dumps(value, ensure_ascii=False) if value is not None else None
