"""Test app ``rag``: phân quyền, upload, kích hoạt nạp dữ liệu và pgvector.

Nhóm test này chạy trên PostgreSQL thật (có cột ``vector`` + index HNSW), nên nó
kiểm chứng luôn hợp đồng dữ liệu mà ``llm_api``/``rag_worker`` đang dùng.
"""

import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.core.models import UserLevel
from apps.rag import services
from apps.rag.models import IngestionStatus, RagChunkData, RawData

Users = get_user_model()

MEDIA = tempfile.mkdtemp(prefix="rag-test-media-")


def _upload(name="huong-dan.md", content=b"# Bao tri\n\nNoi dung huong dan."):
    return SimpleUploadedFile(name, content, content_type="text/markdown")


@override_settings(MEDIA_ROOT=MEDIA)
class RagApiTestCase(APITestCase):
    def setUp(self):
        self.worker = Users.objects.create_user(
            email="worker@example.com", password="MatKhau123!"
        )
        self.senior = Users.objects.create_user(
            email="senior@example.com",
            password="MatKhau123!",
            level=UserLevel.SENIOR_ENGINEER,
        )
        self.admin = Users.objects.create_superuser(
            email="admin@example.com", password="MatKhau123!"
        )

    # ------------------------------------------------------------------
    # Phân quyền
    # ------------------------------------------------------------------
    def test_upload_requires_authentication(self):
        response = APIClient().post("/rag/raw-data/", {"title": "x"}, format="multipart")

        self.assertIn(response.status_code, (401, 403))

    def test_senior_engineer_can_upload_with_real_jwt(self):
        """Đi qua đúng lớp xác thực JWT thật, không dùng ``force_authenticate``.

        ``force_authenticate`` gán thẳng instance ``Users`` nên che mất lỗi
        ``JWTStatelessUserAuthentication`` trả về ``TokenUser``.
        """
        login = APIClient().post(
            "/auth/login/",
            {"email": "senior@example.com", "password": "MatKhau123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.content)
        token = login.json()["access"]

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        with mock.patch.object(
            services, "enqueue_ingestion", return_value={"status": "done", "chunks": 1}
        ):
            response = client.post(
                "/rag/raw-data/",
                {"title": "Tài liệu", "file": _upload()},
                format="multipart",
            )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["user"], str(self.senior.id))

    def test_worker_cannot_upload(self):
        client = APIClient()
        client.force_authenticate(self.worker)

        response = client.post(
            "/rag/raw-data/", {"title": "Tài liệu", "file": _upload()}, format="multipart"
        )

        self.assertEqual(response.status_code, 403)

    def test_senior_engineer_can_upload(self):
        client = APIClient()
        client.force_authenticate(self.senior)

        with mock.patch.object(
            services, "enqueue_ingestion", return_value={"status": "done", "chunks": 3}
        ) as enqueue:
            response = client.post(
                "/rag/raw-data/",
                {"title": "Tài liệu", "file": _upload()},
                format="multipart",
            )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["user"], str(self.senior.id))
        self.assertEqual(body["ingestion"]["chunks"], 3)
        enqueue.assert_called_once()

    def test_rejects_unsupported_extension(self):
        client = APIClient()
        client.force_authenticate(self.senior)

        response = client.post(
            "/rag/raw-data/",
            {
                "title": "PDF không hỗ trợ",
                "file": SimpleUploadedFile("a.pdf", b"%PDF-1.4", content_type="application/pdf"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.json())

    # ------------------------------------------------------------------
    # Kích hoạt nạp dữ liệu
    # ------------------------------------------------------------------
    def test_upload_marks_failed_when_worker_unavailable(self):
        client = APIClient()
        client.force_authenticate(self.senior)

        with mock.patch.object(
            services,
            "enqueue_ingestion",
            side_effect=services.IngestionError("Không gọi được rag_worker"),
        ):
            response = client.post(
                "/rag/raw-data/",
                {"title": "Tài liệu", "file": _upload()},
                format="multipart",
            )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], IngestionStatus.FAILED)
        self.assertIn("Không gọi được rag_worker", body["error"])
        self.assertEqual(body["ingestion"]["status"], "failed")

    @override_settings(MEDIA_BASE_URL="http://media.example")
    def test_enqueue_ingestion_builds_absolute_file_url(self):
        raw = RawData.objects.create(title="A", file=_upload(), user=self.senior)
        captured = {}

        def fake_post(url, json=None, timeout=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers or {}

            class _Response:
                status_code = 200
                text = "{}"

                @staticmethod
                def json():
                    return {"status": "done", "chunks": 1}

            return _Response()

        with mock.patch("apps.rag.services.requests.post", side_effect=fake_post):
            result = services.enqueue_ingestion(raw)

        self.assertEqual(result["mode"], "http")
        self.assertEqual(result["chunks"], 1)
        self.assertTrue(captured["json"]["file_url"].startswith("http"))
        self.assertEqual(captured["json"]["raw_data_id"], str(raw.id))
        self.assertTrue(captured["url"].endswith("/ingest"))

    def test_enqueue_ingestion_marks_failed_on_http_error(self):
        raw = RawData.objects.create(title="B", file=_upload(), user=self.senior)

        class _Response:
            status_code = 500
            text = "boom"

            @staticmethod
            def json():  # pragma: no cover - không gọi tới
                return {}

        with mock.patch("apps.rag.services.requests.post", return_value=_Response()):
            with self.assertRaises(services.IngestionError):
                services.enqueue_ingestion(raw)

        raw.refresh_from_db()
        self.assertEqual(raw.status, IngestionStatus.FAILED)
        self.assertIn("rag_worker trả về 500", raw.error)

    # ------------------------------------------------------------------
    # Dữ liệu / pgvector
    # ------------------------------------------------------------------
    def test_list_scoped_for_worker_role(self):
        RawData.objects.create(title="Của tôi", file=_upload(), user=self.worker)
        RawData.objects.create(title="Của senior", file=_upload(), user=self.senior)
        client = APIClient()
        client.force_authenticate(self.worker)

        response = client.get("/rag/raw-data/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_manager_sees_all_documents(self):
        RawData.objects.create(title="Của worker", file=_upload(), user=self.worker)
        RawData.objects.create(title="Của senior", file=_upload(), user=self.senior)
        client = APIClient()
        client.force_authenticate(self.admin)

        response = client.get("/rag/raw-data/")

        self.assertEqual(response.json()["count"], 2)

    def test_chunk_endpoint_reports_vector_info(self):
        raw = RawData.objects.create(title="Có vector", file=_upload(), user=self.senior)
        RagChunkData.objects.create(
            raw_data=raw,
            chunk_content="Nội dung chunk",
            chunk_index=0,
            metadata={"chunk_index": 0},
            vector=[0.01] * 768,
        )
        client = APIClient()
        client.force_authenticate(self.senior)

        response = client.get("/rag/chunks/")

        self.assertEqual(response.status_code, 200)
        chunk = response.json()["results"][0]
        self.assertTrue(chunk["has_vector"])
        self.assertEqual(chunk["vector_dim"], 768)
        self.assertEqual(chunk["chunk_content"], "Nội dung chunk")

    # ------------------------------------------------------------------
    # Lọc bằng query param
    # ------------------------------------------------------------------
    def test_chunk_list_filters_by_raw_data(self):
        """``?raw_data=<uuid>`` phải LỌC thật, không bị bỏ qua âm thầm.

        Trước đây thiếu filter backend nên client tưởng đã lọc nhưng nhận toàn bộ.
        """
        raw_a = RawData.objects.create(title="A", file=_upload(), user=self.senior)
        raw_b = RawData.objects.create(title="B", file=_upload(), user=self.senior)
        RagChunkData.objects.create(raw_data=raw_a, chunk_content="cua A", chunk_index=0)
        RagChunkData.objects.create(raw_data=raw_b, chunk_content="cua B", chunk_index=0)
        client = APIClient()
        client.force_authenticate(self.senior)

        response = client.get(f"/rag/chunks/?raw_data={raw_a.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["chunk_content"], "cua A")

    def test_chunk_list_rejects_invalid_uuid(self):
        client = APIClient()
        client.force_authenticate(self.senior)

        response = client.get("/rag/chunks/?raw_data=khong-phai-uuid")

        self.assertEqual(response.status_code, 400)

    def test_chunk_filter_cannot_leak_other_users_documents(self):
        """Lọc theo ``raw_data`` không được vượt qua giới hạn sở hữu của queryset."""
        mine = RawData.objects.create(title="Của tôi", file=_upload(), user=self.worker)
        theirs = RawData.objects.create(title="Của họ", file=_upload(), user=self.senior)
        RagChunkData.objects.create(raw_data=mine, chunk_content="cua tôi")
        RagChunkData.objects.create(raw_data=theirs, chunk_content="cua họ")
        client = APIClient()
        client.force_authenticate(self.worker)

        response = client.get(f"/rag/chunks/?raw_data={theirs.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_raw_data_list_filters_by_status(self):
        RawData.objects.create(
            title="xong", file=_upload(), user=self.senior, status=IngestionStatus.DONE
        )
        RawData.objects.create(
            title="loi", file=_upload(), user=self.senior, status=IngestionStatus.FAILED
        )
        client = APIClient()
        client.force_authenticate(self.senior)

        response = client.get("/rag/raw-data/?status=failed")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["title"], "loi")


class VectorSearchContractTests(APITestCase):
    """Xác nhận truy vấn cosine ``<=>`` mà ``llm_api`` dùng trả về đúng chunk.

    Truy vấn dưới đây được sao chép nguyên văn từ
    ``llm_api/database/controllers.py::search_by_embeddings``.
    """

    def setUp(self):
        self.user = Users.objects.create_user(
            email="vec@example.com", password="MatKhau123!"
        )
        self.raw = RawData.objects.create(
            title="Vector test", file=_upload(), user=self.user
        )

    @staticmethod
    def _vector(axis: int, dimensions: int = 768):
        """Vector đơn vị theo một trục (cosine với nhau = 0, cùng trục = 1)."""
        vector = [0.0] * dimensions
        vector[axis] = 1.0
        return vector

    def test_cosine_ordering_returns_nearest_chunk(self):
        RagChunkData.objects.create(
            raw_data=self.raw,
            chunk_content="chunk truc 0",
            chunk_index=0,
            vector=self._vector(0),
        )
        RagChunkData.objects.create(
            raw_data=self.raw,
            chunk_content="chunk truc 1",
            chunk_index=1,
            vector=self._vector(1),
        )
        query = "[" + ",".join(repr(v) for v in self._vector(1)) + "]"

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT chunk_content FROM rag_chunkdata "
                "WHERE vector IS NOT NULL "
                "ORDER BY vector <=> %s::vector "
                "LIMIT %s",
                (query, 1),
            )
            rows = cursor.fetchall()

        self.assertEqual([row[0] for row in rows], ["chunk truc 1"])

    def test_vector_dimension_is_768(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'rag_chunkdata'::regclass AND attname = 'vector'"
            )
            dimensions = cursor.fetchone()[0]

        self.assertEqual(dimensions, 768)

    def test_chunk_delete_cascades_with_raw_data(self):
        RagChunkData.objects.create(
            raw_data=self.raw, chunk_content="x", chunk_index=0, vector=self._vector(2)
        )

        self.raw.delete()

        self.assertEqual(RagChunkData.objects.count(), 0)


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
