"""Đăng ký model ``Users`` vào Django admin.

Không có file này thì ``/admin/`` mở ra trống, dù ``createsuperuser`` đã tạo
được tài khoản (README hướng dẫn dùng lệnh đó).
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.core.models import Users


class UsersCreationForm(UserCreationForm):
    class Meta:
        model = Users
        fields = ("email",)


class UsersChangeForm(UserChangeForm):
    class Meta:
        model = Users
        fields = "__all__"


@admin.register(Users)
class UsersAdmin(BaseUserAdmin):
    """Quản trị tài khoản.

    Bỏ ``username`` (model đăng nhập bằng email) và hiện ``level`` để admin đổi
    được cấp bậc — đây là cấu hình quyền nghiệp vụ RAG.
    """

    form = UsersChangeForm
    add_form = UsersCreationForm

    list_display = ("email", "first_name", "last_name", "level", "is_staff")
    list_filter = ("level", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Thông tin cá nhân", {"fields": ("first_name", "last_name")}),
        ("Quyền", {"fields": ("level", "is_active", "is_staff", "is_superuser")}),
        (
            "Quyền hạn (theo nhóm)",
            {
                "fields": (
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Ngày giờ", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
