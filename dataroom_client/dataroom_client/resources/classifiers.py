"""``client.classifiers`` - versioned binary classifier definitions.

A classifier records which ``single_image`` datasets hold its positive and
negative examples. There is no model here yet: creating one and collecting
examples into it is the whole workflow this namespace covers.
"""

from __future__ import annotations

from .base import Resource, dict_filter_none

LABEL_CHUNK = 100

# The server caps scores per call (SCORES_BULK_LIMIT).
SCORES_CHUNK = 500


class ClassifiersResource(Resource):
    """``client.classifiers``.

    Addressed as ``slug/version``, like datasets. A version is a lock: work on
    it, lock it when it says what you want, and ``new_version`` carries on in a
    fresh one with its own copies of the owned example sets.
    """

    async def list(
        self, limit: int = 1000, slug: str = None, embedding_space: str = None, search: str = None
    ) -> list[dict]:
        """List classifiers, every version, newest version first within each slug."""
        params = dict_filter_none({"slug": slug, "embedding_space": embedding_space, "search": search})
        return await self._c._make_paginated_request(url="classifiers/", limit=limit, params=params or None)

    # `filter` reads as intent when you pass criteria; same call as `list`.
    filter = list

    async def get(self, slug_version: str) -> dict:
        """Retrieve a single classifier by its ``slug/version``."""
        return await self._c._make_request(url=f"classifiers/{slug_version}/")

    async def create(
        self,
        name: str,
        slug: str,
        description: str = None,
        extra_pos_datasets: list[str] = None,
        extra_neg_datasets: list[str] = None,
        embedding_space: str = None,
    ) -> dict:
        """Create a classifier. The slug must be free — carry on from an existing
        one with ``new_version``.

        Every classifier owns a positive and a negative ``single_image`` dataset,
        created here as ``<slug>-positives``/``<slug>-negatives``: they are what
        annotating writes to, are hidden from the datasets list, and are copied
        when a new version branches. ``extra_pos_datasets``/``extra_neg_datasets``
        borrow datasets somebody else curates; those are referenced, never copied
        or frozen.
        """
        return await self._c._make_request(
            url="classifiers/",
            method="POST",
            json=dict_filter_none(
                {
                    "name": name,
                    "slug": slug,
                    "description": description,
                    "extra_pos_datasets": list(extra_pos_datasets) if extra_pos_datasets is not None else None,
                    "extra_neg_datasets": list(extra_neg_datasets) if extra_neg_datasets is not None else None,
                    "embedding_space": embedding_space,
                }
            ),
        )

    async def update(
        self,
        slug_version: str,
        name: str = None,
        description: str = None,
        extra_pos_datasets: list[str] = None,
        extra_neg_datasets: list[str] = None,
        embedding_space: str = None,
    ) -> dict:
        """Update a classifier. Passing an extra-dataset list replaces that side's
        borrowed sets entirely; the owned ones are not editable here."""
        return await self._c._make_request(
            url=f"classifiers/{slug_version}/",
            method="PATCH",
            json=dict_filter_none(
                {
                    "name": name,
                    "description": description,
                    "extra_pos_datasets": list(extra_pos_datasets) if extra_pos_datasets is not None else None,
                    "extra_neg_datasets": list(extra_neg_datasets) if extra_neg_datasets is not None else None,
                    "embedding_space": embedding_space,
                }
            ),
        )

    async def delete(self, slug_version: str) -> None:
        """Delete one version of a classifier."""
        await self._c._make_request(url=f"classifiers/{slug_version}/", method="DELETE")

    async def lock(self, slug_version: str) -> None:
        """Make this version final: freeze it and its example datasets.

        Locking reaches the datasets on purpose — the examples live there, so
        without it labelling would keep changing what the locked version means.
        Carry on with ``new_version``.
        """
        await self._c._make_request(url=f"classifiers/{slug_version}/lock/", method="POST")

    async def unlock(self, slug_version: str) -> None:
        """Undo a lock, on the classifier and its example datasets."""
        await self._c._make_request(url=f"classifiers/{slug_version}/unlock/", method="POST")

    async def new_version(
        self,
        slug_version: str,
        copy_examples: bool = True,
        extra_pos_datasets: list[str] = None,
        extra_neg_datasets: list[str] = None,
    ) -> dict:
        """Carry on from this version in a fresh, editable one.

        The new version gets its own main example datasets: copies of this
        version's by default, so labelling continues without touching what the
        source froze. ``copy_examples=False`` starts them empty instead, for
        relabelling from scratch.

        Additional datasets are references rather than copies, and all of them
        come along unless you name the ones to keep — a subset of what this
        version has, or ``[]`` to drop them.
        """
        return await self._c._make_request(
            url=f"classifiers/{slug_version}/new-version/",
            method="POST",
            json=dict_filter_none(
                {
                    "copy_examples": copy_examples,
                    "extra_pos_datasets": list(extra_pos_datasets) if extra_pos_datasets is not None else None,
                    "extra_neg_datasets": list(extra_neg_datasets) if extra_neg_datasets is not None else None,
                }
            ),
        )

    async def add_examples(self, slug_version: str, side: str, image_ids: list[str]) -> dict:
        """Label images ``pos`` or ``neg``, taking them off the other side.

        Only the classifier's own example datasets change, borrowed ones are
        edited through ``datasets``. Returns the summed ``added``/``removed``.
        """
        if side not in ("pos", "neg"):
            raise ValueError(f"side must be 'pos' or 'neg', got '{side}'.")
        server_side = {"pos": "positive", "neg": "negative"}[side]
        image_ids = list(image_ids)
        result = {"added": 0, "removed": 0}
        for start in range(0, len(image_ids), LABEL_CHUNK):
            response = await self._c._make_request(
                url=f"classifiers/{slug_version}/label/",
                method="POST",
                json={"side": server_side, "image_ids": image_ids[start : start + LABEL_CHUNK]},
            )
            for key in result:
                result[key] += response.get(key, 0)
        return result

    async def examples(self, slug_version: str, side: str, limit: int = 1000, **params) -> list[dict]:
        """Every image labelled on one side - owned set and borrowed ones together."""
        if side not in ("pos", "neg"):
            raise ValueError(f"side must be 'pos' or 'neg', got '{side}'.")
        classifier = await self.get(slug_version)
        main = classifier[f"main_{side}_dataset"]
        datasets = ([main] if main else []) + list(classifier[f"extra_{side}_datasets"])
        if not datasets:
            return []
        return await self._c.images.list(datasets=datasets, limit=limit, **params)

    async def report_training(
        self,
        slug_version: str,
        training_id: str,
        status: str,
        model_id: str = None,
        metrics: dict = None,
        error: str = None,
        code_version: str = None,
        labels_version: str = None,
    ) -> dict:
        """The service's callback: how a training ended. ``status`` is ``trained``
        or ``failed``, ``model_id`` names the artifact an apply run then loads.
        ``code_version`` is the training code's version and ``labels_version``
        the version of the labelled sets it saw, so Dataroom can tell a stale
        model from a current one without asking Dagster."""
        return await self._c._make_request(
            url=f"classifiers/{slug_version}/trainings/{training_id}/report/",
            method="POST",
            json=dict_filter_none(
                {
                    "status": status,
                    "model_id": model_id,
                    "metrics": metrics,
                    "error": error,
                    "code_version": code_version,
                    "labels_version": labels_version,
                }
            ),
        )

    async def report_run(
        self,
        slug_version: str,
        run_id: str,
        status: str = None,
        total: int = None,
        processed: int = None,
        error: str = None,
    ) -> dict:
        """The service's callback: an apply run's progress or outcome. Every field
        is optional, so a mid-run call can report ``total`` and leave the rest."""
        return await self._c._make_request(
            url=f"classifiers/{slug_version}/runs/{run_id}/report/",
            method="POST",
            json=dict_filter_none({"status": status, "total": total, "processed": processed, "error": error}),
        )

    async def add_scores(self, slug_version: str, scores: dict[str, float], run_id: str = None) -> dict:
        """Write this classifier's scores onto image docs, in server-sized chunks.

        Each image gets ``classifications["<slug>/<version>"]``, other classifiers'
        scores untouched. ``run_id`` counts the batch towards that run's progress.
        Ids the collection no longer holds come back in ``missing``.
        """
        ids = list(scores)
        written, missing = 0, []
        for start in range(0, len(ids), SCORES_CHUNK):
            chunk = ids[start : start + SCORES_CHUNK]
            response = await self._c._make_request(
                url=f"classifiers/{slug_version}/scores/",
                method="POST",
                json=dict_filter_none({"scores": {i: scores[i] for i in chunk}, "run_id": run_id}),
            )
            written += response.get("written", 0)
            missing += response.get("missing", [])
        return {"written": written, "missing": missing}
