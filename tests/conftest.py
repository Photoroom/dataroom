import os
from pathlib import Path
import pytest
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.conf import settings

from backend.users.models.token import Token

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS
from backend.dataroom.utils.disable_signals import DisableSignals
from backend.users.models.user import User
from dataroom_client import DataRoomClient, DataRoomFile
from backend.dataroom.models.group import GroupType, GroupTypeRole, Role

from . import vectors

# Under pytest-xdist every worker gets its own OpenSearch index (pytest-django
# already gives each worker its own test database). The per-test setup fixture
# below drops and recreates OSImage.INDEX, so without this suffix parallel
# workers would clobber each other's index mid-test.
_XDIST_WORKER = os.environ.get('PYTEST_XDIST_WORKER')
if _XDIST_WORKER:
    settings.OPENSEARCH_IMAGES_INDEX_NAME = f'{settings.OPENSEARCH_IMAGES_INDEX_NAME}_{_XDIST_WORKER}'
    OSImage.INDEX = settings.OPENSEARCH_IMAGES_INDEX_NAME
    # image ids (and so their media paths) are deterministic across workers -
    # on a shared MEDIA_ROOT one worker can resurrect a file another worker
    # just permanently deleted
    settings.MEDIA_ROOT = Path(f'{settings.MEDIA_ROOT}_{_XDIST_WORKER}')


# GroupTypes used by tests. Domain-flavored names so the test fixtures don't
# look like a fixed taxonomy:
#   - zara_product        permissive type, optional roles only
#   - recolor_dresses     required ``main`` role + required metadata.author
#   - pose_pair           required from/to roles + required metadata.context
_SEED_TYPES = {
    'zara_product': {
        'metadata_schema': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {},
        },
        'roles': [('nobody', False), ('onhang', False), ('front', False), ('side', False)],
    },
    'recolor_dresses': {
        'metadata_schema': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['author'],
            'properties': {'author': {'type': 'string', 'maxLength': 128}},
        },
        'roles': [('member', False), ('main', True)],
    },
    'pose_pair': {
        'metadata_schema': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['context'],
            'properties': {'context': {'type': 'object'}},
        },
        'roles': [('from', True), ('to', True)],
    },
}


@pytest.fixture(autouse=True)
def seed_group_types(db):
    """Re-seed GroupType / Role / GroupTypeRole on every test.

    pytest-django flushes the DB between transaction-mode tests, so this
    fixture re-creates the test types and their allowed-role tables for any
    test that touches Group/Membership.
    """
    for type_name, spec in _SEED_TYPES.items():
        gt, _ = GroupType.objects.update_or_create(
            name=type_name,
            defaults={'metadata_schema': spec['metadata_schema']},
        )
        for role_name, is_required in spec['roles']:
            role, _ = Role.objects.get_or_create(name=role_name)
            GroupTypeRole.objects.update_or_create(
                group_type=gt,
                role=role,
                defaults={'is_required': is_required},
            )


_PRISTINE_MAPPING = None


def _create_os_index():
    OS.client.indices.create(
        index=OSImage.INDEX,
        body=OSImage.INDEX_SETTINGS,
    )
    # create acks before the shard is searchable - without the wait the next
    # doc GET can 503 with no_shard_available
    OS.client.cluster.health(index=OSImage.INDEX, wait_for_status='yellow', request_timeout=10)


@pytest.fixture(autouse=True, scope="session")
def os_index():
    # one index per worker for the whole session: index create/delete are
    # cluster-state updates the node applies serially, so doing them per test
    # both slows the suite down and times out under parallel workers
    global _PRISTINE_MAPPING
    if OS.client.indices.exists(index=OSImage.INDEX):
        OS.client.indices.delete(index=OSImage.INDEX)
    _create_os_index()
    _PRISTINE_MAPPING = OS.client.indices.get_mapping(index=OSImage.INDEX)[OSImage.INDEX]


@pytest.fixture(autouse=True, scope="function")
def setup(os_index):
    # each test still starts on a clean index; cleanup runs after the test
    yield
    if not OS.client.indices.exists(index=OSImage.INDEX):
        # the test deleted the index itself - restore it
        _create_os_index()
        return
    if OS.client.indices.get_mapping(index=OSImage.INDEX)[OSImage.INDEX] != _PRISTINE_MAPPING:
        # the test mapped extra fields (attributes tests) - mappings cannot be
        # removed, only a recreate resets them
        OS.client.indices.delete(index=OSImage.INDEX)
        _create_os_index()
        return
    OS.client.indices.refresh(index=OSImage.INDEX)
    if OS.client.count(index=OSImage.INDEX)['count'] > 0:
        OS.client.delete_by_query(
            index=OSImage.INDEX,
            body={"query": {"match_all": {}}},
            refresh=True,
            conflicts="proceed",
        )
        # merge the emptied segments away: deleted docs otherwise linger as
        # tombstones in the HNSW graph (kNN returns fewer than k hits), and
        # leftover segments shift the internal doc ids that break kNN
        # score ties, making result order differ from a fresh index
        OS.client.indices.forcemerge(index=OSImage.INDEX, max_num_segments=1)
        OS.client.indices.refresh(index=OSImage.INDEX)


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
