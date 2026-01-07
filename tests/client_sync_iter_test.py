import inspect

import pytest

from dataroom_client.dataroom_client.client import DataRoomClientSync


@pytest.mark.django_db
def test_sync_get_images_iter_returns_blocking_iterator(DataRoom, all_images):
    sync_client = DataRoomClientSync(api_url=DataRoom.api_url, api_key=DataRoom.api_key)

    iterator = sync_client.get_images_iter(fields=["id"])  # should be a normal iterator

    assert not inspect.isawaitable(iterator)
    assert not hasattr(iterator, "__aiter__")

    ids = [item["id"] for item in iterator]

    # Order can vary; assert content equality
    expected_ids = {str(img.id) for img in all_images}
    assert set(ids) == expected_ids


@pytest.mark.django_db
def test_sync_get_images_iter_early_stop_and_followup_call(DataRoom, all_images):
    sync_client = DataRoomClientSync(api_url=DataRoom.api_url, api_key=DataRoom.api_key)

    iterator = sync_client.get_images_iter(fields=["id"])  # normal iterator

    first = next(iterator)
    assert "id" in first

    # Stop iteration early; ensure subsequent calls still work and do not hang
    images = sync_client.get_images(fields=["id"])  # list response via sync wrapper
    assert isinstance(images, list)
    assert len(images) == len(all_images)

