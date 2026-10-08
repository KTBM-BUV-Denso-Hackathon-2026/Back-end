"""Settings cho môi trường preview/dev khi chạy ``runserver``.

Kế thừa toàn bộ ``config.settings.base`` — tức **vẫn dùng PostgreSQL + pgvector**
khai báo trong ``.env``. App ``rag`` dùng ``VectorField``/``HnswIndex`` nên
**không chạy được trên SQLite**; muốn chạy local mà chưa có Postgres thì dùng
``docker compose up -d postgres`` ở thư mục gốc workspace.

Hai khác biệt so với ``base``:

- ``DEBUG = True`` và ``ALLOWED_HOSTS = ["*"]`` để công cụ preview truy cập được
  bằng mọi host.
- ``SECRET_KEY``/``FIELD_ENCRYPTION_KEY`` vẫn lấy từ ``.env`` — không có giá trị
  rác riêng cho preview, tránh tình trạng "chạy được preview nhưng hỏng khi deploy".

Cách chạy::

    set PYTHONPATH=..
    ..\\venv\\Scripts\\python.exe manage.py runserver 0.0.0.0:8000 --settings=config.settings.preview
"""

from config.settings.base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
