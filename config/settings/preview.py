"""
Settings override cho PREVIEW/DEV khi chưa có Postgres.
Dùng: python manage.py runserver --settings=config.settings.preview
Chỉ thay đổi DATABASES sang SQLite; mọi thứ khác kế thừa từ base.
"""
from .base import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'preview_db.sqlite3',
    },
    'vector_db': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'preview_db.sqlite3',
    },
}
