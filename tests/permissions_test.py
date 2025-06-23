import pytest
from django.contrib.auth.models import User, Permission
from django.urls import reverse
from django.test import Client


@pytest.mark.django_db
def test_dataroom_access_permission(user_with_no_permission):
    user = user_with_no_permission

    # login as user without the permission
    client = Client()
    client.login(username=user.email, password='123')

    # can't access the protected views
    urls = [
        reverse('images'),
        reverse('api:api-root'),
        reverse('api:images-list'),
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 403

    # add the required permission to the user
    permission = Permission.objects.get(codename='dataroom_access')
    user.user_permissions.add(permission)
    user.refresh_from_db()

    # access granted
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200
