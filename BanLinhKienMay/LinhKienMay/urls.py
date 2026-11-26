from django.urls import path
from . import views
from . import views_auth

urlpatterns = [
    path("", views.home, name="home"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/linhkien/export/", views.export_linhkien, name="export_linhkien"),
    path("dang-ky/", views_auth.dang_ky, name="dang_ky"),
    path("dang-nhap/", views_auth.dang_nhap, name="dang_nhap"),
    path("dang-xuat/", views_auth.dang_xuat, name="dang_xuat"),
]