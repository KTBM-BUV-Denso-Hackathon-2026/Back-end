"""Kích hoạt nạp dữ liệu RAG sang ``rag_worker``.

Hai chế độ (``RAG_INGEST_MODE``):

- ``http`` (mặc định): gọi ``POST {RAG_WORKER_URL}/ingest`` và nhận kết quả ngay.
  Chạy được mà KHÔNG cần broker (Redis) — phù hợp dev và demo.
- ``celery``: đẩy task ``process.rag.task`` qua broker để worker xử lý bất đồng bộ.

Cả hai chế độ đều dùng chung một hàm xử lý bên ``rag_worker``.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.utils import timezone

from apps.rag.models import IngestionStatus, RawData

logger = logging.getLogger(__name__)


class IngestionError(RuntimeError):
    """Không kích hoạt được quá trình nạp dữ liệu."""


def resolve_file_url(raw_data: RawData, request=None) -> str:
    """Trả về URL (hoặc đường dẫn) để ``rag_worker`` lấy được file.

    - File trên storage ngoài (S3...) → dùng nguyên URL.
    - File local → dựng URL tuyệt đối từ request hiện tại (``/media/...``).
    """
    file_url = raw_data.file.url
    if file_url.startswith(("http://", "https://")):
        return file_url
    if request is not None:
        return request.build_absolute_uri(file_url)
    base = getattr(settings, "MEDIA_BASE_URL", "") or ""
    return f"{base.rstrip('/')}{file_url}" if base else file_url


def mark_failed(raw_data: RawData, message: str) -> None:
    """Ghi trạng thái ``failed`` + thông báo lỗi cho tài liệu (idempotent)."""
    raw_data.status = IngestionStatus.FAILED
    raw_data.error = message[:2000]
    raw_data.updated_at = timezone.now()
    raw_data.save(update_fields=["status", "error", "updated_at"])


def enqueue_ingestion(raw_data: RawData, request=None) -> dict:
    """Gửi yêu cầu nạp dữ liệu cho ``rag_worker``.

    Returns:
        dict mô tả kết quả kích hoạt (``mode``, ``status``, ``chunks``...).

    Raises:
        IngestionError: khi không kích hoạt được (đã ghi ``status=failed``).
    """
    mode = getattr(settings, "RAG_INGEST_MODE", "http").lower()
    file_url = resolve_file_url(raw_data, request)
    payload = {
        "raw_data_id": str(raw_data.id),
        "file_url": file_url,
        "title": raw_data.title,
    }

    if mode == "celery":
        return _enqueue_via_celery(raw_data, payload)
    return _enqueue_via_http(raw_data, payload)


def _auth_headers(token: str) -> dict:
    """Header xác thực nội bộ (rỗng -> không gửi, tương thích chế độ dev)."""
    return {"X-Internal-Token": token} if token else {}


def _enqueue_via_http(raw_data: RawData, payload: dict) -> dict:
    """Gọi thẳng API của ``rag_worker`` (chế độ mặc định)."""
    url = f"{settings.RAG_WORKER_URL.rstrip('/')}/ingest"
    try:
        response = requests.post(
            url,
            json=payload,
            headers=_auth_headers(getattr(settings, "RAG_WORKER_TOKEN", "")),
            timeout=settings.RAG_INGEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        message = f"Không gọi được rag_worker tại {url}: {exc}"
        mark_failed(raw_data, message)
        raise IngestionError(message) from exc

    if response.status_code >= 400:
        message = f"rag_worker trả về {response.status_code}: {response.text[:500]}"
        mark_failed(raw_data, message)
        raise IngestionError(message)

    try:
        result = response.json()
    except ValueError:
        result = {"status": "unknown", "raw": response.text[:200]}
    result["mode"] = "http"
    logger.info(
        "Đã nạp RawData %s qua HTTP: %s", raw_data.id, result.get("status")
    )
    return result


def _enqueue_via_celery(raw_data: RawData, payload: dict) -> dict:
    """Đẩy task qua broker (cần Redis/RabbitMQ đang chạy)."""
    from apps.rag.tasks import dispatch_ingestion

    try:
        dispatch_ingestion.delay(payload["raw_data_id"], payload["file_url"])
    except Exception as exc:  # noqa: BLE001 - broker có thể chưa chạy
        message = f"Không đẩy được task Celery: {type(exc).__name__}: {exc}"
        mark_failed(raw_data, message)
        raise IngestionError(message) from exc

    logger.info("Đã đẩy task nạp dữ liệu cho RawData %s", raw_data.id)
    return {"mode": "celery", "status": "queued", "raw_data_id": str(raw_data.id)}
