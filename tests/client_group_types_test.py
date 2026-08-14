"""``client.group_types`` and ``client.roles`` against the live API.

groups_schema_test.py covers the GroupType/Role endpoints from the server side.
These go through the client, so the read and delete paths that no other client
test touches are pinned too.

The seed_group_types fixture in conftest re-creates zara_product, recolor_dresses
and pose_pair for every test, so the reads below have something known to find.
"""

import uuid

import pytest

from dataroom_client import DataRoomError


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_returns_the_seeded_types(DataRoom):
    names = {t['name'] for t in await DataRoom.group_types.list()}
    assert {'zara_product', 'recolor_dresses', 'pose_pair'} <= names


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_reports_roles_and_which_are_required(DataRoom):
    group_type = await DataRoom.group_types.get('pose_pair')

    assert group_type['name'] == 'pose_pair'
    # roles read back as {'role': <name>, 'is_required': <bool>} pairs, built from
    # the GroupTypeRole through-table. pose_pair seeds from/to, both required.
    required = {r['role'] for r in group_type['roles'] if r['is_required']}
    assert required == {'from', 'to'}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_unknown_type_raises(DataRoom):
    with pytest.raises(DataRoomError):
        await DataRoom.group_types.get(f'absent-{uuid.uuid4().hex[:8]}')


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_create_then_delete_a_group_type(DataRoom):
    name = f'gt_{uuid.uuid4().hex[:8]}'
    role = f'role_{uuid.uuid4().hex[:8]}'

    # a GroupType may only reference roles that already exist
    await DataRoom.roles.create(name=role)

    created = await DataRoom.group_types.create(
        name=name,
        roles=[{'role': role, 'is_required': True}],
        description='temporary',
    )
    assert created['name'] == name
    assert created['roles'] == [{'role': role, 'is_required': True}]

    await DataRoom.group_types.delete(name)

    assert name not in {t['name'] for t in await DataRoom.group_types.list()}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_create_then_delete_a_role(DataRoom):
    name = f'role_{uuid.uuid4().hex[:8]}'

    created = await DataRoom.roles.create(name=name, description='temporary')
    assert created['name'] == name
    assert name in {r['name'] for r in await DataRoom.roles.list()}

    await DataRoom.roles.delete(name)

    assert name not in {r['name'] for r in await DataRoom.roles.list()}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_flat_group_type_and_role_methods_still_work(DataRoom):
    """The pre-namespace spellings, which _compat.py keeps alive."""
    assert 'zara_product' in {t['name'] for t in await DataRoom.get_group_types()}
    assert (await DataRoom.get_group_type('zara_product'))['name'] == 'zara_product'

    name = f'gt_{uuid.uuid4().hex[:8]}'
    gt_role = f'role_{uuid.uuid4().hex[:8]}'
    await DataRoom.create_role(name=gt_role)
    await DataRoom.create_group_type(name=name, roles=[{'role': gt_role}])
    await DataRoom.delete_group_type(name)
    assert name not in {t['name'] for t in await DataRoom.get_group_types()}

    role = f'role_{uuid.uuid4().hex[:8]}'
    await DataRoom.create_role(name=role)
    await DataRoom.delete_role(role)
    assert role not in {r['name'] for r in await DataRoom.get_roles()}
