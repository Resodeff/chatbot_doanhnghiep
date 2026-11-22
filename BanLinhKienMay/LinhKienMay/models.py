from django.db import models
from django.contrib.auth.models import AbstractUser

class LinhKien(models.Model):
    """Bảng cha: thông tin chung của mọi linh kiện."""

    LOAI = [
        ("CPU", "CPU"),
        ("MAIN", "Mainboard"),
        ("RAM", "RAM"),
        ("SSD", "SSD"),
        ("HDD", "HDD"),
        ("GPU", "Card đồ họa (VGA)"),
        ("PSU", "Nguồn (PSU)"),
        ("COOLER", "Tản nhiệt & quạt"),
        ("CASE", "Vỏ máy (Case)"),
    ]

    loai = models.CharField(max_length=10, choices=LOAI, db_index=True)
    ten = models.CharField(max_length=300)
    hang = models.CharField(max_length=50, blank=True)
    gia_hien_tai = models.DecimalField(max_digits=12, decimal_places=0)             # giá đang bán (VNĐ)
    gia_cu = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)  # giá niêm yết trước khi giảm
    phan_tram_giam = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    anh_dai_dien = models.URLField(max_length=1000, blank=True)

    class Meta:
        verbose_name = "Linh kiện"
        verbose_name_plural = "Linh kiện"
        ordering = ["loai", "gia_hien_tai"]
        constraints = [
            models.UniqueConstraint(fields=["loai", "ten"], name="uniq_linhkien_loai_ten"),
        ]

    def __str__(self):
        return self.ten

    @property
    def gia_giam(self):
        """Số tiền được giảm (VNĐ) = giá cũ - giá hiện tại."""
        if self.gia_cu and self.gia_cu > self.gia_hien_tai:
            return self.gia_cu - self.gia_hien_tai
        return None

    @property
    def spec(self):
        # related_name của bảng con = mã loại viết thường (cpu, main, ssd...)
        return getattr(self, self.loai.lower(), None)

    @property
    def tom_tat(self):
        try:
            s = self.spec
        except Exception:
            return ""
        return s.tom_tat() if s else ""

def _join(*parts):
    return " • ".join(str(p) for p in parts if p not in (None, "", False))

class CPU(models.Model):
    KIEU_BAN = [("BOX", "Box"), ("TRAY", "Tray")]
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="cpu")
    socket = models.CharField(max_length=20, blank=True)           # AM5, LGA1700, sTR5...
    so_nhan = models.PositiveSmallIntegerField(null=True, blank=True)
    so_luong = models.PositiveSmallIntegerField(null=True, blank=True)
    xung_nhip_ghz = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    xung_boost_ghz = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    bo_nho_dem_mb = models.PositiveSmallIntegerField(null=True, blank=True)
    kieu_ban = models.CharField(max_length=4, choices=KIEU_BAN, default="BOX")

    def tom_tat(self):
        return _join(self.socket,
                     f"{self.so_nhan} nhân {self.so_luong} luồng" if self.so_nhan else "",
                     f"boost {self.xung_boost_ghz}GHz" if self.xung_boost_ghz else "",
                     f"{self.bo_nho_dem_mb}MB cache" if self.bo_nho_dem_mb else "",
                     "Tray" if self.kieu_ban == "TRAY" else "")

class Mainboard(models.Model):
    KICH_THUOC = [("ATX", "ATX"), ("MATX", "Micro-ATX"), ("ITX", "Mini-ITX"), ("EATX", "E-ATX")]
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="main")
    socket = models.CharField(max_length=20, blank=True)
    chipset = models.CharField(max_length=30, blank=True)          # B650, Z890...
    kich_thuoc = models.CharField(max_length=5, choices=KICH_THUOC, blank=True)
    loai_ram = models.CharField(max_length=4, blank=True)          # DDR4 / DDR5
    wifi = models.BooleanField(default=False)

    def tom_tat(self):
        return _join(self.socket, self.chipset, self.get_kich_thuoc_display() if self.kich_thuoc else "",
                     self.loai_ram, "WiFi" if self.wifi else "")

