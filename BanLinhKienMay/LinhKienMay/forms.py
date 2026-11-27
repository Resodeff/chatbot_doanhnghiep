"""Form đăng ký / đăng nhập — dùng form có sẵn của Django, chỉ thêm họ tên.

Đăng nhập dùng thẳng django.contrib.auth.forms.AuthenticationForm nên
không cần form riêng ở đây.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class DangKyForm(UserCreationForm):
    ho_ten = forms.CharField(max_length=100, required=False, label="Họ tên")

    class Meta:
        model = User
        fields = ("username", "ho_ten")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.ho_ten = self.cleaned_data.get("ho_ten", "")
        user.role = "khach"
        if commit:
            user.save()
        return user