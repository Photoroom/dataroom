import datetime

import pytest
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from backend.users.models.user import User


@pytest.mark.django_db()
def test_email_is_saved_lowercase():
    """Tests that emails are always saved lowercase."""
    user = User.objects.create_user("User@eXamPLE.COM", "123")
    assert user.email == "user@example.com"
    user.delete()
    user = User.objects.create(email="User2@eXamPLE.COM", password="123")
    assert user.email == "user2@example.com"
    user.email = "User3@eXamPLE.COM"
    user.save()
    assert user.email == "user3@example.com"


@pytest.mark.django_db()
def test_email_is_unique():
    """Tests that two users with the same email cannot be created."""
    User.objects.create_user("user@example.com", "123")
    with pytest.raises(IntegrityError) as excinfo:
        User.objects.create_user("USER@Example.com", "123")
    assert "Key (email)=(user@example.com) already exists." in str(excinfo.value)


@pytest.mark.django_db()
def test_email_login_is_case_insensitive():
    """Tests that the email field is case-insensitive when logging in."""
    User.objects.create_user("user@example.com", "123")
    client = Client()

    login_successful = client.login(email="user@example.com", password="123")
    assert login_successful is True

    login_successful = client.login(email="User@eXamPLE.COM", password="123")
    assert login_successful is True

    login_successful = client.login(email="user@example.com", password="wrong")
    assert login_successful is False

    login_successful = client.login(email="other@example.com", password="123")
    assert login_successful is False


@pytest.mark.django_db()
def test_user_date_accessed_is_updated():
    """
    Tests that the User.date_accessed field is updated with today's date each time a request is made on a new day.
    """
    User.objects.create_user("user@example.com", "123", is_staff=True)

    today = timezone.now().date()
    yesterday = (timezone.now() - datetime.timedelta(days=1)).date()
    tomorrow = (timezone.now() + datetime.timedelta(days=1)).date()

    # initially it's None
    assert User.objects.get().date_accessed is None

    # accessing any page, should update the date with the current date, but not if it's the same
    client = Client()
    client.login(email="user@example.com", password="123")
    response = client.get(reverse('admin:index'))
    assert response.status_code == 200
    assert User.objects.get().date_accessed == today

    # if current date is older, date_accessed shouldn't update
    with freeze_time(yesterday):
        client.get("/")
        assert User.objects.get().date_accessed == today

    # if current date is in the future, it should update
    with freeze_time(tomorrow):
        client.get("/")
        assert User.objects.get().date_accessed == tomorrow
