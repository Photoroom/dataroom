"""The pre-namespace flat client methods, kept for backward compatibility.

``client.get_datasets(...)`` is ``client.datasets.list(...)`` - only the
spelling is old. Every flat method is a delegate generated from
``_FLAT_METHODS`` below; each borrows its namespace method's signature and
docstring, so ``help()`` and notebook autocompletion keep showing the real
parameters. The four methods that were already deprecated keep their
implementations here: they get no namespace home and die with this layer.
"""

import inspect
import json as json_module
import logging

from .models import DataRoomError, DataRoomFile, arg_deprecation_msg
from .resources import _RESOURCES
from .resources.base import validate_vector

logger = logging.getLogger(__name__)

# flat method -> (namespace attribute, namespace method)
_FLAT_METHODS = {
    # images
    "get_images": ("images", "list"),
    "get_images_iter": ("images", "iter"),
    "get_random_images": ("images", "random"),
    "count_images": ("images", "count"),
    "get_image": ("images", "get"),
    "create_image": ("images", "create"),
    "create_images": ("images", "create_many"),
    "update_image": ("images", "update"),
    "update_images": ("images", "update_many"),
    "delete_image": ("images", "delete"),
    "get_image_similarity": ("images", "similarity"),
    "get_similar_images": ("images", "similar"),
    "get_related_images": ("images", "related"),
    "delete_image_latent": ("images", "delete_latent"),
    "aggregate_images": ("images", "aggregate"),
    "bucket_images": ("images", "bucket"),
    "get_image_groups": ("images", "groups"),
    # tags
    "get_tags": ("tags", "list"),
    "get_tag": ("tags", "get"),
    "create_tag": ("tags", "create"),
    "tag_images": ("tags", "apply"),
    # roles
    "get_roles": ("roles", "list"),
    "create_role": ("roles", "create"),
    "delete_role": ("roles", "delete"),
    # group types
    "get_group_types": ("group_types", "list"),
    "get_group_type": ("group_types", "get"),
    "create_group_type": ("group_types", "create"),
    "delete_group_type": ("group_types", "delete"),
    # groups
    "get_groups": ("groups", "list"),
    "get_group": ("groups", "get"),
    "update_group": ("groups", "update"),
    "delete_group": ("groups", "delete"),
    "get_group_members": ("groups", "members"),
    "upsert_group": ("groups", "upsert"),
    "create_groups": ("groups", "create_many"),
    "delete_groups": ("groups", "delete_many"),
    # queries
    "get_queries": ("queries", "list"),
    "get_query": ("queries", "get"),
    "create_query": ("queries", "create"),
    "update_query": ("queries", "update"),
    # datasets
    "get_datasets": ("datasets", "list"),
    "get_dataset": ("datasets", "get"),
    "create_dataset": ("datasets", "create"),
    "update_dataset": ("datasets", "update"),
    "delete_dataset": ("datasets", "delete"),
    "add_dataset_groups": ("datasets", "add_groups"),
    "remove_dataset_groups": ("datasets", "remove_groups"),
    "add_dataset_images": ("datasets", "add_images"),
    "freeze_dataset": ("datasets", "freeze"),
    "unfreeze_dataset": ("datasets", "unfreeze"),
    "copy_dataset": ("datasets", "copy"),
}


