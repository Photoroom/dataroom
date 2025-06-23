from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm
from django.utils.translation import gettext_lazy as _

from .models.token import Token
from .models.user import User, UserManager


class UserEmailField(forms.EmailField):
    def to_python(self, value):
        return UserManager.normalize_email(value)


class UserChangeForm(DjangoUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
        field_classes = {"email": UserEmailField}


class UserCreationForm(DjangoUserCreationForm):
    """
    A form that creates a user, with no privileges, from the given email and password.
    """

    class Meta:
        model = User
        fields = ("email",)
        field_classes = {"email": UserEmailField}


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ("user", "date_created", "is_readonly")
    search_fields = ("user__email", "key")
    list_filter = ("is_readonly",)
    raw_id_fields = ("user",)
    readonly_fields = ("key",)


class TokenInline(admin.TabularInline):
    model = Token
    readonly_fields = ("key",)
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "date_accessed")}),
    )
    readonly_fields = ("last_login", "date_joined", "date_accessed")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    form = UserChangeForm
    add_form = UserCreationForm
    list_display = ("email", "first_name", "last_name", "date_accessed", "is_staff", "is_superuser")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("first_name", "last_name", "email")
    ordering = ("email",)
    filter_horizontal = (
        "groups",
        "user_permissions",
    )
    inlines = (TokenInline,)
