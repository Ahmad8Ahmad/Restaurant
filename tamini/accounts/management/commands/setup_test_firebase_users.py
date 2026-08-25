"""
Management command: create (or update) Firebase Auth users for E2E testing.

Usage:
    python manage.py setup_test_firebase_users

Requires Firebase Admin SDK to be configured (FIREBASE_CREDENTIALS / FIREBASE_CREDENTIALS_FILE).
"""
import os
import sys

from django.core.management.base import BaseCommand


TEST_USERS = [
    {
        "email": "ahmad0944043511@gmail.com",
        "password": "Rand1234567890",
        "display_name": "Restaurant Owner",
        "email_verified": True,
    },
    {
        "email": "ahmad19.87@hotmail.com",
        "password": "Ahmad0944043511",
        "display_name": "Delivery Driver",
        "email_verified": True,
    },
]


class Command(BaseCommand):
    help = "Create Firebase Auth users for E2E testing"

    def handle(self, *args, **options):
        from tamini.firebase import initialize_firebase
        initialize_firebase()

        import firebase_admin
        if not firebase_admin._apps:
            self.stderr.write(self.style.ERROR(
                "Firebase Admin SDK not initialized. "
                "Set FIREBASE_CREDENTIALS or FIREBASE_CREDENTIALS_FILE."
            ))
            sys.exit(1)

        from firebase_admin import auth as fb_auth

        for u in TEST_USERS:
            try:
                existing = fb_auth.get_user_by_email(u["email"])
                # Update password if needed
                fb_auth.update_user(existing.uid, password=u["password"])
                self.stdout.write(self.style.SUCCESS(
                    f"Updated Firebase user: {u['email']} (uid={existing.uid})"
                ))
            except fb_auth.UserNotFoundError:
                created = fb_auth.create_user(
                    email=u["email"],
                    password=u["password"],
                    display_name=u["display_name"],
                    email_verified=u["email_verified"],
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Created Firebase user: {u['email']} (uid={created.uid})"
                ))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(
                    f"Error for {u['email']}: {exc}"
                ))

        self.stdout.write(self.style.SUCCESS("Done."))
