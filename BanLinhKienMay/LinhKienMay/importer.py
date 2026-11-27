"""Đọc CSV crawl -> danh sách dict sạch (chưa đụng tới Django/DB)."""
import csv
import re
import unicodedata

from .parsers import PARSERS, clean_ten

# tên file CSV -> mã loại trong LinhKien.LOAI
FILE_LOAI = {
    "cpu": "CPU", "mainboard": "MAIN", "ram": "RAM", "ssd": "SSD", "hdd": "HDD",
    "vga": "GPU", "psu": "PSU", "cooling": "COOLER", "case": "CASE",
}
BAD_NAME = re.compile(r"stock buffer|-\s*demo\s*$", re.I)   # hàng trưng bày / demo


def _nfc(s):
    return unicodedata.normalize("NFC", (s or "").strip())


def _int(s):
    try:
        return int(float(s)) if s not in (None, "") else None
    except ValueError:
        return None


def _dec(s):
    try:
        return float(s) if s not in (None, "") else None
    except ValueError:
        return None


def _key(ten):
    t = unicodedata.normalize("NFD", ten.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9]", "", t)


def read_file(path, loai):
    """Trả về (rows, skipped). rows = [(linhkien_dict, spec_dict)], đã gộp trùng tên (giữ giá thấp nhất)."""
    parser = PARSERS[loai]
    best, skipped, dup = {}, [], 0
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            ten_raw, hang = _nfc(r["ten"]), _nfc(r["hang"])
            mo_ta = _nfc(r["mo_ta_ngan"])
            gia = _int(r["gia_vnd"])
            # --- loại bỏ dòng rác ---
            if not gia or gia <= 0:
                skipped.append((ten_raw, "không có giá")); continue
            if (ten_raw.lower() == hang.lower()
                    or (len(ten_raw.split()) <= 2 and not re.search(r"\d", ten_raw))
                    or BAD_NAME.search(ten_raw)):
                skipped.append((ten_raw, "tên không hợp lệ")); continue

            ten = clean_ten(ten_raw, hang)[:300]
            gia_cu = _int(r["gia_cu_vnd"])
            if gia_cu and gia_cu <= gia:          # giá cũ vô nghĩa
                gia_cu = None
            lk = {
                "loai": loai, "ten": ten, "hang": hang[:50],
                "gia_hien_tai": gia, "gia_cu": gia_cu,
                "phan_tram_giam": _dec(r["giam_phan_tram"]) if gia_cu else None,
                "anh_dai_dien": (r.get("anh_dai_dien") or "").strip()[:1000],
            }
            spec = parser(ten_raw, mo_ta)          # parse trên tên gốc (còn chữ 'Tản nước', 'Quạt'...)
            k = _key(ten)
            if k in best:                          # cùng sản phẩm xuất hiện nhiều lần -> giữ giá thấp nhất
                dup += 1
                if gia >= best[k][0]["gia_hien_tai"]:
                    continue
            best[k] = (lk, spec)
    return list(best.values()), skipped, dup