class RAM(models.Model):
    DANG = [("PC", "RAM PC"), ("LAPTOP", "RAM Laptop")]
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="ram")
    dang = models.CharField(max_length=6, choices=DANG, default="PC")
    chuan = models.CharField(max_length=4, blank=True)             # DDR4 / DDR5
    dung_luong_gb = models.PositiveSmallIntegerField(null=True, blank=True)   # tổng bộ kit
    so_thanh = models.PositiveSmallIntegerField(default=1)
    toc_do_mhz = models.PositiveIntegerField(null=True, blank=True)

    def tom_tat(self):
        return _join(self.get_dang_display(), self.chuan,
                     f"{self.dung_luong_gb}GB ({self.so_thanh} thanh)" if self.dung_luong_gb else "",
                     f"{self.toc_do_mhz}MHz" if self.toc_do_mhz else "")


class SSD(models.Model):
    KET_NOI = [("NVME", "M.2 NVMe"), ("SATA", "SATA"), ("USB", "USB (di động)")]
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="ssd")
    chuan_ket_noi = models.CharField(max_length=5, choices=KET_NOI, blank=True)
    dung_luong_gb = models.PositiveIntegerField(null=True, blank=True)
    di_dong = models.BooleanField(default=False)                   # ổ di động (gắn ngoài)
    toc_do_doc_mbs = models.PositiveIntegerField(null=True, blank=True)

    def tom_tat(self):
        return _join(self.get_chuan_ket_noi_display() if self.chuan_ket_noi else "",
                     f"{self.dung_luong_gb}GB" if self.dung_luong_gb else "",
                     f"đọc {self.toc_do_doc_mbs}MB/s" if self.toc_do_doc_mbs else "")

class HDD(models.Model):
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="hdd")
    dung_luong_gb = models.PositiveIntegerField(null=True, blank=True)
    kich_thuoc = models.CharField(max_length=3, blank=True)        # 3.5 / 2.5
    toc_do_quay_rpm = models.PositiveIntegerField(null=True, blank=True)
    bo_nho_dem_mb = models.PositiveIntegerField(null=True, blank=True)
    di_dong = models.BooleanField(default=False)

    def tom_tat(self):
        return _join("Di động" if self.di_dong else "Gắn trong",
                     f"{self.dung_luong_gb}GB" if self.dung_luong_gb else "",
                     f"{self.kich_thuoc} inch" if self.kich_thuoc else "",
                     f"{self.toc_do_quay_rpm}RPM" if self.toc_do_quay_rpm else "")

class GPU(models.Model):
    HANG_CHIP = [("NVIDIA", "NVIDIA"), ("AMD", "AMD"), ("INTEL", "Intel")]
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="gpu")
    hang_chip = models.CharField(max_length=10, choices=HANG_CHIP, blank=True)
    dong_gpu = models.CharField(max_length=40, blank=True)         # RTX 5070 Ti, RX 7600...
    vram_gb = models.PositiveSmallIntegerField(null=True, blank=True)
    loai_vram = models.CharField(max_length=10, blank=True)        # GDDR6, GDDR7

    def tom_tat(self):
        return _join(self.hang_chip, self.dong_gpu,
                     f"{self.vram_gb}GB {self.loai_vram}".strip() if self.vram_gb else "")

class PSU(models.Model):
    KIEU_DAY = [("FULL", "Full modular"), ("SEMI", "Semi modular"), ("NON", "Non modular")]
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="psu")
    cong_suat_w = models.PositiveSmallIntegerField(null=True, blank=True)
    chuan_80plus = models.CharField(max_length=20, blank=True)     # Bronze, Gold...
    kieu_day = models.CharField(max_length=4, choices=KIEU_DAY, blank=True)

    def tom_tat(self):
        return _join(f"{self.cong_suat_w}W" if self.cong_suat_w else "",
                     f"80+ {self.chuan_80plus}" if self.chuan_80plus else "",
                     self.get_kieu_day_display() if self.kieu_day else "")

class TanNhiet(models.Model):
    KIEU = [("KHI", "Tản khí"), ("AIO", "Tản nước AIO"), ("QUAT", "Quạt")]
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="cooler")
    kieu = models.CharField(max_length=4, choices=KIEU, blank=True)
    kich_thuoc_rad_mm = models.PositiveSmallIntegerField(null=True, blank=True)   # 120/240/360...
    co_rgb = models.BooleanField(default=False)
    mau = models.CharField(max_length=20, blank=True)

    def tom_tat(self):
        return _join(self.get_kieu_display() if self.kieu else "",
                     f"{self.kich_thuoc_rad_mm}mm" if self.kich_thuoc_rad_mm else "",
                     "RGB" if self.co_rgb else "", self.mau)

