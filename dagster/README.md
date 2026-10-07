# Dagster pipelines

Train and apply classifiers for Dataroom.

## Run locally

1. `docker compose up dataroom_dagster`
2. Open http://localhost:3000

## Test

```sh
cd dagster
uv venv .venv
uv pip install --python .venv/bin/python --extra-index-url https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match ../dataroom_client -e '.[dev]'
.venv/bin/pytest tests
```

## The asset graph

`build_env(env)` builds one graph per Dataroom deployment (`dev`, `eval`,
`prod`): keys `dataroom/<env>/<name>`, group `dataroom_<env>`, jobs
`dataroom_<env>_train_classifier` and `dataroom_<env>_apply_classifier`, and a
`dataroom_<env>` resource. A run's environment is in its asset key and nowhere
in its config. Dataroom launches the jobs over Dagster's GraphQL API with the
partition key as the `dagster/partition` run tag; the assets call back over
Dataroom's REST API.

```
labels               external, partition: classifier `<slug>/<version>`
  │ same key
trained_classifier   partition: classifier
  │ MultiToSingleDimension(classifier)
classified_images    partition: classifier × set ◀── same key ── target_embeddings (classifier × set)

image_embeddings     partition: set × backbone — feature extraction on its own
```

`image_embeddings` runs the backbone over a set with no classifier, no model
and no scores: it is how a set gets its features before any classifier exists,
how a backbone nobody has trained on yet gets tried, and how the cost of a big
set is paid deliberately rather than inside the first apply run that needs it.
`target_embeddings` covers an apply target and writes the same latent, so
whichever runs first does the work and the other reports `embedded_now: 0`.

A **set** is one Dataroom image selection, named the way Dataroom names it:
`dataset/<slug>/<v>`, `tag/<name>`, `source/<name>` or `query/<slug>` (a saved
query, which the images API resolves). Every one of those is short, stable and
free of `|`, so a key carries the whole selection and nothing about the target
travels in the run config. A two-dimensional key is the dimension values joined
by `|` in alphabetical order of dimension name, so a scores partition reads
`cats/2|dataset/shop/3`; Dagster also tags each event `partition/classifier`
and `partition/set`, which is how the UI filters along one axis.

The two embedding assets are keyed differently on purpose, and there is no
third key joining set, backbone and classifier: Dagster caps a multi-partition
at two dimensions, so scores cannot be keyed `(classifier, backbone, set)`, and
a mapping from `(classifier, set)` to `(set, backbone)` would have to look up
the classifier's backbone, which partition mappings cannot do — they are static
functions of the key. So `target_embeddings` is keyed the way the scores are,
which is what gives the scores a same-key edge to the features they were
computed from, while `image_embeddings` is keyed the way features actually are.
The overlap is at the asset level only: both write the same per-image latent,
so the work itself is done once.

### Who decides, who records

Dataroom is the system of record and the launcher: it knows which datasets a
version trains on and which images lack features, so it decides *what* runs.
Dagster records *what happened*, with lineage and versions. Nothing here
launches a run on its own — there are no automation conditions.

`labels` is an **external asset Dataroom observes**, never materializes. Before
every launch, and whenever a version's labelled sets change, Dataroom `POST`s
`/report_asset_observation/` with the positive, negative and held-out datasets
and the backbone as metadata. Dagster reads an external asset's data version
from observations only, which is why its partitions bar stays at 0% forever;
the Observations tab holds the history. A training reads *which* datasets it trains
on from the latest observation rather than from Dataroom's API, so adding an
extra dataset to a version after a run launches cannot change what that run
learns from.

What the observation pins is the identity of those datasets, not their
contents: their members are read live from the images API while the run
works. Training locks the version at launch, which freezes the datasets the
classifier owns, so those cannot move under a run. A borrowed extra dataset
is deliberately not frozen — it belongs to whoever curates it — so its
members can change mid-run, and neither the data version nor `labels_version`
would show it. That is the same "editing a dataset version in place opts out
of lineage" rule as everywhere else, with a run-length window; freeze the
datasets you borrow, or pin a locked version of them, when it matters.

### code_version and data_version

Every materialization carries both as tags, and staleness is computed from them
per partition:

| asset | `code_version` | `data_version` |
|---|---|---|
| `labels` | none (external) | `<backbone>:<sorted dataset slug_versions>`, from Dataroom |
| `trained_classifier` | `TRAIN_CODE_VERSION` | the model id |
| `target_embeddings` | `EMBED_CODE_VERSION` | `<latent>:<images in the set>` |
| `classified_images` | default | `<model id>:<latent>:<images scored>` |

- **`code_version`** is a hand-maintained constant on the asset. Bump it when
  what the asset produces changes meaning: a different head architecture or
  training recipe, a different way of computing or storing features. Dagster
  then marks every materialized partition stale, and Dataroom shows "trained
  with older code". Nothing retrains by itself.
- **`data_version`** is what the run reports about its output. For the head it
  is the model id, so a retrain changes it and every set that head scored goes
  stale. For features it is coverage, not content: the same set embedded again
  with nothing new to add is the same data, a set that grew is not. For
  `labels` it is the sorted slug_versions, so the head goes stale when the
  *list* of datasets changes and not otherwise — editing a dataset version in
  place is opting out of lineage, and the way back is a forced retrain.

Dataroom reads the same facts over GraphQL (`staleStatusByPartition`) and from
the training report, which carries `code_version` and `labels_version`, and
decides whether to offer a retrain. A version is locked when it trains, so a
trained version has exactly one set of labels; annotating on means a new
version.

### The run config

Assets derive everything from their partition key and the labels observation.
The run config only carries the Dataroom record ids to report onto
(`training_id`, `apply_run_id`), the model id for an apply, and
hyperparameters. A run launched by hand from the UI without those ids does its
work and reports nothing.

## Compute backends

Training and embedding run on the backend that `CLASSIFIER_COMPUTE` names.
The default `local` runs them in the run pod. Other values are a short name or a module path.

To add a backend:

1. Make a module with `run_step(step, payload, dataroom, run_id, log) -> dict`
   (see `ComputeBackend` in `dataroom/classifier/assets.py`)
2. Run the step with `dataroom.classifier.local.run` wherever it runs
3. Set `CLASSIFIER_COMPUTE` to the module path
