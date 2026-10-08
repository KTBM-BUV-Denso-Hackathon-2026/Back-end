"""Validator cho file nạp vào hệ thống RAG."""

from pathlib import PurePosixPath

from django.core.exceptions import ValidationError

#: Các định dạng mà ``rag_worker`` có thể trích xuất nội dung.
ALLOWED_EXTENSIONS = (".txt", ".md", ".markdown", ".csv", ".json")

#: Kích thước tối đa cho một file nạp vào (10 MB).
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def validate_document_extension(value) -> None:
    """Đảm bảo file tải lên có phần mở rộng được worker hỗ trợ."""
    name = getattr(value, "name", "") or ""
    extension = PurePosixPath(name.replace("\\", "/")).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Định dạng file không được hỗ trợ. Chỉ nhận: "
            + ", ".join(ALLOWED_EXTENSIONS)
        )


def validate_document_size(value) -> None:
    """Chặn file quá lớn để tránh treo worker/DB."""
    size = getattr(value, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File vượt quá giới hạn {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
