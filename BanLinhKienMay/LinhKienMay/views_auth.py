"""Đăng ký / đăng nhập / đăng xuất + trang lịch sử build của tôi.

Đặt file này cạnh views.py (không cần sửa views.py cho phần auth).
Khai báo URL trong LinhKienMay/urls.py (xem file urls.py kèm theo).
"""
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from .forms import DangKyForm

def dang_ky(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = DangKyForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # đăng ký xong đăng nhập luôn
            return redirect("home")
    else:
        form = DangKyForm()
    return render(request, "LinhKienMay/dang_ky.html", {"form": form})

def dang_nhap(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(request.POST.get("next") or "home")
    else:
        form = AuthenticationForm(request)
    return render(request, "LinhKienMay/dang_nhap.html", {"form": form})

@require_POST
def dang_xuat(request):
    logout(request)
    return redirect("home")