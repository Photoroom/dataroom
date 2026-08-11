"""Resource namespaces (client.datasets / groups / images / ...).

The namespaces own the endpoint implementations; the flat methods (get_datasets,
create_dataset, ...) are thin delegates kept for backward compatibility. The DataRoom
fixture is the async client, so its namespaces return awaitables. On DataRoomClientSync
the same namespaces block, wrapped by _SyncResource on the shared background loop.
"""

import uuid

import pytest

from dataroom_client import DataRoomClientSync

TYPE = 'zara_product'


@pytest.mark.django_db(transaction=True)
def test_namespaces_present_and_cached(DataRoom):
    for name in ('datasets', 'groups', 'images', 'roles', 'group_types', 'queries'):
        assert getattr(DataRoom, name) is getattr(DataRoom, name)  # cached, same instance


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_datasets_namespace_round_trip(DataRoom, seed_group_types):
    slug = f'ns-{uuid.uuid4().hex[:6]}'
    ds = await DataRoom.datasets.create(name='NS', slug=slug, type=TYPE)
    assert ds['slug_version'] == f'{slug}/1'

    listed = await DataRoom.datasets.list(slug=slug)
    assert any(d['slug_version'] == f'{slug}/1' for d in listed)
    assert (await DataRoom.datasets.get(f'{slug}/1'))['name'] == 'NS'

    # filter is an alias of list
    filtered = await DataRoom.datasets.filter(slug=slug)
    assert filtered[0]['slug_version'] == f'{slug}/1'

    g = await DataRoom.groups.upsert(name=f'g_{uuid.uuid4().hex[:8]}', type=TYPE, metadata={})
    await DataRoom.datasets.add_groups(f'{slug}/1', [g['id']])
    assert len(await DataRoom.datasets.groups(f'{slug}/1')) == 1
    assert (await DataRoom.datasets.get(f'{slug}/1'))['group_count'] == 1

    await DataRoom.datasets.delete(f'{slug}/1')


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_groups_namespace_bulk_and_expand(DataRoom, seed_group_types):
    slug = f'ns-{uuid.uuid4().hex[:6]}'
    await DataRoom.datasets.create(name='B', slug=slug, type=TYPE)
    specs = [{'name': f'ns_{uuid.uuid4().hex[:8]}', 'type': TYPE, 'members': []} for _ in range(3)]
    created = await DataRoom.groups.create_many(specs)
    assert len(created) == 3

    await DataRoom.datasets.add_groups(f'{slug}/1', [g['id'] for g in created])
    members = await DataRoom.groups.list(dataset=f'{slug}/1', include_datasets=True)
    assert len(members) == 3
    assert members[0]['datasets'] == [f'{slug}/1']

    # delete_many is the counterpart of create_many - one request, not one per group.
    deleted = await DataRoom.groups.delete_many([g['id'] for g in created])
    assert deleted == {'deleted_count': 3}
    assert await DataRoom.groups.list(dataset=f'{slug}/1') == []


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_roles_namespace(DataRoom, seed_group_types):
    await DataRoom.roles.create(name=f'r_{uuid.uuid4().hex[:6]}', description='x')
    names = {r['name'] for r in await DataRoom.roles.list()}
    assert 'onhang' in names  # seeded


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_flat_methods_still_work(DataRoom, seed_group_types):
    """Backward compatibility: the old flat calls are untouched."""
    slug = f'flat-{uuid.uuid4().hex[:6]}'
    ds = await DataRoom.create_dataset(name='F', slug=slug, type=TYPE)
    assert (await DataRoom.get_dataset(ds['slug_version']))['slug'] == slug
    await DataRoom.delete_dataset(ds['slug_version'])


@pytest.mark.django_db(transaction=True)
def test_sync_client_namespaces_block(live_server, token, seed_group_types):
    """The identical namespaces on DataRoomClientSync block and return values directly."""
    sync = DataRoomClientSync(api_url=live_server.url + '/api/', api_key=token.key)
    slug = f'sync-{uuid.uuid4().hex[:6]}'
    ds = sync.datasets.create(name='S', slug=slug, type=TYPE)
    assert ds['slug_version'] == f'{slug}/1'  # a dict came back - the call blocked
    assert sync.datasets.list(slug=slug)[0]['slug_version'] == f'{slug}/1'
    g = sync.groups.upsert(name=f'sync_{uuid.uuid4().hex[:8]}', type=TYPE, metadata={})
    sync.datasets.add_groups(f'{slug}/1', [g['id']])
    assert sync.datasets.get(f'{slug}/1')['group_count'] == 1
    sync.groups.delete_many([g['id']])
    sync.datasets.delete(f'{slug}/1')
