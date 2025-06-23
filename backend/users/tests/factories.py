import factory.fuzzy

from backend.users.models.user import User


class UserFactory(factory.django.DjangoModelFactory):
    email = factory.Sequence(lambda n: f"user_{n}@example.com")
    password = "123"

    class Meta:
        model = User
