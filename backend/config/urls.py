from allauth.account import views as allauth_views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django_jinja import views as jinja_views
from drf_spectacular import views as spectacular

from backend.dataroom import views
from backend.users.views import UserLoginView

admin_title = "Admin Backend"
admin.site.site_header = admin_title
admin.site.site_title = admin_title
admin.site.index_title = admin_title

handler400 = jinja_views.BadRequest.as_view(tmpl_name="errors/400.jinja")
handler403 = jinja_views.PermissionDenied.as_view(tmpl_name="errors/403.jinja")
handler404 = jinja_views.PageNotFound.as_view(tmpl_name="errors/404.jinja")
handler500 = jinja_views.ServerError.as_view(tmpl_name="errors/500.jinja")

urlpatterns = []

if settings.DEBUG:
    urlpatterns += [
        path("400/", handler400),
        path("403/", handler403),
        path("404/", handler404),
        path("500/", handler500),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls)), *urlpatterns]

# media files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# deepscatter tiles
if settings.DEBUG:
    urlpatterns += static(settings.DEEPSCATTER_STATIC_URL, document_root=settings.DEEPSCATTER_STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += [
        path('api/schema/orval/', spectacular.SpectacularAPIView.as_view(), name='api_schema_orval'),
    ]

urlpatterns += [
    # allauth
    path("account/login/", view=RedirectView.as_view(pattern_name="account_login")),
    path("account/logout/", view=RedirectView.as_view(pattern_name="account_logout")),
    path("account/", include("allauth.urls")),
    path("login/", UserLoginView.as_view(), name="account_login"),
    path("logout/", allauth_views.logout, name="account_logout"),
    # API
    path("api/", include("backend.api.urls")),
    path('api/schema/', login_required(spectacular.SpectacularAPIView.as_view()), name='api_schema'),
    path('api/docs/', login_required(spectacular.SpectacularRedocView.as_view(url_name='api_schema')), name='api_docs'),
    # django admin
    path("admin-backend/login/", RedirectView.as_view(pattern_name='account_login')),
    path("admin-backend", RedirectView.as_view(pattern_name='admin:index')),
    path("admin-backend/", admin.site.urls),
    # The Single Page App should handle all other routes
    path("images/<str:image_id>", views.SPAView.as_view(), name="image_detail"),
    path("images/<str:image_id>/", views.SPAView.as_view()),
    path("", RedirectView.as_view(pattern_name="images"), name="index"),
    path("images", views.SPAView.as_view(), name="images"),
    re_path(r'^(?!\/(api|settings)).*$', views.SPAView.as_view()),  # catch all for SPA
]
