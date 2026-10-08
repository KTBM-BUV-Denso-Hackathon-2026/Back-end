"""Test API của app ``chat``.

``llm_api`` được mock (``apps.chat.services``) để test chạy độc lập, không cần
service thật. Integration test với service thật nằm ở README (kiểm tra thủ công).
"""

import json
import unittest
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from apps.chat import services
from apps.chat.models import Chat

Users = get_user_model()


class FakeStream:
    """Giả lập ``services.LLMStream`` cho đường streaming."""

    def __init__(self, events):
        self.events = iter(events)
        self.closed = False

    def close(self):
        self.closed = True


class ChatApiTestCase(APITestCase):
    def setUp(self):
        self.user = Users.objects.create_user(
            email="owner@example.com", password="MatKhau123!"
        )
        self.other = Users.objects.create_user(
            email="other@example.com", password="MatKhau123!"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def test_list_requires_authentication(self):
        response = APIClient().get("/chat/chats/")

        self.assertIn(response.status_code, (401, 403))

    def test_create_chat_with_real_jwt(self):
        """Xác thực bằng JWT thật: ``request.user`` phải là instance ``Users``.

        Nếu dùng nhầm ``JWTStatelessUserAuthentication``, ``request.user`` là
        ``TokenUser`` và việc gán khoá ngoại ``Chat.owner`` sẽ nổ
        ``ValueError: must be a "Users" instance``.
        """
        login = APIClient().post(
            "/auth/login/",
            {"email": "owner@example.com", "password": "MatKhau123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.content)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        response = client.post("/chat/chats/", {"title": "Thật"}, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Chat.objects.get(pk=response.json()["id"]).owner, self.user)

    def test_create_chat_sets_owner_and_default_title(self):
        response = self.client.post("/chat/chats/", {"title": ""}, format="json")

        self.assertEqual(response.status_code, 201)
        chat = Chat.objects.get(pk=response.json()["id"])
        self.assertEqual(chat.owner, self.user)
        self.assertEqual(chat.message, [])
        self.assertEqual(chat.title, f"Hội thoại {chat.id}")

    def test_message_is_serialized_as_json_list(self):
        """API phải trả ``message`` dạng mảng JSON, không phải chuỗi repr của list.

        ``EncryptedJSONField`` kế thừa ``TextField``; nếu serializer không khai báo
        ``JSONField`` thì DRF dùng ``CharField`` và trả về "[{'role': ...}]" - client
        buộc phải ``ast.literal_eval`` mới dùng được.
        """
        history = [
            {"role": "user", "content": "Quy trình bảo trì?"},
            {"role": "assistant", "content": "Ba bước."},
        ]
        chat = Chat.objects.create(owner=self.user, title="JSON", message=history)

        response = self.client.get(f"/chat/chats/{chat.id}/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["message"], history)
        self.assertEqual(response.json()["message_count"], 2)

    def test_ask_replaces_placeholder_title_with_first_question(self):
        """Nhãn mặc định "Hội thoại <id>" phải được thay bằng câu hỏi đầu tiên."""
        created = self.client.post("/chat/chats/", {"title": ""}, format="json")
        chat = Chat.objects.get(pk=created.json()["id"])
        self.assertEqual(chat.title, chat.default_title)

        fake = services.LLMAnswer(
            chat_id=str(chat.id),
            answer="ok",
            messages=[
                {"role": "user", "content": "Cầu chì cháy thì sao?"},
                {"role": "assistant", "content": "ok"},
            ],
        )

        with mock.patch.object(services, "ask", return_value=fake):
            response = self.client.post(
                f"/chat/chats/{chat.id}/ask/",
                {"question": "Cầu chì cháy thì sao?"},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        chat.refresh_from_db()
        self.assertEqual(chat.title, "Cầu chì cháy thì sao?")

    def test_list_only_returns_own_chats(self):
        mine = Chat.objects.create(owner=self.user, title="Của tôi")
        Chat.objects.create(owner=self.other, title="Của người khác")

        response = self.client.get("/chat/chats/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], mine.id)

    def test_cannot_open_other_users_chat(self):
        strangers = Chat.objects.create(owner=self.other, title="Không phải của tôi")

        response = self.client.get(f"/chat/chats/{strangers.id}/")

        self.assertEqual(response.status_code, 404)

    def test_delete_own_chat(self):
        chat = Chat.objects.create(owner=self.user, title="Xoá được")

        response = self.client.delete(f"/chat/chats/{chat.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Chat.objects.filter(pk=chat.id).exists())

    # ------------------------------------------------------------------
    # Ask
    # ------------------------------------------------------------------
    def test_ask_returns_answer_and_persists_history(self):
        history_in = [
            {"role": "user", "content": "Xin chào"},
            {"role": "assistant", "content": "Chào bạn"},
        ]
        history_out = history_in + [
            {"role": "user", "content": "Quy trình bảo trì?"},
            {"role": "assistant", "content": "Gồm 3 bước."},
        ]
        chat = Chat.objects.create(owner=self.user, title="", message=history_in)
        fake = services.LLMAnswer(
            chat_id=str(chat.id),
            answer="Gồm 3 bước.",
            messages=history_out,
            contexts=["- chunk 1"],
        )

        with mock.patch.object(services, "ask", return_value=fake) as ask_mock:
            response = self.client.post(
                f"/chat/chats/{chat.id}/ask/",
                {"question": "Quy trình bảo trì?"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "Gồm 3 bước.")
        self.assertEqual(body["contexts"], ["- chunk 1"])

        # llm_api phải nhận đúng history cũ + câu hỏi mới.
        kwargs = ask_mock.call_args.kwargs
        self.assertEqual(kwargs["question"], "Quy trình bảo trì?")
        self.assertEqual(kwargs["history"], history_in)

        # History được lưu vào DB; đọc lại vẫn là list (đi qua field mã hoá).
        chat.refresh_from_db()
        self.assertIsInstance(chat.message, list)
        self.assertEqual(chat.message, history_out)
        self.assertEqual(chat.title, "Quy trình bảo trì?")

    def test_ask_rejects_blank_question(self):
        chat = Chat.objects.create(owner=self.user, title="x")

        response = self.client.post(
            f"/chat/chats/{chat.id}/ask/", {"question": "   "}, format="json"
        )

        self.assertEqual(response.status_code, 400)

    def test_ask_returns_502_when_llm_service_fails(self):
        chat = Chat.objects.create(owner=self.user, title="x")

        with mock.patch.object(
            services,
            "ask",
            side_effect=services.LLMServiceError("Không gọi được LLM API"),
        ):
            response = self.client.post(
                f"/chat/chats/{chat.id}/ask/", {"question": "Hỏi gì đó"}, format="json"
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn("Không gọi được LLM API", response.json()["detail"])

    def test_ask_forwards_generation_options(self):
        chat = Chat.objects.create(owner=self.user, title="x")
        fake = services.LLMAnswer(chat_id=str(chat.id), answer="ok", messages=[])

        with mock.patch.object(services, "ask", return_value=fake) as ask_mock:
            self.client.post(
                f"/chat/chats/{chat.id}/ask/",
                {"question": "q", "top_k": 3, "temperature": 0.1, "max_new_tokens": 64},
                format="json",
            )

        kwargs = ask_mock.call_args.kwargs
        self.assertEqual(kwargs["top_k"], 3)
        self.assertEqual(kwargs["temperature"], 0.1)
        self.assertEqual(kwargs["max_new_tokens"], 64)

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    def test_ask_stream_proxies_sse_and_saves_history(self):
        chat = Chat.objects.create(owner=self.user, title="x")
        final_messages = [
            {"role": "user", "content": "Câu hỏi"},
            {"role": "assistant", "content": "Trả lời dần"},
        ]
        stream = FakeStream(
            [
                {"type": "start", "chat_id": str(chat.id)},
                {"type": "delta", "chat_id": str(chat.id), "delta": "Trả lời "},
                {"type": "delta", "chat_id": str(chat.id), "delta": "dần"},
                {"type": "end", "chat_id": str(chat.id), "messages": final_messages},
            ]
        )

        with mock.patch.object(services, "open_stream", return_value=stream):
            response = self.client.post(
                f"/chat/chats/{chat.id}/ask/",
                {"question": "Câu hỏi", "stream": True},
                format="json",
            )
            body = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        # PHẢI kèm charset=utf-8. Nếu chỉ "text/event-stream" thì client nào
        # không tự giả định UTF-8 (vd requests trong Python, fallback sang
        # ISO-8859-1) sẽ hiển thị tiếng Việt thành mojibake ("ÄÃ¢y" thay vì "Đây").
        self.assertEqual(response["Content-Type"], "text/event-stream; charset=utf-8")
        events = [
            json.loads(line[len("data: ") :])
            for line in body.splitlines()
            if line.startswith("data: ")
        ]
        self.assertEqual(events[0]["type"], "start")
        self.assertEqual([e["type"] for e in events[-2:]], ["delta", "end"])
        self.assertTrue(stream.closed)

        chat.refresh_from_db()
        self.assertEqual(chat.message, final_messages)


class LlmApiIntegrationConfigTests(SimpleTestCase):
    """Cấu hình gọi ``llm_api``: header xác thực + cắt lịch sử."""

    def test_auth_header_is_sent_when_token_configured(self):
        with override_settings(LLM_API_TOKEN="s3cret"):
            self.assertEqual(
                services._auth_headers("s3cret"), {"X-Internal-Token": "s3cret"}
            )

    def test_no_auth_header_when_token_empty(self):
        """Rỗng -> không gửi header, để tương thích chế độ dev của llm_api."""
        with override_settings(LLM_API_TOKEN=""):
            self.assertEqual(services._auth_headers(""), {})

    def test_history_is_trimmed_to_limit(self):
        history = [{"role": "user", "content": str(i)} for i in range(250)]
        with override_settings(LLM_MAX_HISTORY_MESSAGES=10):
            trimmed = services._trim_history(history)

        self.assertEqual(len(trimmed), 10)
        # Phải giữ các message CUỐI, không phải đầu.
        self.assertEqual(trimmed[0]["content"], "240")
        self.assertEqual(trimmed[-1]["content"], "249")

    def test_history_not_trimmed_when_under_limit(self):
        history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        with override_settings(LLM_MAX_HISTORY_MESSAGES=10):
            self.assertEqual(services._trim_history(history), history)

    def test_history_limit_zero_disables_trimming(self):
        history = [{"role": "user", "content": str(i)} for i in range(50)]
        with override_settings(LLM_MAX_HISTORY_MESSAGES=0):
            self.assertEqual(len(services._trim_history(history)), 50)

    def test_trim_history_drops_non_dict_and_fills_defaults(self):
        """Phần tử rác bị loại và mọi message chuẩn hoá về đúng 2 khoá."""
        messy = [
            "khong phai dict",
            {"content": "thieu role"},
            {"role": "user", "content": "day du"},
            {"role": "assistant"},  # thieu content -> ""
        ]
        with override_settings(LLM_MAX_HISTORY_MESSAGES=10):
            cleaned = services._trim_history(messy)

        self.assertEqual(
            cleaned,
            [
                {"role": "user", "content": "thieu role"},
                {"role": "user", "content": "day du"},
                {"role": "assistant", "content": ""},
            ],
        )

    def test_payload_contains_trimmed_history(self):
        with override_settings(LLM_MAX_HISTORY_MESSAGES=2):
            payload = services._payload(
                "7", "cau hoi?", [{"role": "user", "content": str(i)} for i in range(9)]
            )
        self.assertEqual(
            [m["content"] for m in payload["history"]], ["7", "8"]
        )
        self.assertEqual(payload["chat_id"], "7")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
