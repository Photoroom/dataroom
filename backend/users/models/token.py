import binascii
import os

from django.db import models

from backend.common.base_model import BaseModel


class Token(BaseModel):
    key = models.CharField(max_length=40, unique=True)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    is_readonly = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    @classmethod
    def generate_key(cls):
        return binascii.hexlify(os.urandom(20)).decode()

    def __str__(self):
        return str(self.id)
