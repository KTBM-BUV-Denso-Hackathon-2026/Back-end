"""Task Celery của ``denso_backend`` cho việc nạp dữ liệu RAG.

Toàn bộ logic bóc tách/chia chunk/embedding nằm ở microservice ``rag_worker``
(``rag_worker/main.py``) để không bị trùng lặp. Task ở đây chỉ điều phối: gửi
task ``process.rag.task`` sang broker để ``rag_worker`` thực thi.

Chỉ dùng khi ``RAG_INGEST_MODE=celery``.
"""

from celery import current_app, shared_task


@shared_task(name="apps.rag.tasks.dispatch_ingestion", ignore_result=True)
def dispatch_ingestion(raw_data_id: str, file_url: str) -> None:
    """Chuyển tiếp yêu cầu nạp dữ liệu sang worker qua broker."""
    current_app.send_task(
        "process.rag.task",
        args=[raw_data_id, file_url],
        queue="rag",
    )
