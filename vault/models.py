from django.db import models

from . import secure

PROFILE_AAD = b"stash-profile-v1"


class Profile(models.Model):
    """Single row: your name and greeting, stored encrypted."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    data_enc = models.BinaryField(null=True)

    @classmethod
    def load(cls) -> dict:
        row = cls.objects.filter(id=1).first()
        return secure.decrypt_json(row.data_enc, PROFILE_AAD) if row else {}

    @classmethod
    def save_data(cls, data: dict) -> None:
        cls.objects.update_or_create(id=1, defaults={"data_enc": secure.encrypt_json(data, PROFILE_AAD)})
