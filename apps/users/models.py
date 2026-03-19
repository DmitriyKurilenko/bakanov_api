from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    MANAGER = "manager", "Менеджер"
    HEAD = "head", "РОП"
    ADMIN = "admin", "Админ"


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.MANAGER)

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"
