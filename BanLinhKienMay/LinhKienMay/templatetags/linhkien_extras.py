"""Bo loc template rieng cho app LinhKienMay.

Dung trong template:
    {% load linhkien_extras %}
    {{ p.gia_hien_tai|vnd }}đ   ->  1.000.000đ

Tai sao khong dung floatformat:"0g" co san: dau phan cach cua "0g" phu
thuoc locale trong settings (muc mac dinh tieng Anh cho dau phay, khong
phai dau cham). Bo loc nay luon cho dau cham kieu Viet Nam, khong phu
thuoc settings.
"""
from django import template

register = template.Library()

@register.filter
def vnd(value):
    """So tien -> chuoi co dau cham moi 3 so. Vd: 1000000 -> '1.000.000'.
    Gia tri khong phai so thi tra nguyen ve (khong lam vo template)."""
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return value
    return f"{n:,}".replace(",", ".")