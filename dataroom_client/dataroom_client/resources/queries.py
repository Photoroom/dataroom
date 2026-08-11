"""``client.queries`` - saved queries.

The flat client methods (``get_queries``, ``create_query``, ...) are thin
delegates to this class - see ``_compat.py``.
"""

from __future__ import annotations

from .base import Resource, dict_filter_none


class QueriesResource(Resource):
    """``client.queries``.

    Saved queries: store a set of image filters once under a slug, then pass
    ``query=<slug>`` to any image endpoint instead of repeating the filters.
    """

    async def list(self, limit: int = 1000) -> list[dict]:
        """
        Retrieves a list of queries.

        @param limit: The maximum number of queries to return.
        @return: A list of query dictionaries.
        """
        return await self._c._make_paginated_request(
            url="queries/",
            limit=limit,
        )

    # `filter` reads as intent when you pass criteria; same call as `list`.
    filter = list

    async def get(self, slug: str) -> dict:
        """
        Retrieves a single query by its slug.

        @param slug: The identifier for the query (e.g., "my-query").
        @return: A dictionary representing the query.
        """
        return await self._c._make_request(
            url=f"queries/{slug}/",
        )

    async def create(self, slug: str, name: str, filters: dict, description: str | None = None) -> dict:
        """
        Creates a new query.

        @param slug: The identifier for the query (e.g., "my-query").
        @param name: The display name of the query.
        @param filters: The filters for the query.
        @param description: An optional description for the query.
        @return: A dictionary representing the newly created query.
        """
        return await self._c._make_request(
            url="queries/",
            method="POST",
            json={
                "slug": slug,
                "name": name,
                "description": description if description else "",
                "filters": filters,
            },
        )

    async def delete(self, slug: str) -> None:
        """
        Deletes a query. Images are not affected - a query is only a stored set
        of filters.

        @param slug: The identifier for the query (e.g., "my-query").
        """
        return await self._c._make_request(url=f"queries/{slug}/", method="DELETE")

    async def update(
        self, slug: str, name: str | None = None, description: str | None = None, filters: dict | None = None
    ) -> dict:
        """
        Updates a query. Partial: fields you leave out are kept as they are.

        @param slug: The identifier for the query (e.g., "my-query").
        @param name: The display name of the query.
        @param description: An optional description for the query.
        @param filters: The filters for the query.
        @return: A dictionary representing the updated query.
        """
        return await self._c._make_request(
            url=f"queries/{slug}/",
            method="PATCH",
            json=dict_filter_none(
                {
                    "slug": slug,
                    "name": name,
                    "description": description,
                    "filters": filters,
                }
            ),
        )
