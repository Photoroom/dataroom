"""``client.queries`` against the live API.

tests/queries_test.py already covers these endpoints with raw requests. These
tests exist because that does not pin the *client's* view of them: a field the
server renames, or a payload key the client spells differently, passes there and
fails in a user's notebook. Everything here goes over HTTP through the real
client, so the two halves of the interface are checked against each other.
"""

import uuid

import pytest

from dataroom_client import DataRoomError


@pytest.fixture
def slug():
    return f'q-{uuid.uuid4().hex[:8]}'


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_create_returns_the_stored_query(DataRoom, slug):
    created = await DataRoom.queries.create(
        slug=slug,
        name='Shutterstock',
        filters={'sources': 'shutterstock'},
        description='everything from shutterstock',
    )

    assert created['slug'] == slug
    assert created['name'] == 'Shutterstock'
    assert created['description'] == 'everything from shutterstock'


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_write_responses_omit_filters_but_reads_include_them(DataRoom, slug):
    """Pinning an asymmetry rather than endorsing it.

    create/update serialize through QueryCreateUpdateSerializer, whose `filters`
    field has no `source`, so it is dropped on output - the model stores them in
    `query_dict`. Reads go through QuerySerializer, which maps the two. So
    `created['filters']` is a KeyError while `get(...)['filters']` works.

    If that is ever made consistent, this test should fail and be deleted.
    """
    created = await DataRoom.queries.create(slug=slug, name='Q', filters={'sources': 'shutterstock'})
    assert 'filters' not in created

    updated = await DataRoom.queries.update(slug, name='Q2')
    assert 'filters' not in updated

    assert (await DataRoom.queries.get(slug))['filters'] == {'sources': 'shutterstock'}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_description_defaults_to_empty(DataRoom, slug):
    created = await DataRoom.queries.create(slug=slug, name='No description', filters={'sources': 'getty'})
    assert created['description'] == ''


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_round_trips_the_created_query(DataRoom, slug):
    await DataRoom.queries.create(slug=slug, name='Q', filters={'aspect_ratio__gt': 0.5})

    fetched = await DataRoom.queries.get(slug)
    assert fetched['slug'] == slug
    assert fetched['name'] == 'Q'
    assert fetched['filters'] == {'aspect_ratio__gt': 0.5}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_includes_created_queries_and_filter_is_an_alias(DataRoom):
    a, b = f'q-{uuid.uuid4().hex[:8]}', f'q-{uuid.uuid4().hex[:8]}'
    await DataRoom.queries.create(slug=a, name='Alpha', filters={'sources': 'shutterstock'})
    await DataRoom.queries.create(slug=b, name='Beta', filters={'sources': 'getty'})

    slugs = {q['slug'] for q in await DataRoom.queries.list()}
    assert {a, b} <= slugs

    assert {q['slug'] for q in await DataRoom.queries.filter()} == slugs


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_is_partial(DataRoom, slug):
    await DataRoom.queries.create(slug=slug, name='Before', filters={'sources': 'shutterstock'})

    assert (await DataRoom.queries.update(slug, name='After'))['name'] == 'After'

    # the field left out of the PATCH keeps its value rather than being cleared.
    # Read it back, because write responses do not carry filters - see
    # test_write_responses_omit_filters_but_reads_include_them.
    after_rename = await DataRoom.queries.get(slug)
    assert after_rename['name'] == 'After'
    assert after_rename['filters'] == {'sources': 'shutterstock'}

    await DataRoom.queries.update(slug, filters={'sources': 'getty'})
    refiltered = await DataRoom.queries.get(slug)
    assert refiltered['filters'] == {'sources': 'getty'}
    assert refiltered['name'] == 'After'


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_delete_removes_the_query(DataRoom, slug):
    await DataRoom.queries.create(slug=slug, name='Doomed', filters={'sources': 'shutterstock'})

    await DataRoom.queries.delete(slug)

    with pytest.raises(DataRoomError):
        await DataRoom.queries.get(slug)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_duplicate_slug_raises(DataRoom, slug):
    await DataRoom.queries.create(slug=slug, name='First', filters={'sources': 'shutterstock'})

    with pytest.raises(DataRoomError):
        await DataRoom.queries.create(slug=slug, name='Second', filters={'sources': 'getty'})


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_saved_query_filters_images(DataRoom, slug, image_logo, image_girl):
    """The point of a saved query: pass its slug instead of repeating filters.

    image_logo is 180x180 (aspect ratio 1.0), image_girl is 400x266 (~1.5), so a
    query on aspect ratio has to select exactly one of them.
    """
    await DataRoom.queries.create(slug=slug, name='Wide', filters={'aspect_ratio__gt': 1.2})

    listed = await DataRoom.images.list(query=slug)
    assert [i['id'] for i in listed] == [image_girl.id]

    assert await DataRoom.images.count(query=slug) == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_flat_query_methods_still_work(DataRoom, slug):
    """The pre-namespace spellings, which _compat.py keeps alive."""
    created = await DataRoom.create_query(slug=slug, name='Flat', filters={'sources': 'shutterstock'})
    assert created['slug'] == slug

    assert (await DataRoom.get_query(slug))['name'] == 'Flat'
    assert slug in {q['slug'] for q in await DataRoom.get_queries()}
    assert (await DataRoom.update_query(slug, name='Flat again'))['name'] == 'Flat again'
