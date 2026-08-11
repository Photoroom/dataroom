"""Client SDK tests for groups + memberships.

Mirrors the pattern of other client_*_test.py files: async, uses the DataRoom
fixture, raises DataRoomError on validation failures.
"""

import pytest
from dataroom_client import DataRoomError


# ----------------------------------------------------------------------
# upsert_group — create path
# ----------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.django_db
async def test_upsert_creates_product_group(DataRoom):
    g = await DataRoom.upsert_group(name="zara_01455460", type="zara_product")
    assert g["type"] == "zara_product"
    assert g["name"] == "zara_01455460"

    fetched = await DataRoom.get_group(g["id"])
    assert fetched["id"] == g["id"]


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_dataset_requires_author_metadata(DataRoom):
    with pytest.raises(DataRoomError) as exc:
        await DataRoom.upsert_group(name="ds_no_author", type="recolor_dresses", metadata={})
    assert "metadata" in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_dataset_with_author_succeeds(DataRoom, image_logo):
    g = await DataRoom.upsert_group(
        name="ds_with_author",
        type="recolor_dresses",
        metadata={"author": "alice"},
        members=[{"image_id": image_logo.id, "role": "main"}],
    )
    assert g["type"] == "recolor_dresses"


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_relationship_requires_context(DataRoom):
    with pytest.raises(DataRoomError):
        await DataRoom.upsert_group(name="rel_bad", type="pose_pair", metadata={})


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_unknown_type_rejected(DataRoom):
    with pytest.raises(DataRoomError):
        await DataRoom.upsert_group(name="bad_type", type="mystery")


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_list_groups_filtered_by_type(DataRoom, image_logo):
    await DataRoom.upsert_group(name="p_one", type="zara_product")
    await DataRoom.upsert_group(name="p_two", type="zara_product")
    await DataRoom.upsert_group(
        name="ds_one",
        type="recolor_dresses",
        metadata={"author": "a"},
        members=[{"image_id": image_logo.id, "role": "main"}],
    )

    products = await DataRoom.get_groups(type="zara_product")
    datasets = await DataRoom.get_groups(type="recolor_dresses")
    assert {g["name"] for g in products} >= {"p_one", "p_two"}
    assert {g["name"] for g in datasets} >= {"ds_one"}


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_group_type_immutable(DataRoom):
    g = await DataRoom.upsert_group(name="immutable_p", type="zara_product")
    with pytest.raises(DataRoomError):
        # PATCH guard: server rejects type changes.
        await DataRoom._make_request(
            url=f"groups/{g['id']}/",
            method="PATCH",
            json={"type": "recolor_dresses"},
        )


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_update_group_description(DataRoom):
    g = await DataRoom.upsert_group(name="desc_p", type="zara_product")
    updated = await DataRoom.update_group(group_id=g["id"], description="new desc")
    assert updated["description"] == "new desc"


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_delete_group_soft(DataRoom):
    g = await DataRoom.upsert_group(name="del_p", type="zara_product")
    await DataRoom.delete_group(g["id"])

    # not visible in list
    visible = await DataRoom.get_groups(type="zara_product")
    assert g["id"] not in {x["id"] for x in visible}


# ----------------------------------------------------------------------
# upsert_group — replace path
# ----------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.django_db
async def test_upsert_sets_members(DataRoom, image_logo):
    await DataRoom.upsert_group(
        name="members_p",
        type="zara_product",
        members=[
            {
                "image_id": image_logo.id,
                "role": "onhang",
                "metadata": {"source": "test"},
            }
        ],
    )

    g = next(x for x in await DataRoom.get_groups(type="zara_product") if x["name"] == "members_p")
    members = await DataRoom.get_group_members(g["id"])
    assert len(members) == 1
    assert members[0]["image_id"] == image_logo.id
    assert members[0]["role"] == "onhang"
    assert members[0]["metadata"] == {"source": "test"}


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_upsert_rejects_invalid_role(DataRoom, image_logo):
    with pytest.raises(DataRoomError):
        await DataRoom.upsert_group(
            name="bad_role_p",
            type="zara_product",
            members=[{"image_id": image_logo.id, "role": "not_a_real_role"}],
        )


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_upsert_drops_omitted_members(DataRoom, image_logo, image_logo_alt):
    await DataRoom.upsert_group(
        name="rm_p",
        type="zara_product",
        members=[
            {"image_id": image_logo.id, "role": "onhang"},
            {"image_id": image_logo_alt.id, "role": "front"},
        ],
    )
    # second upsert (same name) keeps only one
    await DataRoom.upsert_group(
        name="rm_p",
        type="zara_product",
        members=[{"image_id": image_logo.id, "role": "onhang"}],
    )

    g = next(x for x in await DataRoom.get_groups(type="zara_product") if x["name"] == "rm_p")
    members = await DataRoom.get_group_members(g["id"])
    assert [m["image_id"] for m in members] == [image_logo.id]


# ----------------------------------------------------------------------
# Image-side: get_image_groups
# ----------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.django_db
async def test_get_image_groups(DataRoom, image_logo):
    await DataRoom.upsert_group(
        name="hydrate_p",
        type="zara_product",
        members=[{"image_id": image_logo.id, "role": "onhang"}],
    )
    await DataRoom.upsert_group(
        name="hydrate_ds",
        type="recolor_dresses",
        metadata={"author": "alice"},
        members=[{"image_id": image_logo.id, "role": "main"}],
    )

    hits = await DataRoom.get_image_groups(image_logo.id)
    by_type = {h["group"]["type"]: h for h in hits}
    assert by_type["zara_product"]["role"] == "onhang"
    assert by_type["recolor_dresses"]["role"] == "main"
