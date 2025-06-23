from django.urls import include, path
from rest_framework.routers import DefaultRouter

from backend.api.datasets.views import DatasetViewSet
from backend.api.images.views import ImageViewSet
from backend.api.opensearch.views import OpenSearchAPIView
from backend.api.stats.views import StatsViewSet
from backend.api.tags.views import TagViewSet
from backend.api.tokens.views import TokenViewSet

app_name = "api"

router = DefaultRouter()
router.register(r'images', ImageViewSet, basename='images')
router.register(r'datasets', DatasetViewSet, basename='datasets')
router.register(r'tags', TagViewSet, basename='tags')
router.register(r'stats', StatsViewSet, basename='stats')
router.register(r'tokens', TokenViewSet, basename='tokens')


urlpatterns = [
    path('', include(router.urls)),
    path('opensearch/', OpenSearchAPIView.as_view(), name='opensearch'),
    path('opensearch/<path:path>/', OpenSearchAPIView.as_view(), name='opensearch'),
]
