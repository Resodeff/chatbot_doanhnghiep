"""Tách thông số kỹ thuật từ tên sản phẩm crawl được (gearvn, phongvu).

Mọi hàm parse_* nhận (ten, mo_ta) và trả về dict thông số. Không tách được
thì để None -> cột tương ứng trong DB là NULL (không bịa dữ liệu).
"""
import re

# ---------- tiện ích ----------
def _num(s):
    return float(s.replace(",", "."))


def _find(pattern, text, flags=re.I):
    m = re.search(pattern, text, flags)
    return m if m else None


def _dung_luong_gb(text):
    """'1TB' -> 1000, '512GB' -> 512, '512G' -> 512 (lấy dung lượng đầu tiên)."""
    m = _find(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|T|G)\b", text)
    if not m:
        return None
    v = _num(m.group(1))
    return int(v * 1000) if m.group(2).upper() in ("TB", "T") else int(v)


def clean_ten(ten, hang):
    """Bỏ tiền tố khuyến mãi 'Giảm 15 %' và tiền tố 'Hãng Loại ' của phongvu."""
    t = re.sub(r"^\s*Giảm\s*\d+(?:[.,]\d+)?\s*%\s*", "", ten.strip(), flags=re.I)
    # phongvu: "Corsair Nguồn máy tính Corsair RM850x ..." -> "Corsair RM850x ..."
    m = re.match(
        r"^(?P<h>\S+(?: \S+)?)\s+(?:CPU|Mainboard|RAM (?:PC|laptop)|Ổ cứng(?: di động)?(?: SSD| HDD)?|"
        r"ổ cứng SSD|Card màn hình|Nguồn máy tính|Tản nhiệt (?:nước|khí)|Tản nước|Quạt tản nhiệt PC|"
        r"Quạt|Bộ Tản Nhiệt Nước|Case máy tính|Vỏ máy tính)\s+(?=\S)", t, flags=re.I)
    if m and hang and m.group("h").lower() == hang.lower():
        t = t[m.end():]
    return re.sub(r"\s{2,}", " ", t).strip()


# ---------- CPU ----------
SOCKET_RE = r"\b(AM[345]|sTR5|sTRX4|sWRX8|LGA ?(?:1700|1851|1200|1151|2066|4677|4189|1150)|(?:1700|1851|1200|1151))\b"

def parse_cpu(ten, mo_ta):
    t = f"{ten} {mo_ta}"
    d = {"socket": None, "so_nhan": None, "so_luong": None,
         "xung_nhip_ghz": None, "xung_boost_ghz": None, "bo_nho_dem_mb": None,
         "kieu_ban": "TRAY" if re.search(r"\btray\b", ten, re.I) else "BOX"}
    m = _find(SOCKET_RE, t)
    if m:
        s = m.group(1).upper().replace(" ", "")
        d["socket"] = s if s.startswith("LGA") or s.startswith("AM") else (
            s if s.startswith("S") else "LGA" + s)
        d["socket"] = d["socket"].replace("STR5", "sTR5").replace("STRX4", "sTRX4").replace("SWRX8", "sWRX8")
    m = _find(r"(\d+)\s*(?:nhân|cores?)\s*[/,-]?\s*(\d+)\s*(?:luồng|threads?)", t)
    if m:
        d["so_nhan"], d["so_luong"] = int(m.group(1)), int(m.group(2))
    m = _find(r"(\d+(?:[.,]\d+)?)\s*GHz\s*[-–/ ]*\s*(?:(?:Boost|Turbo)(?: tối đa| to| up to)?\s*)?(\d+(?:[.,]\d+)?)\s*GHz", t)
    if m:
        d["xung_nhip_ghz"], d["xung_boost_ghz"] = _num(m.group(1)), _num(m.group(2))
    else:
        m = _find(r"(?:Boost|Turbo)(?: tối đa| to| up to)?\s*(\d+(?:[.,]\d+)?)\s*GHz", t)
        if m:
            d["xung_boost_ghz"] = _num(m.group(1))
        m = _find(r"(\d+(?:[.,]\d+)?)\s*GHz", t)
        if m and not d["xung_boost_ghz"]:
            d["xung_nhip_ghz"] = _num(m.group(1))
    m = _find(r"(\d+)\s*MB(?!/s)", ten)
    if m:
        d["bo_nho_dem_mb"] = int(m.group(1))
    return d


