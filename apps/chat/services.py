"""Client gọi microservice ``llm_api``.

``denso_backend`` là caller duy nhất chịu trách nhiệm lưu hội thoại; ``llm_api``
là service stateless (xem ``llm_api/README.md``). Module này gói toàn bộ việc
gọi HTTP, để view chỉ còn việc map lỗi sang HTTP response.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Sequence

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    """Session dùng chung (tái sử dụng connection pool)."""
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


class LLMServiceError(RuntimeError):
    """Lỗi khi gọi ``llm_api`` (mạng, timeout, hoặc lỗi 4xx/5xx)."""


@dataclass
class LLMAnswer:
    """Kết quả một lượt hỏi - đáp."""

    chat_id: str
    answer: str
    messages: List[dict] = field(default_factory=list)
    contexts: List[str] = field(default_factory=list)


def _endpoint(path: str) -> str:
    return f"{settings.LLM_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _auth_headers(token: str) -> dict:
    """Header xác thực nội bộ (rỗng -> không gửi, tương thích chế độ dev)."""
    return {"X-Internal-Token": token} if token else {}


def _trim_history(history: Sequence[dict]) -> List[dict]:
    """Cắt lịch sử còn tối đa ``LLM_MAX_HISTORY_MESSAGES`` message gần nhất.

    ``llm_api`` có trần cứng và sẽ trả 422 nếu vượt. Cắt ở đây giúp hội thoại dài
    vẫn hỏi được. Đồng thời ép mọi message về đúng ``{"role", "content"}`` và bỏ
    phần tử không phải dict — nếu không ``llm_api`` trả 422 với thông báo khó hiểu.
    """
    cleaned = [
        {"role": item.get("role", "user"), "content": item.get("content", "")}
        for item in history or []
        if isinstance(item, dict)
    ]
    limit = getattr(settings, "LLM_MAX_HISTORY_MESSAGES", 0)
    if limit and len(cleaned) > limit:
        logger.info(
            "Cắt lịch sử từ %d xuống %d message (LLM_MAX_HISTORY_MESSAGES).",
            len(cleaned),
            limit,
        )
        cleaned = cleaned[-limit:]
    return cleaned


def _payload(
    chat_id: str,
    question: str,
    history: Sequence[dict],
    top_k: Optional[int] = None,
    temperature: Optional[float] = None,
    max_new_tokens: Optional[int] = None,
) -> dict:
    payload = {
        "chat_id": str(chat_id),
        "new_question": question,
        "history": _trim_history(history),
    }
    if top_k is not None:
        payload["top_k"] = top_k
    if temperature is not None:
        payload["temperature"] = temperature
    if max_new_tokens is not None:
        payload["max_new_tokens"] = max_new_tokens
    return payload


def ask(
    chat_id: str,
    question: str,
    history: Sequence[dict],
    top_k: Optional[int] = None,
    temperature: Optional[float] = None,
    max_new_tokens: Optional[int] = None,
) -> LLMAnswer:
    """Gọi ``POST /chat`` (non-streaming) và trả về câu trả lời đã chuẩn hoá.

    Raises:
        LLMServiceError: khi không gọi được service hoặc service trả lỗi.
    """
    url = _endpoint("/chat")
    payload = _payload(chat_id, question, history, top_k, temperature, max_new_tokens)

    try:
        response = get_session().post(
            url,
            json=payload,
            headers=_auth_headers(settings.LLM_API_TOKEN),
            timeout=settings.LLM_API_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise LLMServiceError(f"Không gọi được LLM API tại {url}: {exc}") from exc

    if response.status_code >= 400:
        raise LLMServiceError(
            f"LLM API trả về {response.status_code}: {response.text[:500]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMServiceError("LLM API trả về dữ liệu không phải JSON.") from exc

    return LLMAnswer(
        chat_id=str(data.get("chat_id", chat_id)),
        answer=data.get("answer", "") or "",
        messages=list(data.get("messages") or []),
        contexts=list(data.get("contexts") or []),
    )


def _iter_sse_events(response: requests.Response) -> Iterator[dict]:
    """Đọc một luồng SSE và yield từng event đã được parse (JSON)."""
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if not data:
            continue
        try:
            yield json.loads(data)
        except ValueError:
            logger.warning("Bỏ qua SSE event không phải JSON: %s", data[:200])


def sse_frame(event: dict) -> bytes:
    """Mã hoá một event dict thành một khung SSE đúng chuẩn (bytes).

    Giữ nguyên tiền tố ``data: `` (bắt buộc theo định dạng SSE) và tiếng Việt
    trong JSON.
    """
    payload = json.dumps(event, ensure_ascii=False)
    return f"data: {payload}\n\n".encode("utf-8")


@dataclass
class LLMStream:
    """Kết quả mở một luồng streaming tới ``llm_api``.

    Việc gọi HTTP được thực hiện NGAY (eager) để lỗi kết nối/HTTP còn map được
    sang status 502; phần còn lại chỉ là đọc dần từng event.
    """

    response: requests.Response
    events: Iterator[dict]

    def close(self) -> None:
        self.response.close()


def open_stream(
    chat_id: str,
    question: str,
    history: Sequence[dict],
    top_k: Optional[int] = None,
    temperature: Optional[float] = None,
    max_new_tokens: Optional[int] = None,
) -> LLMStream:
    """Mở luồng SSE từ ``llm_api``.

    Raises:
        LLMServiceError: khi không kết nối được hoặc service trả lỗi >= 400.
    """
    url = _endpoint("/chat")
    payload = _payload(chat_id, question, history, top_k, temperature, max_new_tokens)
    payload["stream"] = True

    try:
        response = get_session().post(
            url,
            json=payload,
            headers=_auth_headers(settings.LLM_API_TOKEN),
            timeout=settings.LLM_API_STREAM_TIMEOUT,
            stream=True,
        )
    except requests.RequestException as exc:
        raise LLMServiceError(f"Không gọi được LLM API tại {url}: {exc}") from exc

    if response.status_code >= 400:
        body = response.text[:500]
        response.close()
        raise LLMServiceError(f"LLM API trả về {response.status_code}: {body}")

    return LLMStream(response=response, events=_iter_sse_events(response))
