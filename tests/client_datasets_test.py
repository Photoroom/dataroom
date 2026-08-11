"""dataroom_client dataset methods, driven against a live server.

Datasets collect Groups of one immutable GroupType, so every test here seeds a
group type and adds real groups rather than loose images.
"""

import uuid

import pytest
from asgiref.sync import sync_to_async

from backend.dataroom.datasets.single_image import SINGLE_IMAGE_TYPE, ensure_single_image_type
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS
from dataroom_client import DataRoomError

TYPE = 'zara_product'


def _create_image(image_id: str):
    image = OSImage(
        id=image_id,
        author='tester',
        source='test',
        image=f'images/{image_id}/original.png',
        image_hash=f'sha256:{image_id}',
        width=10,
        height=10,
        short_edge=10,
        pixel_count=100,
        aspect_ratio=1.0,
        aspect_ratio_fraction='1:1',
    )
    image.create()
    OS.client.indices.refresh(index=OSImage.INDEX)
    return image


async def _group(DataRoom, name=None):
    group = await DataRoom.upsert_group(name=name or f'g_{uuid.uuid4().hex[:8]}', type=TYPE, metadata={})
    return group['id']


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_create_get_list_dataset(DataRoom, seed_group_types):
    assert await DataRoom.get_datasets() == []

    dataset = await DataRoom.create_dataset(name='Spring', slug='spring', type=TYPE)
    assert (dataset['slug'], dataset['version'], dataset['type']) == ('spring', 1, TYPE)

    # The version auto-increments per slug.
    second = await DataRoom.create_dataset(name='Spring 2', slug='spring', type=TYPE, description='next')
    assert second['version'] == 2
    assert second['description'] == 'next'

    fetched = await DataRoom.get_dataset('spring/2')
    assert fetched['name'] == 'Spring 2'

    # Listing returns every version, newest first within a slug.
    listed = await DataRoom.get_datasets(slug='spring')
    assert [d['slug_version'] for d in listed] == ['spring/2', 'spring/1']


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_dataset_cannot_change_type(DataRoom, seed_group_types):
    await DataRoom.create_dataset(name='Spring', slug='spring', type=TYPE)

    updated = await DataRoom.update_dataset('spring/1', name='Renamed', description='desc')
    assert (updated['name'], updated['description']) == ('Renamed', 'desc')

    # type is immutable once set; the server rejects a different one.
    with pytest.raises(DataRoomError):
        await DataRoom.update_dataset('spring/1', type='recolor_dresses')


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_group_membership_add_remove_revive(DataRoom, seed_group_types):
    await DataRoom.create_dataset(name='Spring', slug='spring', type=TYPE)
    group_id = await _group(DataRoom)

    await DataRoom.add_dataset_groups('spring/1', [group_id])
    members = await DataRoom.get_groups(dataset='spring/1')
    assert len(members) == 1

    # Removal soft-deletes the membership.
    await DataRoom.remove_dataset_groups('spring/1', [group_id])
    assert len(await DataRoom.get_groups(dataset='spring/1')) == 0

    # Re-adding revives the same membership rather than creating a second one.
    await DataRoom.add_dataset_groups('spring/1', [group_id])
    assert len(await DataRoom.get_groups(dataset='spring/1')) == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_add_group_of_wrong_type_is_rejected(DataRoom, seed_group_types):
    await DataRoom.create_dataset(name='Spring', slug='spring', type=TYPE)

    # A second type, with no required roles so the group can be created empty.
    await DataRoom.create_group_type(name='swatch', metadata_schema={'type': 'object', 'additionalProperties': True})
    other = await DataRoom.upsert_group(name=f'o_{uuid.uuid4().hex[:8]}', type='swatch', metadata={})

    with pytest.raises(DataRoomError):
        await DataRoom.add_dataset_groups('spring/1', [other['id']])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_freeze_blocks_membership_changes(DataRoom, seed_group_types):
    await DataRoom.create_dataset(name='Spring', slug='spring', type=TYPE)
    group_id = await _group(DataRoom)

    await DataRoom.freeze_dataset('spring/1')
    with pytest.raises(DataRoomError):
        await DataRoom.add_dataset_groups('spring/1', [group_id])

    await DataRoom.unfreeze_dataset('spring/1')
    await DataRoom.add_dataset_groups('spring/1', [group_id])
    assert len(await DataRoom.get_groups(dataset='spring/1')) == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_copy_clones_members_and_inherits_type(DataRoom, seed_group_types):
    await DataRoom.create_dataset(name='Spring', slug='spring', type=TYPE)
    group_id = await _group(DataRoom)
    await DataRoom.add_dataset_groups('spring/1', [group_id])

    copy = await DataRoom.copy_dataset('spring/1', name='Summer', slug='summer')
    assert copy['type'] == TYPE
    assert len(await DataRoom.get_groups(dataset=copy['slug_version'])) == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_add_dataset_images_wraps_each_image(DataRoom, seed_group_types):
    # The single_image GroupType must exist before a single_image dataset can be created.
    await sync_to_async(ensure_single_image_type)()
    await DataRoom.create_dataset(name='Loose', slug='loose', type=SINGLE_IMAGE_TYPE)

    image_ids = [uuid.uuid4().hex for _ in range(2)]
    for image_id in image_ids:
        await sync_to_async(_create_image)(image_id)

    result = await DataRoom.add_dataset_images('loose/1', image_ids)
    assert result['updated_count'] == len(image_ids)
    assert len(await DataRoom.get_groups(dataset='loose/1')) == len(image_ids)

    # Idempotent: re-adding revives rather than duplicating.
    again = await DataRoom.add_dataset_images('loose/1', image_ids)
    assert again['updated_count'] == 0
    assert len(await DataRoom.get_groups(dataset='loose/1')) == len(image_ids)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_delete_dataset(DataRoom, seed_group_types):
    await DataRoom.create_dataset(name='Spring', slug='spring', type=TYPE)
    await DataRoom.delete_dataset('spring/1')
    with pytest.raises(DataRoomError):
        await DataRoom.get_dataset('spring/1')


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_groups_expansion_via_dataset_filter(DataRoom, seed_group_types):
    await DataRoom.create_dataset(name='Spring', slug='spring', type=TYPE)
    group_id = await _group(DataRoom)
    await DataRoom.add_dataset_groups('spring/1', [group_id])

    image_id = uuid.uuid4().hex
    await sync_to_async(_create_image)(image_id)
    await DataRoom.upsert_group(
        group_id=group_id, name=f'g_{uuid.uuid4().hex[:8]}', type=TYPE, metadata={},
        members=[{'image_id': image_id, 'role': 'onhang'}],
    )

    # Unexpanded: no roles array.
    plain = await DataRoom.get_groups(dataset='spring/1')
    assert 'roles' not in plain[0]

    # Expanded: the members show up with their roles.
    expanded = await DataRoom.get_groups(dataset='spring/1', include_roles=True)
    roles = expanded[0]['roles']
    assert [(r['image_id'], r['role']) for r in roles] == [(image_id, 'onhang')]

    # return_roles narrows; a role nothing is assigned to yields an empty array.
    narrowed = await DataRoom.get_groups(dataset='spring/1', return_roles=['front'])
    assert narrowed[0]['roles'] == []

    # group-level expansion: which datasets contain each group.
    with_ds = await DataRoom.get_groups(dataset='spring/1', include_datasets=True)
    assert with_ds[0]['datasets'] == ['spring/1']