class VoCase(models.Model):
    FORM = [("FULL", "Full tower"), ("MID", "Mid tower"), ("MINI", "Mini tower"), ("ITX", "ITX")]
    linhkien = models.OneToOneField(LinhKien, on_delete=models.CASCADE, primary_key=True, related_name="case")
    form = models.CharField(max_length=4, choices=FORM, blank=True)
    kich_thuoc_ho_tro = models.CharField(max_length=50, blank=True)   # "ATX,MATX,ITX"
    mau = models.CharField(max_length=20, blank=True)

    def tom_tat(self):
        return _join(self.get_form_display() if self.form else "",
                     f"hỗ trợ {self.kich_thuoc_ho_tro}" if self.kich_thuoc_ho_tro else "", self.mau)

# loại -> model con (dùng cho importer & admin)
SPEC_MODELS = {
    "CPU": CPU, "MAIN": Mainboard, "RAM": RAM, "SSD": SSD, "HDD": HDD,
    "GPU": GPU, "PSU": PSU, "COOLER": TanNhiet, "CASE": VoCase,
}


class User(AbstractUser):
    """Mở rộng User mặc định của Django."""

    ROLE = [
        ("khach", "Khách hàng"),
        ("nhan_vien", "Nhân viên"),
        ("admin", "Admin"),
    ]

    ho_ten = models.CharField(max_length=100, blank=True)
    so_dien_thoai = models.CharField(max_length=15, blank=True)
    dia_chi = models.TextField(blank=True)
    role = models.CharField(max_length=10, choices=ROLE, default="khach")

    class Meta:
        verbose_name = "Người dùng"
        verbose_name_plural = "Người dùng"

    def __str__(self):
        return self.username

class ChatLog(models.Model):
    """Lưu lịch sử từng tin nhắn trong hội thoại với chatbot."""

    ROLE = [
        ("user", "Khách"),
        ("assistant", "Chatbot"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="chat_logs",
        help_text="Null nếu khách chưa đăng nhập",
    )
    session_id = models.CharField(
        max_length=64, db_index=True,
        help_text="ID phiên chat — nhóm các tin nhắn cùng 1 cuộc trò chuyện",
    )
    role = models.CharField(max_length=9, choices=ROLE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lịch sử chat"
        verbose_name_plural = "Lịch sử chat"
        ordering = ["session_id", "created_at"]

    def __str__(self):
        return f"[{self.session_id}] {self.role}: {self.message[:50]}"

class AIModel(models.Model):
    """Cấu hình model AI chạy qua Ollama."""

    ollama_name = models.CharField(
        max_length=100,
        help_text="Tên model trong Ollama, vd: qwen3:4b-instruct-2507-q4_K_M",
    )
    mo_ta = models.CharField(max_length=200, blank=True)
    temperature = models.DecimalField(max_digits=4, decimal_places=2, default=0.3)
    num_ctx = models.PositiveIntegerField(default=4096)
    is_active = models.BooleanField(
        default=False,
        help_text="Chỉ 1 model được active tại 1 thời điểm",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "AI Model"
        verbose_name_plural = "AI Models"

    def __str__(self):
        return f"{self.ollama_name}{' ✓' if self.is_active else ''}"

    def save(self, *args, **kwargs):
        # Khi set is_active=True, tắt tất cả model khác
        if self.is_active:
            AIModel.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

class APIConfig(models.Model):
    """Cấu hình endpoint FastAPI trỏ đến Ollama."""

    model = models.ForeignKey(
        AIModel, on_delete=models.CASCADE,
        related_name="api_configs",
    )
    api_url = models.CharField(
        max_length=200, default="http://127.0.0.1:8001",
        help_text="URL của FastAPI server",
    )
    timeout = models.PositiveIntegerField(
        default=130,
        help_text="Thời gian chờ tối đa (giây)",
    )
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "API Config"
        verbose_name_plural = "API Configs"

    def __str__(self):
        return f"{self.api_url} → {self.model.ollama_name}{' ✓' if self.is_active else ''}"

    def save(self, *args, **kwargs):
        # Khi set is_active=True, tắt tất cả config khác
        if self.is_active:
            APIConfig.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)