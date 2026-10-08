"""View cho app ``chat``.

- ``/chat/chats/``            : liệt kê & tạo hội thoại của user hiện tại.
- ``/chat/chats/<id>/``       : xem / sửa / xoá một hội thoại.
- ``/chat/chats/<id>/ask/``   : hỏi đáp (gọi microservice ``llm_api``).
"""

import logging

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat import services
from apps.chat.models import Chat
from apps.chat.serializers import (
    AskRequestSerializer,
    AskResponseSerializer,
    ChatListSerializer,
    ChatSerializer,
)

logger = logging.getLogger(__name__)


class ChatListCreateView(generics.ListCreateAPIView):
    """Liệt kê / tạo hội thoại. User chỉ thấy hội thoại của chính mình."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Chat.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ChatSerializer
        return ChatListSerializer

    def perform_create(self, serializer):
        chat = serializer.save(owner=self.request.user)
        if not chat.title:
            chat.title = chat.default_title
            chat.save(update_fields=["title", "updated_at"])


class ChatDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Xem / đổi tên / xoá một hội thoại."""

    serializer_class = ChatSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Chat.objects.filter(owner=self.request.user)


class ChatAskView(APIView):
    """Hỏi đáp dựa trên lịch sử của một hội thoại.

    Body: ``{"question": "...", "top_k": 5, "stream": false}``.

    Luồng xử lý:
    1. Lấy ``chat.message`` (đã giải mã) làm history.
    2. Gọi ``llm_api`` (``POST /chat``) — service này tự làm RAG.
    3. Lưu lại ``messages`` mà service trả về (đã gồm câu hỏi mới + câu trả lời).

    Khi ``stream=true``, trả ``text/event-stream`` proxy trực tiếp từ ``llm_api``
    và vẫn lưu history khi nhận event ``end``.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AskRequestSerializer

    @extend_schema(
        request=AskRequestSerializer,
        responses={
            200: AskResponseSerializer,
            502: OpenApiResponse(description="llm_api không phản hồi được"),
        },
        description=(
            "Hỏi đáp RAG dựa trên lịch sử hội thoại. Khi ``stream=true``, response là "
            "``text/event-stream`` (SSE) với các event ``start`` / ``token`` / ``end`` "
            "hoặc ``error``, mỗi event là một dòng ``data: {json}``."
        ),
    )
    def post(self, request, pk):
        chat = get_object_or_404(Chat, pk=pk, owner=request.user)

        payload = AskRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        history = chat.message or []

        try:
            if data.get("stream"):
                return self._stream(chat, history, data)
            result = services.ask(
                chat_id=str(chat.id),
                question=data["question"],
                history=history,
                top_k=data.get("top_k"),
                temperature=data.get("temperature"),
                max_new_tokens=data.get("max_new_tokens"),
            )
        except services.LLMServiceError as exc:
            logger.warning("Gọi llm_api thất bại cho chat_id=%s: %s", chat.id, exc)
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        self._persist(chat, result.messages, data["question"])
        return Response(AskResponseSerializer(result).data)

    # ------------------------------------------------------------------
    # Nội bộ
    # ------------------------------------------------------------------
    @staticmethod
    def _persist(chat: Chat, messages, question: str) -> None:
        """Lưu history mới vào ``chat.message`` (bỏ qua nếu service trả rỗng)."""
        if not messages:
            return
        fields = ["message", "updated_at"]
        chat.message = messages
        # Tiêu đề mặc định chỉ là nhãn tạm -> thay bằng câu hỏi đầu tiên.
        if not chat.title or chat.title == chat.default_title:
            chat.title = question[:255]
            fields.append("title")
        chat.save(update_fields=fields)

    def _stream(self, chat: Chat, history, data) -> StreamingHttpResponse:
        """Mở luồng SSE từ ``llm_api`` và proxy về client."""
        stream = services.open_stream(
            chat_id=str(chat.id),
            question=data["question"],
            history=history,
            top_k=data.get("top_k"),
            temperature=data.get("temperature"),
            max_new_tokens=data.get("max_new_tokens"),
        )

        def proxy():
            try:
                for event in stream.events:
                    if event.get("type") == "end":
                        self._persist(chat, event.get("messages"), data["question"])
                    elif event.get("type") == "error":
                        logger.error(
                            "llm_api báo lỗi khi stream chat_id=%s: %s",
                            chat.id,
                            event.get("error"),
                        )
                    yield services.sse_frame(event)
            finally:
                stream.close()

        response = StreamingHttpResponse(
            proxy(),
            # PHẢI khai báo charset=utf-8: nếu chỉ "text/event-stream" thì client
            # (vd requests trong Python) sẽ fallback sang ISO-8859-1 và tiếng Việt
            # ra mojibake ("ÄÃ¢y" thay vì "Đây"). EventSource của trình duyệt tự
            # giả định UTF-8 nhưng fetch + TextDecoder thì không, nên server phải
            # nói rõ.
            content_type="text/event-stream; charset=utf-8",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
