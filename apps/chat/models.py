"""Model của app ``chat``."""

from django.conf import settings
from django.db import models

from apps.core.models import EncryptedJSONField, UpdateTimestamp


class Chat(UpdateTimestamp):
    """Một cuộc hội thoại.

    ``message`` là danh sách message theo chuẩn OpenAI:
    ``[{"role": "user"|"assistant"|"system", "content": "..."}]``.
    Trường này được mã hoá trong DB (xem ``EncryptedJSONField``).
    """

    id = models.AutoField(primary_key=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chats",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    message = EncryptedJSONField(default=list)

    class Meta:
        db_table = "chat_chat"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Chat {self.id} - Owner: {self.owner_id}"

    @property
    def message_count(self) -> int:
        return len(self.message or [])

    @property
    def default_title(self) -> str:
        """Nhãn tạm khi người dùng chưa đặt tên hội thoại.

        Chỉ là giá trị hiển thị - khi có câu hỏi đầu tiên, tiêu đề sẽ được thay
        bằng chính câu hỏi đó (xem ``ChatAskView._persist``).
        """
        return f"Hội thoại {self.id}"
