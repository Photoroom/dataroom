from pathlib import Path
import pytest
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile

from backend.users.models.token import Token

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS
from backend.dataroom.utils.disable_signals import DisableSignals
from backend.users.models.user import User
from dataroom_client import DataRoomClient, DataRoomFile

from . import vectors


@pytest.fixture(autouse=True, scope="function")
def setup():
    # run before each test
    if OS.client.indices.exists(index=OSImage.INDEX):
        # delete the index
        OS.client.indices.delete(index=OSImage.INDEX)
    # create the index
    OS.client.indices.create(
        index=OSImage.INDEX,
        body=OSImage.INDEX_SETTINGS,
    )


@pytest.fixture
def tests_path():
    return Path(__file__).resolve().parent


@pytest.fixture
def user_with_no_permission():
    return User.objects.create_user("user_with_no_permission@example.com", "123")


@pytest.fixture
def user():
    user = User.objects.create_user("user@example.com", "123")
    permission = Permission.objects.get(codename='dataroom_access')
    user.user_permissions.add(permission)
    return user


@pytest.fixture
def user2():
    user2 = User.objects.create_user("user2@example.com", "123")
    permission = Permission.objects.get(codename='dataroom_access')
    user2.user_permissions.add(permission)
    return user2


@pytest.fixture
def token(user):
    return Token.objects.create(user=user)


@pytest.fixture
def readonly_token(user):
    return Token.objects.create(user=user, is_readonly=True)


@pytest.fixture
def token2(user2):
    return Token.objects.create(user=user2)


@pytest.fixture
def DataRoom(live_server, token):
    client = DataRoomClient(
        api_url=live_server.url + "/api/",
        api_key=token.key,
    )
    client._test_user = token.user
    return client


@pytest.fixture
def DataRoom2(live_server, token2):
    client = DataRoomClient(
        api_url=live_server.url + "/api/",
        api_key=token2.key,
    )
    client._test_user = token2.user
    return client


@pytest.fixture
def DataRoomReadOnly(live_server, readonly_token):
    client = DataRoomClient(
        api_url=live_server.url + "/api/",
        api_key=readonly_token.key,
    )
    client._test_user = readonly_token.user
    return client


@pytest.fixture
def os_image(user):
    image = OSImage(
        id='test-image',
        author=user.email,
        source='test',
        image='images/test-image/original.png',
        image_hash='sha256:123test',
        width=10,
        height=10,
        short_edge=10,
        pixel_count=100,
        aspect_ratio=1.0,
        aspect_ratio_fraction="1:1",
    )
    image.create()
    return image


def _create_image(DataRoom, image_path, vector=None):
    dr_file = DataRoomFile.from_path(image_path)
    # disable signals to avoid calling an external API for the embeddings
    with DisableSignals():
        image_name = str(image_path).split('/')[-1].split('.')[0]
        image = OSImage(
            id=f'test-{image_name}',
            author=DataRoom._test_user.email,
            source='test',
            image_file=ContentFile(dr_file.bytes_io.read(), name=dr_file.filename),
            coca_embedding_exists=True,
            coca_embedding_author=DataRoom._test_user.email,
            coca_embedding_vector=vector,
        )
        image.create()
        OS.client.indices.refresh(index=OSImage.INDEX)
        image.update_thumbnail()

    return image


@pytest.fixture
def image_logo(DataRoom, tests_path):
    # 180x180, 1:1, 1.0
    return _create_image(DataRoom, tests_path / 'images/logo.png', vector=vectors.image_logo_vector)


@pytest.fixture
def image_logo_alt(DataRoom, tests_path):
    # 180x180, 1:1, 1.0
    return _create_image(DataRoom, tests_path / 'images/logo_alt.png', vector=vectors.image_logo_alt_vector)


@pytest.fixture
def image_logo_small(DataRoom, tests_path):
    # 180x180, 1:1, 1.0
    return _create_image(DataRoom, tests_path / 'images/logo_small.png', vector=vectors.image_logo_small_vector)


@pytest.fixture
def image_girl(DataRoom, tests_path):
    # 400x266, 9:8, 1.5037
    return _create_image(DataRoom, tests_path / 'images/girl.jpg', vector=vectors.image_girl_vector)


@pytest.fixture
def image_perfume(DataRoom, tests_path):
    # 120x160, 3:4, 0.75
    return _create_image(DataRoom, tests_path / 'images/perfume.jpg', vector=vectors.image_perfume_vector)


@pytest.fixture
def all_images(
    image_logo,
    image_logo_alt,
    image_logo_small,
    image_girl,
    image_perfume,
):
    return [
        image_logo,
        image_logo_alt,
        image_logo_small,
        image_girl,
        image_perfume,
    ]
