import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Tạo tài khoản admin nếu chưa có (chạy nhiều lần vẫn an toàn)"

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("ADMIN_USER", "resodeff"))
        parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD", "12345678"))
        parser.add_argument("--reset", action="store_true",
                            help="Nếu admin đã có thì đặt lại mật khẩu")

    def handle(self, *args, **opts):
        User = get_user_model()
        u, created = User.objects.get_or_create(
            username=opts["username"],
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created or opts["reset"]:
            u.is_staff = u.is_superuser = True
            u.set_password(opts["password"])
            u.save()
            self.stdout.write(self.style.SUCCESS(
                f"{'Đã tạo' if created else 'Đã đặt lại mật khẩu'} admin: {opts['username']}"))
        else:
            self.stdout.write(f"Admin '{opts['username']}' đã có, bỏ qua")