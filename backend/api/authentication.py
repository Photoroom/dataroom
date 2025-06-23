from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from backend.users.models.token import Token


class APITokenAuthentication(TokenAuthentication):
    model = Token  # custom Token model

    def authenticate(self, request):
        user_token_pair = super().authenticate(request)
        if user_token_pair is None:
            return None

        user, token = user_token_pair

        if token.is_readonly and request.method not in ['GET', 'HEAD', 'OPTIONS']:
            raise exceptions.PermissionDenied('This token is read-only')

        return user, token
