from rest_framework import serializers

from backend.users.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id',
            'email',
        )
        read_only_fields = (
            'id',
            'email',
        )
