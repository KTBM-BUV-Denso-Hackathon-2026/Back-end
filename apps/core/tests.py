"""Test cho app ``core``: user manager và field mã hoá."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.chat.models import Chat
from apps.core.models import EncryptedJSONField, UserLevel

Users = get_user_model()


class UserManagerTests(TestCase):
    def test_create_user_uses_email_and_hides_password(self):
        user = Users.objects.create_user(
            email="Worker@Example.com", password="MatKhau123!"
        )

        self.assertEqual(user.email, "Worker@example.com")  # chuẩn hoá domain
        self.assertTrue(user.check_password("MatKhau123!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.level, UserLevel.WORKER)

    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            Users.objects.create_user(email="", password="x")

    def test_create_superuser(self):
        admin = Users.objects.create_superuser(
            email="admin@example.com", password="MatKhau123!"
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.level, UserLevel.ADMIN)
        self.assertTrue(admin.can_manage_rag)

    def test_can_manage_rag_only_for_managers(self):
        worker = Users.objects.create_user(email="w@example.com", password="x")
        senior = Users.objects.create_user(
            email="s@example.com", password="x", level=UserLevel.SENIOR_ENGINEER
        )

        self.assertFalse(worker.can_manage_rag)
        self.assertTrue(senior.can_manage_rag)

    def test_role_claim_matches_level(self):
        """jwt_allauth đọc ``user.role`` khi phát JWT - thiếu là 500 mỗi lần login."""
        from apps.core.models import (
            ROLE_ADMIN,
            ROLE_SENIOR_ENGINEER,
            ROLE_STAFF,
            ROLE_WORKER,
        )

        worker = Users.objects.create_user(email="r1@example.com", password="x")
        senior = Users.objects.create_user(
            email="r2@example.com", password="x", level=UserLevel.SENIOR_ENGINEER
        )
        admin = Users.objects.create_user(
            email="r3@example.com", password="x", level=UserLevel.ADMIN
        )
        superuser = Users.objects.create_superuser(email="r4@example.com", password="x")

        self.assertEqual(worker.role, ROLE_WORKER)
        self.assertEqual(senior.role, ROLE_SENIOR_ENGINEER)
        self.assertEqual(admin.role, ROLE_ADMIN)
        self.assertEqual(superuser.role, ROLE_STAFF)

    def test_role_assignment_maps_back_to_level(self):
        """jwt_allauth gán ``user.role = int(role)`` - gán xong phải giữ nguyên."""
        from apps.core.models import ROLE_SENIOR_ENGINEER

        user = Users.objects.create_user(email="r5@example.com", password="x")
        user.role = ROLE_SENIOR_ENGINEER

        self.assertEqual(user.level, UserLevel.SENIOR_ENGINEER)
        self.assertEqual(user.role, ROLE_SENIOR_ENGINEER)

    def test_issuing_jwt_does_not_crash(self):
        """Bảo vệ trực tiếp lỗi ``AttributeError: 'Users' object has no attribute 'role'``."""
        from jwt_allauth.tokens.app_settings import RefreshToken

        user = Users.objects.create_user(
            email="r6@example.com", password="x", level=UserLevel.SENIOR_ENGINEER
        )
        token = RefreshToken.for_user(user)

        self.assertIn("role", token.payload)
        self.assertEqual(token.payload["role"], user.role)

    def test_created_user_can_actually_log_in(self):
        """jwt_allauth đòi EmailAddress(verified=True) mới cho đăng nhập.

        Không có bước đồng bộ này thì user do ``createsuperuser`` tạo ra sẽ bị
        trả 401 "User email is not verified" mãi mãi.
        """
        from allauth.account.models import EmailAddress

        user = Users.objects.create_superuser(
            email="boss@example.com", password="MatKhau123!"
        )
        address = EmailAddress.objects.filter(user=user).first()

        self.assertIsNotNone(address, "phải có bản ghi EmailAddress cho user")
        self.assertEqual(address.email, "boss@example.com")
        self.assertTrue(address.verified)
        self.assertTrue(address.primary)


class EncryptedJSONFieldTests(TestCase):
    """Field phải mã hoá khi ghi và trả về đúng list/dict khi đọc."""

    def test_round_trip_keeps_python_structure(self):
        user = Users.objects.create_user(email="u@example.com", password="x")
        messages = [
            {"role": "user", "content": "Quy trình bảo trì?"},
            {"role": "assistant", "content": "Gồm 3 bước: A, B, C."},
        ]
        chat = Chat.objects.create(owner=user, title="Test", message=messages)

        chat.refresh_from_db()

        self.assertIsInstance(chat.message, list)
        self.assertEqual(chat.message, messages)
        self.assertEqual(chat.message[1]["content"], "Gồm 3 bước: A, B, C.")

    def test_value_is_encrypted_in_database(self):
        """Giá trị thô trong DB phải là bản mã Fernet, không có nội dung gốc."""
        user = Users.objects.create_user(email="enc@example.com", password="x")
        secret_text = "Bí mật nội bộ DENSO"
        chat = Chat.objects.create(
            owner=user,
            title="Secret",
            message=[{"role": "user", "content": secret_text}],
        )

        with connection.cursor() as cursor:
            cursor.execute("SELECT message FROM chat_chat WHERE id = %s", [chat.id])
            raw = cursor.fetchone()[0]

        self.assertNotIn(secret_text, str(raw))
        # Token của Fernet luôn bắt đầu bằng 'gAAAAA'.
        self.assertTrue(
            str(raw).startswith("gAAAA"), f"Giá trị lưu trong DB không phải bản mã: {raw!r}"
        )

    def test_default_is_empty_list(self):
        user = Users.objects.create_user(email="e@example.com", password="x")
        chat = Chat.objects.create(owner=user, title="Empty")

        chat.refresh_from_db()

        self.assertEqual(chat.message, [])

    def test_field_accepts_dict_and_none(self):
        field = EncryptedJSONField()

        self.assertIsNone(field.get_prep_value(None))
        self.assertEqual(field.get_prep_value({"a": 1}), '{"a": 1}')
        self.assertEqual(field.get_prep_value("already-a-string"), "already-a-string")


class UsersStrTests(TestCase):
    def test_get_full_name_falls_back_to_email(self):
        user = Users.objects.create_user(email="noname@example.com", password="x")

        self.assertEqual(user.get_full_name(), "noname@example.com")
        self.assertEqual(str(user), "noname@example.com")

    def test_get_full_name_uses_first_and_last_name(self):
        user = Users.objects.create_user(
            email="full@example.com",
            password="x",
            first_name="Nguyen",
            last_name="An",
        )

        self.assertEqual(user.get_full_name(), "Nguyen An")


class AuthApiTests(TestCase):
    """Kiểm tra luồng xác thực thật qua HTTP: đăng ký -> đăng nhập -> lấy thông tin.

    Đây là lưới an toàn cho các lỗi tích hợp với jwt_allauth (ví dụ model thiếu
    thuộc tính ``role`` khiến mọi lần đăng nhập trả HTTP 500).
    """

    PASSWORD = "MatKhau123!"

    def test_register_login_and_fetch_profile(self):
        register = self.client.post(
            "/auth/registration/",
            data={
                "email": "newbie@example.com",
                "password1": self.PASSWORD,
                "password2": self.PASSWORD,
                "first_name": "New",
                "last_name": "Bie",
            },
            content_type="application/json",
        )
        self.assertEqual(register.status_code, 201, register.content)
        self.assertIn("access", register.json())

        login = self.client.post(
            "/auth/login/",
            data={"email": "newbie@example.com", "password": self.PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200, login.content)
        payload = login.json()
        self.assertIn("access", payload)
        # Refresh token có thể nằm trong body hoặc trong cookie HttpOnly tuỳ cấu hình.
        self.assertTrue(
            payload.get("refresh") or login.cookies.get("refresh_token"),
            "login phải phát refresh token",
        )

        profile = self.client.get(
            "/auth/user/", HTTP_AUTHORIZATION=f"Bearer {payload['access']}"
        )
        self.assertEqual(profile.status_code, 200, profile.content)
        self.assertEqual(profile.json()["email"], "newbie@example.com")

    def test_refresh_issues_new_access_token(self):
        Users.objects.create_user(email="refresh@example.com", password=self.PASSWORD)
        login = self.client.post(
            "/auth/login/",
            data={"email": "refresh@example.com", "password": self.PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200, login.content)
        refresh = login.json().get("refresh") or login.cookies["refresh_token"].value

        response = self.client.post(
            "/auth/refresh/", data={"refresh": refresh}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("access", response.json())

    def test_login_rejects_wrong_password(self):
        Users.objects.create_user(email="known@example.com", password=self.PASSWORD)

        response = self.client.post(
            "/auth/login/",
            data={"email": "known@example.com", "password": "sai-mat-khau"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401, response.content)

    def test_superuser_created_from_cli_can_log_in(self):
        """``createsuperuser`` phải tạo luôn EmailAddress đã xác thực."""
        Users.objects.create_superuser(email="root@example.com", password=self.PASSWORD)

        response = self.client.post(
            "/auth/login/",
            data={"email": "root@example.com", "password": self.PASSWORD},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)

    def test_protected_endpoint_requires_authentication(self):
        response = self.client.get("/chat/chats/")

        self.assertIn(response.status_code, (401, 403), response.content)
