"""Management command to create or promote a user to superadmin.

Used for initial environment bootstrap and emergency admin recovery in local
or controlled environments.
"""

from __future__ import annotations

from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.users.models import UserRole


class Command(BaseCommand):
    """Create a superadmin account or update an existing user to superadmin."""

    help = "Create or update a superadmin user"

    def add_arguments(self, parser):
        """Register CLI arguments for superadmin identity and password."""
        parser.add_argument("--username", default="superadmin", help="Superadmin username")
        parser.add_argument("--email", default="superadmin@example.com", help="Superadmin email")
        parser.add_argument("--password", default=None, help="Superadmin password")

    def handle(self, *args, **options):
        """Validate inputs, ask for password if needed, and persist admin flags."""
        User = get_user_model()

        username = options["username"].strip()
        email = options["email"].strip()
        password = options.get("password")

        if not username:
            raise CommandError("Username cannot be empty")
        if not email:
            raise CommandError("Email cannot be empty")

        if not password:
            password = getpass("Password for superadmin: ").strip()
            if not password:
                raise CommandError("Password cannot be empty")

        user, created = User.objects.get_or_create(username=username, defaults={"email": email})

        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        setattr(user, "role", UserRole.ADMIN)
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created superadmin: {username}"))
        else:
            self.stdout.write(self.style.WARNING(f"Updated existing user as superadmin: {username}"))
