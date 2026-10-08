"""Khởi tạo package ``config`` của ``denso_backend``.

Celery được nạp **mềm**: nếu ``celery`` chưa cài (hoặc lỗi cấu hình broker) thì
API vẫn chạy bình thường, chỉ chế độ ``RAG_INGEST_MODE=celery`` không dùng được.
Nhờ vậy ``manage.py check``/``runserver`` không chết vì một phụ thuộc tuỳ chọn.
"""

try:  # pragma: no cover - phụ thuộc tuỳ chọn
    from .celery import app as celery_app
except Exception:  # noqa: BLE001 - thiếu celery thì bỏ qua, không chặn API
    celery_app = None

__all__ = ("celery_app",)
