from rest_framework import serializers

from backend.users.models.token import Token


class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = ['id', 'key', 'is_readonly']
        read_only_fields = ['id', 'key']
