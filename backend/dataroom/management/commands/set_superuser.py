from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Promote a user to staff/superuser by email or username."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            help="Email of the user to promote",
        )
        parser.add_argument(
            "--username",
            help="Username of the user to promote",
        )
        parser.add_argument(
            "--staff-only",
            action="store_true",
            help="Only set is_staff (do not grant is_superuser)",
        )

    def handle(self, *args, **options):
        user_model = get_user_model()
        email = options.get("email")
        username = options.get("username")

        if not email and not username:
            raise CommandError("Provide --email or --username")

        try:
            user = user_model.objects.get(email=email) if email else user_model.objects.get(username=username)
        except user_model.DoesNotExist as exc:
            raise CommandError("User not found") from exc

        user.is_staff = True
        if not options.get("staff_only"):
            user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])

        role = "staff" if options.get("staff_only") else "staff+superuser"
        self.stdout.write(self.style.SUCCESS(f"User '{user}' promoted to {role}"))
