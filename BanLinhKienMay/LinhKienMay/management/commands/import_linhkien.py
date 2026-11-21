import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from LinhKienMay.importer import FILE_LOAI, read_file
from LinhKienMay.models import LinhKien, SPEC_MODELS


class Command(BaseCommand):
    help = "Nhập dữ liệu linh kiện từ các file CSV crawl (cpu.csv, mainboard.csv, ...)"

    def add_arguments(self, parser):
        parser.add_argument("--dir", default="data", help="Thư mục chứa các file .csv (mặc định: data)")
        parser.add_argument("--clear", action="store_true", help="Xóa toàn bộ linh kiện cũ trước khi nhập")

    @transaction.atomic
    def handle(self, *args, **opts):
        folder = opts["dir"]
        if not os.path.isdir(folder):
            raise CommandError(f"Không thấy thư mục: {folder}")
        if opts["clear"]:
            n, _ = LinhKien.objects.all().delete()
            self.stdout.write(f"Đã xóa {n} bản ghi cũ")

        total_new = total_upd = 0
        for fname, loai in FILE_LOAI.items():
            path = os.path.join(folder, fname + ".csv")
            if not os.path.exists(path):
                self.stdout.write(self.style.WARNING(f"- bỏ qua {fname}.csv (không có file)"))
                continue
            rows, skipped, dup = read_file(path, loai)

            existing = {o.ten: o for o in LinhKien.objects.filter(loai=loai)}
            new_objs, new_specs, upd_objs = [], {}, []
            for lk, spec in rows:
                key = lk["ten"]
                if key in existing:                       # chạy lại: cập nhật giá/trạng thái
                    o = existing[key]
                    for f in ("gia_hien_tai", "gia_cu", "phan_tram_giam", "hang"):
                        setattr(o, f, lk[f])
                    upd_objs.append(o)
                else:
                    new_objs.append(LinhKien(**lk))
                    new_specs[key] = spec

            LinhKien.objects.bulk_create(new_objs, batch_size=500)
            if upd_objs:
                LinhKien.objects.bulk_update(
                    upd_objs, ["gia_hien_tai", "gia_cu", "phan_tram_giam", "hang"], batch_size=500)

            # lấy lại id theo tên rồi tạo bảng con
            ids = {o.ten: o.pk for o in LinhKien.objects.filter(loai=loai)}
            model = SPEC_MODELS[loai]
            spec_objs = [model(linhkien_id=ids[k], **self._clean(model, s))
                         for k, s in new_specs.items()]
            model.objects.bulk_create(spec_objs, batch_size=500)

            total_new += len(new_objs)
            total_upd += len(upd_objs)
            self.stdout.write(f"- {fname}.csv: +{len(new_objs)} mới, {len(upd_objs)} cập nhật, "
                              f"{len(skipped)} bỏ qua, {dup} trùng tên")
            for ten, why in skipped[:3]:
                self.stdout.write(f"    bỏ qua: {ten[:60]!r} ({why})")

        self.stdout.write(self.style.SUCCESS(f"Xong: {total_new} mới, {total_upd} cập nhật"))

    @staticmethod
    def _clean(model, spec):
        """None -> giá trị hợp lệ cho cột (CharField không null -> '', BooleanField -> False)."""
        out = {}
        for k, v in spec.items():
            field = model._meta.get_field(k)
            if v is None and not field.null:
                v = False if field.get_internal_type() == "BooleanField" else (
                    field.default if field.has_default() else "")
            out[k] = v
        return out