class FlatAPI:
    """Mixin for ``DataRoomClient``: the flat aliases of the namespace methods."""

    # ---- deprecated endpoints, flat-only: no namespace home --------------

    async def add_image_attributes(
        self,
        image_id: str,
        attributes: dict,
    ) -> dict:
        """
        DEPRECATED: switch to ``client.images.update(image_id, attributes={...})``.
        Your attributes are merged into the existing ones, exactly like before.

        Update attributes of an image, merging them with the existing attributes.

        @param image_id: The UUID of the image to update.
        @param attributes: A dictionary of attributes to associate with the image.
        @return: A dictionary representing the updated image.
        """
        logger.warning(
            'add_image_attributes() is deprecated and will stop working in a future release. '
            'Switch to client.images.update(image_id, attributes={...}) - '
            'your attributes are merged into the existing ones, exactly like before.'
        )

        return await self._make_request(
            url=f"images/{image_id}/add_attributes/",
            method="PUT",
            json={
                "attributes": attributes,
            },
        )

    async def add_image_attributes_in_bulk(
        self,
        ids_to_attributes: dict[str, dict],
    ) -> list[dict]:
        """
        DEPRECATED: switch to
        ``client.images.update_many([{"id": ..., "attributes": {...}}, ...])``.
        Attributes are merged into the existing ones, exactly like before.

        Update attributes of a list of images, merging them with the existing attributes.

        @param ids_to_attributes: A dictionary mapping image IDs to dictionaries of attributes.
        @return: A list of dictionaries representing the updated images.
        """
        logger.warning(
            'add_image_attributes_in_bulk() is deprecated and will stop working in a future release. '
            'Switch to client.images.update_many([{"id": ..., "attributes": {...}}, ...]) - '
            'attributes are merged into the existing ones, exactly like before.'
        )

        return await self._make_request(
            url=f"images/add_attributes_bulk/",
            method="POST",
            json=[
                {"image_id": key, "attributes": val}
                for key, val in ids_to_attributes.items()
            ],
        )

    async def set_image_latent(
        self,
        image_id: str,
        latent_file: DataRoomFile,
        latent_type: str,
        is_mask=None,
    ) -> dict:
        """
        DEPRECATED: switch to
        ``client.images.update(image_id, latents=[{"latent_type": ..., "file": ...}])``.
        Latents are merged, so the image's other latent types are kept.

        @param image_id: The UUID of the image to update.
        @param latent_file: A DataRoomFile object containing the latent data.
        @param latent_type: A string identifying the type of latent.
        @param is_mask: Deprecated parameter.
        @return: A dictionary representing the updated image.
        """
        logger.warning(
            'set_image_latent() is deprecated and will stop working in a future release. '
            'Switch to client.images.update(image_id, latents=[{"latent_type": ..., "file": ...}]).'
        )

        if not isinstance(latent_file, DataRoomFile):
            raise DataRoomError("Argument latent_file must be a DataRoomFile")

        if is_mask is not None:
            logger.warning(arg_deprecation_msg('is_mask'))

        json_data = {
            "latent_type": latent_type,
        }
        files = {
            "file": (
                latent_file.filename,
                latent_file.bytes_io,
                latent_file.content_type,
            ),
            "json": (None, json_module.dumps(json_data), "text/plain"),
        }
        return await self._make_request(
            url=f"images/{image_id}/set_latent/",
            method="POST",
            files=files,
        )

    async def set_image_coca_embedding(self, image_id: str, vector: str) -> dict:
        """
        DEPRECATED: switch to ``client.images.update(image_id, coca_embedding=vector)``.

        @param image_id: The UUID of the image to update.
        @param vector: A string representation of the 768-float embedding vector.
        @return: A dictionary representing the updated image.
        """
        logger.warning(
            'set_image_coca_embedding() is deprecated and will stop working in a future release. '
            'Switch to client.images.update(image_id, coca_embedding=vector).'
        )
        validate_vector(vector)
        return await self._make_request(
            url=f"images/{image_id}/",
            method="PUT",
            json={
                "coca_embedding": vector,
            },
        )



def _make_delegate(flat_name, ns_attr, method_name):
    def flat(self, *args, **kwargs):
        return getattr(getattr(self, ns_attr), method_name)(*args, **kwargs)

    ns_func = getattr(_RESOURCES[ns_attr], method_name)
    flat.__name__ = flat_name
    flat.__qualname__ = f"FlatAPI.{flat_name}"
    flat.__signature__ = inspect.signature(ns_func)
    doc = inspect.getdoc(ns_func) or ""
    flat.__doc__ = f"Flat alias of ``client.{ns_attr}.{method_name}()``.\n\n{doc}"
    return flat


for _flat, (_ns, _meth) in _FLAT_METHODS.items():
    setattr(FlatAPI, _flat, _make_delegate(_flat, _ns, _meth))