# ---------- Mainboard ----------
def parse_mainboard(ten, mo_ta):
    t = f"{ten} {mo_ta}"
    d = {"chipset": None, "socket": None, "kich_thuoc": None, "loai_ram": None,
         "wifi": bool(_find(r"wi-?fi", t))}
    m = _find(r"\b(TRX50|WRX90|W790E?|X299|[ABHXZWQ]\d{2,3}E?)(?=[A-Z\-\s]|$)", ten, 0)
    if m:
        d["chipset"] = m.group(1).upper()
    # socket suy ra từ chipset
    c = d["chipset"] or ""
    if re.fullmatch(r"[ABX](320|350|450|550|570|620|650E?|670E?|840|850|870E?)|A520|A620|B450|B550|X570", c):
        d["socket"] = "AM4" if re.fullmatch(r"A320|B350|B450|B550|A520|X370|X470|X570", c) else "AM5"
    elif re.fullmatch(r"[HBZQ](610|660|760|690|790|810|860|890|670)|Z690|Z790|Z890|H610|B660|B760|B860|H810|Q670", c):
        d["socket"] = "LGA1851" if c in ("Z890", "B860", "H810") else "LGA1700"
    elif c in ("TRX50",):
        d["socket"] = "sTR5"
    m = _find(r"\bDDR([45])\b|\bD([45])\b", t)
    if m:
        d["loai_ram"] = "DDR" + (m.group(1) or m.group(2))
    if _find(r"\bITX\b", ten):
        d["kich_thuoc"] = "ITX"
    elif _find(r"\b(?:m-?atx|micro)\b", ten) or (c and _find(rf"{re.escape(c)}M\b", ten, 0)):
        d["kich_thuoc"] = "MATX"
    elif _find(r"\bE-?ATX\b", ten):
        d["kich_thuoc"] = "EATX"
    elif c:
        d["kich_thuoc"] = "ATX"
    return d


# ---------- RAM ----------
def parse_ram(ten, mo_ta):
    t = f"{ten} {mo_ta}"
    d = {"chuan": None, "dung_luong_gb": None, "so_thanh": 1, "toc_do_mhz": None,
         "dang": "LAPTOP" if _find(r"laptop|so-?dimm", t) else "PC"}
    m = _find(r"DDR([345])", t)
    if m:
        d["chuan"] = "DDR" + m.group(1)
    m = _find(r"\((\d+)\s*x\s*(\d+)\s*GB\)", ten)
    if m:
        d["so_thanh"], d["dung_luong_gb"] = int(m.group(1)), int(m.group(1)) * int(m.group(2))
    else:
        m = _find(r"(\d+)\s*GB", ten)
        if m:
            d["dung_luong_gb"] = int(m.group(1))
    m = _find(r"(\d{4,5})\s*MHz", t) or _find(r"bus\s*(\d{4,5})", t) or _find(r"\b(\d{4,5})\s*DDR[45]", t) \
        or _find(r"DDR[45]\s*(\d{4,5})\b", t)
    if m:
        d["toc_do_mhz"] = int(m.group(1))
    return d


# ---------- SSD / HDD ----------
def _di_dong(t):
    return bool(_find(r"di động|portable|passport|my book|one touch|external|storejet|\busb\b|thunderbolt|\bduo\b|"
                      r"\bT[579]\b|\bX\d{1,2}\b.*usb|ESD\d+", t))


def parse_ssd(ten, mo_ta):
    t = f"{ten} {mo_ta}"
    d = {"dung_luong_gb": _dung_luong_gb(ten) or _dung_luong_gb(mo_ta),
         "chuan_ket_noi": None, "di_dong": _di_dong(ten), "toc_do_doc_mbs": None}
    if d["di_dong"]:
        d["chuan_ket_noi"] = "USB"
    elif _find(r"nvme|m\.2|pcie", t):
        d["chuan_ket_noi"] = "NVME"
    elif _find(r"sata|2\.5", t):
        d["chuan_ket_noi"] = "SATA"
    m = _find(r"(?:up to\s*)?(\d{3,5})\s*MB/s", t)
    if m:
        d["toc_do_doc_mbs"] = int(m.group(1))
    return d


def parse_hdd(ten, mo_ta):
    t = f"{ten} {mo_ta}"
    d = {"dung_luong_gb": _dung_luong_gb(ten) or _dung_luong_gb(mo_ta), "kich_thuoc": None,
         "toc_do_quay_rpm": None, "bo_nho_dem_mb": None, "di_dong": _di_dong(ten)}
    m = _find(r"\b(3\.5|2\.5)\s*(?:inch|\"|”|in)?", t)
    if m:
        d["kich_thuoc"] = m.group(1)
    m = _find(r"(\d{4})\s*rpm", t)
    if m:
        d["toc_do_quay_rpm"] = int(m.group(1))
    m = _find(r"\b(\d{2,3})\s*MB\b", ten)
    if m:
        d["bo_nho_dem_mb"] = int(m.group(1))
    return d


