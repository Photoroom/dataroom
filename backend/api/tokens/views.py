from rest_framework.viewsets import ModelViewSet

from backend.api.tokens.serializers import TokenSerializer
from backend.users.models.token import Token


class TokenViewSet(ModelViewSet):
    def get_serializer_class(self):
        return TokenSerializer

    def get_queryset(self):
        return Token.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        serializer.save(user=self.request.user)
