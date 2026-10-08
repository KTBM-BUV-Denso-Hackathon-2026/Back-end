"""
Django settings cho ``denso_backend``.

Mọi tham số đọc từ biến môi trường (file ``denso_backend/.env``). Xem
``.env.example`` để biết danh sách đầy đủ.

Kiến trúc DB: **một** PostgreSQL duy nhất, đã bật extension ``pgvector``.

> Vì sao không tách riêng "vector DB": ``RawData.user`` là FK tới ``core.Users``
> và ``Chat`` liên quan tới cùng người dùng; PostgreSQL không cho phép FK xuyên
> database, nên tách DB sẽ khiến migration của app ``rag`` không thể chạy.
> Dùng chung một DB thì ``rag_chunkdata`` (vector) và dữ liệu nghiệp vụ vẫn
> tách bảng rõ ràng, và ``llm_api``/``rag_worker`` chỉ cần một ``DATABASE_URL``.
>
> App ``rag`` dùng pgvector (VectorField/HnswIndex) nên **bắt buộc** PostgreSQL,
> không dùng SQLite.
"""

import os
import sys
from pathlib import Path

import dj_database_url
import dotenv
from django.core.exceptions import ImproperlyConfigured

dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# Tiện ích đọc biến môi trường
# ---------------------------------------------------------------------------
# File này nằm ở ``denso_backend/config/settings/base.py``:
#   parents[0] = denso_backend/config/settings
#   parents[1] = denso_backend/config
#   parents[2] = denso_backend        <-- thư mục gốc của project
BASE_DIR = Path(__file__).resolve().parents[2]  # thư mục denso_backend/


def env(name: str, default: str = "") -> str:
    """Đọc biến môi trường dạng chuỗi."""
    value = os.getenv(name)
    return default if value is None or value == "" else value


