from django.contrib import admin
from .models import LinhKien, SPEC_MODELS


def make_inline(model):
    return type(f"{model.__name__}Inline", (admin.StackedInline,), {
        "model": model, "extra": 0, "max_num": 1, "can_delete": False,
        "verbose_name": "Thông số", "verbose_name_plural": "Thông số",
    })


INLINES = {loai: make_inline(m) for loai, m in SPEC_MODELS.items()}


@admin.register(LinhKien)
class LinhKienAdmin(admin.ModelAdmin):
    list_display = ("ten", "loai", "hang", "gia_hien_tai", "gia_cu", "phan_tram_giam")
    list_filter = ("loai", "hang")
    search_fields = ("ten", "hang")
    list_per_page = 50

    def get_inline_instances(self, request, obj=None):
        if obj is None:          # đang tạo mới: chưa biết loại nên chưa hiện thông số
            return []
        inline = INLINES.get(obj.loai)
        return [inline(self.model, self.admin_site)] if inline else []
