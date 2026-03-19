"""Management command to create/update demo users for local QA and role checks.

This command is intended for development/staging usage where a predictable
set of users with different roles is required for UI/API access testing.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.users.models import UserRole


TEST_USERS = [
    {
        "username": "manager1",
        "email": "manager1@kapitan-trips.ru",
        "role": UserRole.MANAGER,
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "manager2",
        "email": "manager2@kapitan-trips.ru",
        "role": UserRole.MANAGER,
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "rop1",
        "email": "rop1@kapitan-trips.ru",
        "role": UserRole.HEAD,
        "is_staff": True,
        "is_superuser": False,
    },
    {
        "username": "admin1",
        "email": "admin1@kapitan-trips.ru",
        "role": UserRole.ADMIN,
        "is_staff": True,
        "is_superuser": False,
    },
]

"""Static demo user presets created by the command.

Each entry defines identity and permission flags that are synchronized on each
run to keep local test data consistent.
"""


class Command(BaseCommand):
    """Create or update a predefined set of role-based test users.

    Behavior:
    - Creates users when they do not exist.
    - Updates email/role/staff/superuser flags when users already exist.
    - Sets password for newly created users and optionally for existing users.
    """

    help = "Create or update test users (manager/head/admin)"

    def add_arguments(self, parser):
        """Register CLI arguments for password strategy."""
        parser.add_argument(
            "--password",
            default="Kapitan123!",
            help="Password for all test users (default: Kapitan123!)",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Reset passwords for existing test users",
        )

    def handle(self, *args, **options):
        """Execute user synchronization and print per-user status."""
        User = get_user_model()
        password = options["password"]
        reset_password = options["reset_password"]

        created_count = 0
        updated_count = 0

        for item in TEST_USERS:
            user, created = User.objects.get_or_create(
                username=item["username"],
                defaults={
                    "email": item["email"],
                    "role": item["role"],
                    "is_staff": item["is_staff"],
                    "is_superuser": item["is_superuser"],
                    "is_active": True,
                },
            )

            user.email = item["email"]
            setattr(user, "role", item["role"])
            user.is_staff = item["is_staff"]
            user.is_superuser = item["is_superuser"]
            user.is_active = True

            if created or reset_password:
                user.set_password(password)

            user.save()

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created: {item['username']} ({item['role']})"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"Updated: {item['username']} ({item['role']})"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created_count}, updated={updated_count}, password_reset={'yes' if reset_password else 'no'}"
            )
        )
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Test users for login"))
        for item in TEST_USERS:
            self.stdout.write(
                f"  - {item['username']} / {password} ({item['role']})"
            )
