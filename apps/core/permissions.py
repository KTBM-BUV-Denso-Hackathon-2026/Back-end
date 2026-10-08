"""Quyền truy cập dùng chung (DRF permissions)."""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsRAGManager(BasePermission):
    """Chỉ superuser hoặc user có ``level`` thuộc nhóm quản lý tri thức được ghi.

    - Đọc (GET/HEAD/OPTIONS): mọi user đã đăng nhập đều được phép.
    - Ghi (POST/PUT/PATCH/DELETE): chỉ RAG manager.
    """

    message = "Bạn không có quyền thay đổi dữ liệu tri thức (RAG)."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(getattr(user, "can_manage_rag", False))