def env_bool(name: str, default: bool = False) -> bool:
    """Đọc biến môi trường dạng boolean (true/1/yes/on)."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    """Đọc biến môi trường dạng số nguyên."""
    value = os.getenv(name)
    return default if value is None or value == "" else int(value)


def env_float(name: str, default: float) -> float:
    """Đọc biến môi trường dạng số thực."""
    value = os.getenv(name)
    return default if value is None or value == "" else float(value)


def env_list(name: str, default: list) -> list:
    """Đọc biến môi trường dạng danh sách, phân tách bằng dấu phẩy."""
    value = os.getenv(name)
    if value is None or value == "":
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Bảo mật
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", "django-insecure-dev-only-change-me")
DEBUG = env_bool("DEBUG", True)

# Chặn mang SECRET_KEY mặc định lên production: Django chỉ cảnh báo, ở đây ta
# ném lỗi ngay để không deploy nhầm. Cờ bypass dùng cho CI/kiosk nội bộ.
if not DEBUG and not env_bool("ALLOW_INSECURE_SECRET_KEY", False):
    if SECRET_KEY == "django-insecure-dev-only-change-me" or SECRET_KEY.startswith(
        "django-insecure-"
    ):
        raise ImproperlyConfigured(
            "SECRET_KEY đang là giá trị mặc định/insecure khi DEBUG=False.\n"
            "Sinh key thật bằng:\n"
            '  python -c "from django.core.management.utils import '
            'get_random_secret_key; print(get_random_secret_key())"'
        )

# Luôn cho phép host dùng trong dev/test để tránh lỗi DisallowedHost khó hiểu.
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]"])
if DEBUG:
    ALLOWED_HOSTS = sorted(
        set(ALLOWED_HOSTS)
        | {"localhost", "127.0.0.1", "[::1]", "0.0.0.0", "testserver"}
    )


def _encryption_key():
    """Đọc ``FIELD_ENCRYPTION_KEY`` và kiểm tra định dạng Fernet.

    Hỗ trợ nhiều key (cách nhau bởi dấu phẩy) để xoay khoá: key đầu tiên dùng
    để mã hoá, các key còn lại vẫn giải mã được dữ liệu cũ.
    """
    raw = env("FIELD_ENCRYPTION_KEY", "")
    if not raw:
        raise ImproperlyConfigured(
            "Thiếu FIELD_ENCRYPTION_KEY trong .env.\n"
            "Sinh khoá mới bằng lệnh:\n"
            "  python -c \"from cryptography.fernet import Fernet;"
            " print(Fernet.generate_key().decode())\""
        )

    keys = [item.strip() for item in raw.split(",") if item.strip()]
    try:
        from cryptography.fernet import Fernet

        for key in keys:
            Fernet(key.encode())
    except Exception as exc:  # noqa: BLE001 - thông báo lỗi cho người dùng
        raise ImproperlyConfigured(
            f"FIELD_ENCRYPTION_KEY không hợp lệ ({exc}).\n"
            "Khoá phải là chuỗi base64 44 ký tự. Sinh lại bằng:\n"
            "  python -c \"from cryptography.fernet import Fernet;"
            " print(Fernet.generate_key().decode())\""
        ) from exc

    return keys[0] if len(keys) == 1 else keys


FIELD_ENCRYPTION_KEY = _encryption_key()


# ---------------------------------------------------------------------------
# Ứng dụng
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "jwt_allauth",
    "rest_framework",
    "rest_framework.authtoken",
    "allauth",
    "allauth.account",
    "encrypted_model_fields",
    "drf_spectacular",
    "django_filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Cần cho full-text search + GIN index của app rag.
    "django.contrib.postgres",
    # allauth/JWT cần site hiện tại (jwt_allauth tự set SITE_ID=1).
    "django.contrib.sites",
    "apps.core",
    "apps.chat",
    "apps.rag",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CORS phải đứng ngay sau SecurityMiddleware và trước mọi thứ phát sinh response
    # để request bị chặn bởi CORS cũng nhận được header CORS.
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls.base"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_USER_MODEL = "core.Users"

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def _db_url(prefix: str, default_name: str) -> str:
    """Trả về URL kết nối PostgreSQL.

    Thứ tự ưu tiên:
    1. ``DATABASE_URL`` (tên chuẩn).
    2. ``MAIN_DATABASE_URL`` (tương thích ``.env`` cũ).
    3. Các biến rời ``<prefix>HOST/PORT/NAME/USER/PASSWORD``.
    """
    for name in ("DATABASE_URL", "MAIN_DATABASE_URL"):
        url = env(name, "")
        if url:
            return url

    host = env(f"{prefix}HOST", "localhost")
    port = env(f"{prefix}PORT", "5432")
    name = env(f"{prefix}NAME", default_name)
    user = env(f"{prefix}USER", f"{default_name}_user")
    password = env(f"{prefix}PASSWORD", "")
    credentials = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql://{credentials}{host}:{port}/{name}"


def _conn_max_age() -> int:
    """Thời gian giữ kết nối DB.

    Khi chạy test, đặt 0 để Django đóng hết kết nối trước khi xoá database
    test (tránh lỗi "database is being accessed by other users" trên
    PostgreSQL cloud như Neon).
    """
    if "test" in sys.argv:
        return 0
    return env_int("DB_CONN_MAX_AGE", 600)


def _parse_db(prefix: str, default_name: str) -> dict:
    """Tạo cấu hình DB cho Django; tự bật SSL khi host không phải localhost.

    Ví dụ Neon (cloud Postgres) bắt buộc SSL, còn Postgres chạy local trong
    Docker thì không hỗ trợ SSL.
    """
    url = _db_url(prefix, default_name)
    host = url.rsplit("@", 1)[-1].split("/", 1)[0].split(":")[0].lower()
    ssl_require = host not in {"localhost", "127.0.0.1", "[::1]", ""}
    return dj_database_url.parse(
        url, conn_max_age=_conn_max_age(), ssl_require=ssl_require
    )


DATABASES = {
    "default": _parse_db("DB_", "denso_db"),
}

# ---------------------------------------------------------------------------
# Xác thực / JWT / allauth
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SITE_ID = 1

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Danh sách origin frontend được phép gọi API. Để trống (= không khai báo gì)
# nghĩa là chặn mọi cross-origin request — đây là mặc định an toàn.
# Muốn cho phép: CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
# CORS_ALLOW_ALL_ORIGINS=true chỉ dành cho demo nhanh, KHÔNG dùng ở production.
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", [])
CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", False)
CORS_ALLOW_CREDENTIALS = env_bool("CORS_ALLOW_CREDENTIALS", True)
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

# Model ``core.Users`` không có field ``username`` (đăng nhập bằng email), nên
# phải khai báo rõ để allauth không đi tìm field ``username``.
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"

# jwt_allauth bắt buộc đăng nhập bằng email với đúng các field dưới đây.
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
# Email gửi ra console khi dev (đặt SMTP thật qua biến môi trường khi lên prod).
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)

# jwt_allauth mặc định gửi refresh token trong cookie HttpOnly (view refresh/logout
# của thư viện lại ngầm hiểu khác nhau), nên phải khai báo tường minh để login /
# refresh / logout thống nhất. Mặc định trả refresh token trong JSON body - dễ dùng
# cho desktop/mobile/Postman; bật ``true`` để dùng cookie HttpOnly cho web.
JWT_ALLAUTH_REFRESH_TOKEN_AS_COOKIE = env_bool(
    "JWT_ALLAUTH_REFRESH_TOKEN_AS_COOKIE", False
)

MIGRATION_MODULES = {
    "jwt_allauth": "config.migrations_external.jwt_allauth",
}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # PHẢI dùng ``JWTAuthentication`` (nạp user thật từ DB), KHÔNG dùng
    # ``JWTStatelessUserAuthentication``.
    #
    # jwt_allauth mặc định gợi ý bản stateless, nhưng bản đó trả về ``TokenUser``
    # - một wrapper chỉ có ``id``/``pk``/``username`` (không truy vấn DB). Với app này
    # nó làm hỏng hai chỗ:
    #   1. ``Chat.owner`` / ``RawData.user`` là khoá ngoại tới ``core_users``, gán
    #      ``TokenUser`` vào sẽ lỗi ``ValueError: must be a "Users" instance``.
    #   2. ``request.user.can_manage_rag`` / ``.level`` không tồn tại -> senior
    #      engineer không thể nạp dữ liệu tri thức.
    # ``JWTAuthentication`` vẫn trả ``request.auth`` là token nên claim ``role``
    # và các permission của jwt_allauth vẫn hoạt động bình thường.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": env_int("API_PAGE_SIZE", 20),
    # Cho phép lọc danh sách bằng query param, ví dụ ``/rag/chunks/?raw_data=<uuid>``.
    # Trước đây thiếu mục này nên query param bị bỏ qua âm thầm — client tưởng đã
    # lọc nhưng thực ra nhận toàn bộ dữ liệu.
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    # Chống brute-force đăng nhập và spam API. Tắt khi chạy test để các test
    # dùng chung địa chỉ IP (127.0.0.1) không đụng giới hạn.
    "DEFAULT_THROTTLE_CLASSES": (
        ("rest_framework.throttling.AnonRateThrottle",)
        if "test" in sys.argv
        else (
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
        )
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", "60/min"),
        "user": env("THROTTLE_USER", "600/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "DENSO RAG Chatbot API",
    "DESCRIPTION": (
        "Backend quản lý hội thoại + dữ liệu tri thức cho chatbot RAG. "
        "Hỏi đáp được xử lý bởi microservice llm_api."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# Tích hợp microservice
# ---------------------------------------------------------------------------
# llm_api (FastAPI) — RAG + gọi model.
LLM_API_BASE_URL = env("LLM_API_BASE_URL", "http://localhost:8100")
LLM_API_TIMEOUT = env_float("LLM_API_TIMEOUT", 120.0)
LLM_API_STREAM_TIMEOUT = env_float("LLM_API_STREAM_TIMEOUT", 600.0)
# Shared-secret gửi qua header ``X-Internal-Token``. Phải BẰNG ``INTERNAL_API_TOKEN``
# trong ``llm_api/.env``. Rỗng = không gửi header (chỉ hợp lệ khi service cũng
# để trống, tức chạy localhost dev).
LLM_API_TOKEN = env("LLM_API_TOKEN", "")

# rag_worker (FastAPI + Celery) — nạp tài liệu vào vector DB.
RAG_WORKER_URL = env("RAG_WORKER_URL", "http://localhost:8200")
RAG_INGEST_MODE = env("RAG_INGEST_MODE", "http").strip().lower()
RAG_INGEST_TIMEOUT = env_float("RAG_INGEST_TIMEOUT", 600.0)
# Phải BẰNG ``INTERNAL_API_TOKEN`` trong ``rag_worker/.env``.
RAG_WORKER_TOKEN = env("RAG_WORKER_TOKEN", "")

# Số message lịch sử tối đa gửi sang llm_api cho mỗi lượt hỏi. llm_api có trần
# cứng riêng (MAX_HISTORY_MESSAGES) và trả 422 nếu vượt — cắt sẵn ở đây để hội
# thoại dài vẫn dùng được thay vì báo lỗi. Luôn giữ lại các cặp user/assistant
# ở cuối để ngữ cảnh không bị cắt lệch.
LLM_MAX_HISTORY_MESSAGES = env_int("LLM_MAX_HISTORY_MESSAGES", 100)

# Số chiều vector — phải khớp EMBEDDING_DIM của llm_api/rag_worker
# và cột ``vector`` của bảng rag_chunkdata.
RAG_EMBEDDING_DIM = env_int("RAG_EMBEDDING_DIM", 768)

# ---------------------------------------------------------------------------
# Celery (chỉ cần khi RAG_INGEST_MODE=celery)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "")
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
# Kết quả nạp dữ liệu nằm trong `rag_rawdata.status`, không cần result backend
# nên mặc định bỏ qua (tiết kiệm bộ nhớ Redis). Bật nếu bạn cần `.get()`.
CELERY_TASK_IGNORE_RESULT = env_bool("CELERY_TASK_IGNORE_RESULT", True)
CELERY_TIMEZONE = "UTC"

# ---------------------------------------------------------------------------
# I18N / static / media
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# URL công khai của media, dùng khi cần dựng URL tuyệt đối mà không có request.
MEDIA_BASE_URL = env("MEDIA_BASE_URL", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Logging (đủ để thấy lỗi tích hợp giữa các service khi dev)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
    },
}
