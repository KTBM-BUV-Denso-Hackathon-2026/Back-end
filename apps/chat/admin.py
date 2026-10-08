"""Đăng ký model ``Chat`` vào Django admin.

Cho phép admin xem/xoá hội thoại khi cần dọn dữ liệu. ``message`` được mã hoá
bằng Fernet nên admin hiển thị dạng JSON đã giải mã, không sửa tay (sửa tay sẽ
mất tính toàn vẹn của bản mã).
"""

from django.contrib import admin

from apps.chat.models import Chat


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "owner", "message_count", "created_at", "updated_at")
    list_select_related = ("owner",)
    search_fields = ("title", "owner__email")
    readonly_fields = ("message", "created_at", "updated_at")
    date_hierarchy = "created_at"

    @admin.display(description="Số message")
    def message_count(self, obj):
        return obj.message_count
