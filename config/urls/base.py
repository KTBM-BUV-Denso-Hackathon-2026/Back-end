"""URL gốc của dự án ``denso_backend``.

- ``/admin/``        : Django admin.
- ``/auth/``         : đăng ký / đăng nhập / refresh token (dj-jwt-allauth).
- ``/chat/``         : hội thoại + hỏi đáp.
- ``/rag/``          : tài liệu tri thức + chunk.
- ``/api-docs/``     : schema / swagger / redoc.
- ``/media/...``     : file upload (chỉ khi DEBUG).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config.urls.api_docs import urlpatterns as api_docs_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("jwt_allauth.urls")),
    path("chat/", include("apps.chat.urls")),
    path("rag/", include("apps.rag.urls")),
    path("api-docs/", include(api_docs_urlpatterns)),
]

# File media do Django phục vụ khi dev; production nên dùng nginx/S3.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