# ---------- GPU ----------
def parse_gpu(ten, mo_ta):
    t = f"{ten} {mo_ta}"
    d = {"hang_chip": None, "dong_gpu": None, "vram_gb": None, "loai_vram": None}
    if _find(r"geforce|\brtx\b|\bgtx\b|quadro|nvidia", t):
        d["hang_chip"] = "NVIDIA"
    elif _find(r"radeon|\bRX\s?\d|\bamd\b", t):
        d["hang_chip"] = "AMD"
    elif _find(r"\barc\b|intel", t):
        d["hang_chip"] = "INTEL"
    m = _find(r"\b((?:RTX|GTX|GT)\s?(?:PRO\s)?\d{3,4}(?:\s?(?:Ti SUPER|Ti|SUPER))?|RX\s?\d{3,4}(?:\s?(?:XT|GRE))?|Arc\s?[AB]\d{3})", ten)
    if m:
        d["dong_gpu"] = re.sub(r"\s+", " ", m.group(1)).upper().replace("TI", "Ti").replace("SUPER", "SUPER")
    m = _find(r"\b(\d{1,3})\s*GB(?:\s*(GDDR\d+X?))?", t)
    if m:
        d["vram_gb"] = int(m.group(1))
        d["loai_vram"] = m.group(2).upper() if m.group(2) else None
    if not d["loai_vram"]:
        m = _find(r"GDDR\d+X?", t)
        d["loai_vram"] = m.group(0).upper() if m else None
    return d


# ---------- PSU ----------
def parse_psu(ten, mo_ta):
    t = f"{ten} {mo_ta}"
    d = {"cong_suat_w": None, "chuan_80plus": None, "kieu_day": None}
    m = _find(r"\b(\d{3,4})\s*w\b", ten) or _find(r"\b(\d{3,4})\s*w\b", t)
    if m:
        d["cong_suat_w"] = int(m.group(1))
    m = _find(r"(?:80\s*plus\s*|cybenetics\s*)?\b(white|bronze|silver|gold|platinum|titanium)\b", t)
    if m:
        d["chuan_80plus"] = m.group(1).capitalize()
    if _find(r"semi[\s-]?modular|bán modular", t):
        d["kieu_day"] = "SEMI"
    elif _find(r"non[\s-]?modular|dây dẹp", t) and not _find(r"full[\s-]?modular", t):
        d["kieu_day"] = "NON"
    elif _find(r"full[\s-]?modular|\bmodular\b", t):
        d["kieu_day"] = "FULL"
    return d


# ---------- Tản nhiệt / quạt ----------
def parse_cooler(ten, mo_ta):
    t = f"{ten}"
    d = {"kieu": None, "kich_thuoc_rad_mm": None, "co_rgb": bool(_find(r"rgb", t)), "mau": None}
    if _find(r"tản nhiệt nước|tản nước|\baio\b|liquid|kraken|\bLCD\b|galahad|capellix|titan|dashflow|(?:ML|LT|LS|LQ|ELITE|H)\s?\d{3}[ia]?\b.*(?:rgb|argb)|\b(?:240|280|360|420)\b", t) \
            and not _find(r"quạt|\bfan\b", t):
        d["kieu"] = "AIO"
    elif _find(r"quạt|\bfan\b|\bfans\b|bộ \d quạt", t):
        d["kieu"] = "QUAT"
    elif _find(r"tản nhiệt|tản khí|cooler|air|hyper|assassin|phantom|\bAK\d{3}|NH-", t):
        d["kieu"] = "KHI"
    m = _find(r"\b(120|140|240|280|360|420)\b", t)
    if m and d["kieu"] in ("AIO", "QUAT"):
        d["kich_thuoc_rad_mm"] = int(m.group(1))
    m = _find(r"\((Đen|Trắng|Xám|Hồng|Xanh|Bạc)[^)]*\)|\b(Đen|Trắng)\b", t)
    if m:
        d["mau"] = (m.group(1) or m.group(2)).capitalize()
    return d


# ---------- Case ----------
def parse_case(ten, mo_ta):
    t = f"{ten} {mo_ta}"
    d = {"form": None, "mau": None, "kich_thuoc_ho_tro": None}
    if _find(r"full[\s-]?tower|\bFT\b", t):
        d["form"] = "FULL"
    elif _find(r"mid[\s-]?tower|\bMT\b", t):
        d["form"] = "MID"
    elif _find(r"mini[\s-]?tower|\bmini\b|\bmatx\b|\bm-?atx\b", t):
        d["form"] = "MINI"
    elif _find(r"\bitx\b", t):
        d["form"] = "ITX"
    m = _find(r"\b(Đen|Trắng|Xám|Hồng|Xanh|Bạc)\b|\b(black|white)\b", ten)
    if m:
        v = (m.group(1) or m.group(2)).lower()
        d["mau"] = {"black": "Đen", "white": "Trắng"}.get(v, v.capitalize())
    sizes = []
    for k, rx in (("ATX", r"\bATX\b"), ("MATX", r"\bm-?atx\b|micro-?atx"), ("ITX", r"\bitx\b")):
        if _find(rx, ten):
            sizes.append(k)
    d["kich_thuoc_ho_tro"] = ",".join(sizes) or None
    return d


PARSERS = {
    "CPU": parse_cpu, "MAIN": parse_mainboard, "RAM": parse_ram, "SSD": parse_ssd, "HDD": parse_hdd,
    "GPU": parse_gpu,
    "PSU": parse_psu, "COOLER": parse_cooler, "CASE": parse_case,
}
