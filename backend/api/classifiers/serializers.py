from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from backend.api.users.serializers import UserSerializer
from backend.dataroom.choices import ApplyRunStatus, TrainingStatus
from backend.dataroom.classifiers.runner import get_runner
from backend.dataroom.datasets.single_image import SINGLE_IMAGE_TYPE, ensure_single_image_type
from backend.dataroom.models.classifier import Classifier, ClassifierApplyRun, ClassifierTraining
from backend.dataroom.models.dataset import Dataset, DatasetMembership
from backend.dataroom.models.os_image import SUPPORTED_EMBEDDING_SPACES


def _member_counts(dataset_ids) -> dict:
    """{dataset_id: active member count} in one grouped query."""
    if not dataset_ids:
        return {}
    rows = (
        Dataset.objects.filter(id__in=dataset_ids)
        .values('id')
        .annotate(
            total=Count(
                'memberships',
                filter=Q(memberships__deleted_at__isnull=True, memberships__group__deleted_at__isnull=True),
            )
        )
    )
    return {row['id']: row['total'] for row in rows}


def _groups_by_dataset(**filters) -> dict:
    """{dataset_id: {group_id, ...}} of the active memberships matching filters."""
    rows = DatasetMembership.objects.filter(
        deleted_at__isnull=True, group__deleted_at__isnull=True, **filters
    ).values_list('dataset_id', 'group_id')
    groups: dict = {}
    for dataset_id, group_id in rows:
        groups.setdefault(dataset_id, set()).add(group_id)
    return groups


def batch_example_counts(classifiers):
    """Per-classifier example counts, split main vs extra, in one query.

    A classifier's examples are its own dataset plus any borrowed ones, and in a
    ``single_image`` dataset one member group is one image — so a member count
    is an image count.

    ``val_pos``/``val_neg`` are the held-out members of each side. A held-out
    image is still an example, so it is counted in ``pos``/``neg`` too — these
    say how many of those training will not learn from.

    ``val_orphan`` is the rest of the held-out set: images that are in it while
    no longer being an example of either side, which is what removing one from
    a side dataset directly leaves behind (labelling it ``none`` takes it off
    the held-out set as well). Training and its metrics both skip them, so
    without this count they are invisible.
    """
    dataset_ids = set()
    val_dataset_ids = set()
    for classifier in classifiers:
        for dataset in (classifier.main_pos_dataset, classifier.main_neg_dataset):
            if dataset:
                dataset_ids.add(dataset.id)
        for dataset in [*classifier.extra_pos_datasets.all(), *classifier.extra_neg_datasets.all()]:
            dataset_ids.add(dataset.id)
        if classifier.val_dataset:
            val_dataset_ids.add(classifier.val_dataset.id)
    counts = _member_counts(dataset_ids)
    held = _groups_by_dataset(dataset_id__in=val_dataset_ids) if val_dataset_ids else {}
    all_held = {group_id for groups in held.values() for group_id in groups}
    # Only the held-out groups: the question is which side each one sits on.
    sides = _groups_by_dataset(dataset_id__in=dataset_ids, group_id__in=all_held) if all_held else {}

    result = {}
    for classifier in classifiers:
        main_pos = counts.get(getattr(classifier.main_pos_dataset, 'id', None), 0)
        main_neg = counts.get(getattr(classifier.main_neg_dataset, 'id', None), 0)
        extra_pos = sum(counts.get(d.id, 0) for d in classifier.extra_pos_datasets.all())
        extra_neg = sum(counts.get(d.id, 0) for d in classifier.extra_neg_datasets.all())
        mine = held.get(getattr(classifier.val_dataset, 'id', None), set())
        pos_side = sides.get(getattr(classifier.main_pos_dataset, 'id', None), set())
        neg_side = sides.get(getattr(classifier.main_neg_dataset, 'id', None), set())
        result[classifier.id] = {
            'main_pos': main_pos,
            'main_neg': main_neg,
            'extra_pos': extra_pos,
            'extra_neg': extra_neg,
            'pos': main_pos + extra_pos,
            'neg': main_neg + extra_neg,
            'val_pos': len(mine & pos_side),
            'val_neg': len(mine & neg_side),
            'val_orphan': len(mine - pos_side - neg_side),
        }
    return result


class ExtraDatasetsField(serializers.SlugRelatedField):
    """Borrowed example datasets, addressed by ``slug/version``.

    A classifier labels individual images, so an example set has to be a dataset
    of ``single_image`` groups; anything else would put whole multi-image groups
    on one side of a binary decision. A classifier's own (internal) datasets are
    refused here — those are the main sets, not extras.
    """

    def __init__(self, **kwargs):
        super().__init__(slug_field='slug_version', queryset=Dataset.objects.all(), **kwargs)

    def to_internal_value(self, data):
        dataset = super().to_internal_value(data)
        if dataset.type_id != SINGLE_IMAGE_TYPE:
            raise serializers.ValidationError(
                f"Dataset '{dataset.slug_version}' is of type '{dataset.type_id}'. A classifier's example "
                f"sets must be '{SINGLE_IMAGE_TYPE}' datasets, so that one member is one labelled image."
            )
        if dataset.is_internal:
            raise serializers.ValidationError(
                f"Dataset '{dataset.slug_version}' belongs to a classifier and is edited through it, so it "
                f'cannot be borrowed as an extra example set.'
            )
        return dataset


class ExampleCountsSerializer(serializers.Serializer):
    """Shape of ``counts`` — declared so the generated clients get numbers
    rather than an opaque object."""

    main_pos = serializers.IntegerField()
    main_neg = serializers.IntegerField()
    extra_pos = serializers.IntegerField()
    extra_neg = serializers.IntegerField()
    pos = serializers.IntegerField()
    neg = serializers.IntegerField()
    val_pos = serializers.IntegerField()
    val_neg = serializers.IntegerField()
    val_orphan = serializers.IntegerField()


class ClassifierSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    # only spaces the service can embed
    embedding_space = serializers.ChoiceField(choices=SUPPORTED_EMBEDDING_SPACES, allow_blank=True, required=False)
    main_pos_dataset = serializers.SlugRelatedField(slug_field='slug_version', read_only=True)
    main_neg_dataset = serializers.SlugRelatedField(slug_field='slug_version', read_only=True)
    val_dataset = serializers.SlugRelatedField(slug_field='slug_version', read_only=True)
    extra_pos_datasets = ExtraDatasetsField(many=True, required=False)
    extra_neg_datasets = ExtraDatasetsField(many=True, required=False)
    counts = serializers.SerializerMethodField()

    class Meta:
        model = Classifier
        fields = (
            'slug_version',
            'slug',
            'version',
            'name',
            'description',
            'version_note',
            'author',
            'main_pos_dataset',
            'main_neg_dataset',
            'val_dataset',
            'extra_pos_datasets',
            'extra_neg_datasets',
            'counts',
            'embedding_space',
            'is_frozen',
            'date_created',
            'date_updated',
        )
        read_only_fields = (
            'slug_version',
            'version',
            'author',
            'main_pos_dataset',
            'main_neg_dataset',
            'val_dataset',
            'counts',
            'date_created',
            'date_updated',
        )

    @extend_schema_field(ExampleCountsSerializer)
    def get_counts(self, obj) -> dict:
        # list() batches the whole page into context, a single instance counts just itself
        counts = self.context.get('example_counts')
        if counts is None:
            counts = batch_example_counts([obj])
        return counts[obj.id]

    def validate_slug(self, value):
        # Reusing a slug used to make the next version, sharing the example
        # datasets with the one before, so locking one froze the other too.
        # New versions come from the new-version endpoint, with their own copies.
        if self.instance is not None:
            raise serializers.ValidationError('A classifier keeps its slug.')
        latest = Classifier.objects.filter(slug=value).order_by('-version').first()
        if latest is not None:
            raise serializers.ValidationError(
                f"Classifier '{value}' already exists (latest is v{latest.version}). To carry on from it, POST to "
                f'/api/classifiers/{latest.slug_version}/new-version/ — that gives the new version its own copies of '
                f'the example datasets. Use a different slug for an unrelated classifier.'
            )
        return value

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        classifier = super().create(validated_data)
        create_main_datasets(classifier, self.context['request'].user)
        return classifier

    def validate(self, attrs):
        # A locked version is a fixed record of one choice of examples. Editing
        # is refused rather than silently ignored: the way forward is a new
        # version, which carries on from this one with its own copies.
        #
        # ``version_note`` is exempt: it says what the version was for, and you
        # usually only know that once it is locked and something newer exists.
        # It annotates the record without changing what the version trains on.
        if self.instance is not None and self.instance.is_frozen:
            editable = set(attrs) - {'is_frozen', 'version_note'}
            if editable:
                raise serializers.ValidationError(
                    f"Classifier '{self.instance.slug_version}' is locked. POST to its new-version endpoint to "
                    f'carry on in a fresh version, or unlock this one.'
                )

        instance = self.instance
        extra_pos = attrs.get('extra_pos_datasets')
        extra_neg = attrs.get('extra_neg_datasets')
        if extra_pos is None and instance is not None:
            extra_pos = list(instance.extra_pos_datasets.all())
        if extra_neg is None and instance is not None:
            extra_neg = list(instance.extra_neg_datasets.all())
        pos_set = {d.slug_version for d in extra_pos or []}
        neg_set = {d.slug_version for d in extra_neg or []}
        overlap = pos_set & neg_set
        if overlap:
            raise serializers.ValidationError(
                {
                    'extra_neg_datasets': (
                        f'{", ".join(sorted(overlap))} is attached as both a positive and a negative '
                        f'example set, so every image in it would be labelled both ways.'
                    )
                }
            )
        return super().validate(attrs)


class ClassifierNewVersionSerializer(serializers.Serializer):
    """Options for branching a version."""

    copy_examples = serializers.BooleanField(
        required=False,
        default=True,
        help_text=(
            'Start the new version with a copy of this one\'s main example datasets. '
            'False gives it empty ones instead, for relabelling from scratch.'
        ),
    )
    extra_pos_datasets = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text=(
            'Which of this version\'s additional positive datasets to carry over, by '
            '``slug/version``. Omit to carry all of them; pass [] for none. Must be a '
            'subset of what this version has.'
        ),
    )
    extra_neg_datasets = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text='The negative side of ``extra_pos_datasets``.',
    )
    version_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        help_text=(
            'What this new version is for: why it was branched, what is changing. '
            'Unlike ``description`` it belongs to the one version, and is not '
            'carried forward from the source.'
        ),
    )


class ClassifierLabelSerializer(serializers.Serializer):
    """Which images to label, and which side to put them on."""

    image_ids = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    side = serializers.ChoiceField(
        choices=('positive', 'negative', 'none'),
        help_text=(
            'The side to put these images on. ``none`` unlabels them: they leave both '
            'main example datasets and this classifier stops having an opinion on them.'
        ),
    )


class ClassifierLabelResponseSerializer(serializers.Serializer):
    """What a labelling call changed, per side."""

    added = serializers.IntegerField(help_text='Images that became examples on the requested side.')
    removed = serializers.IntegerField(help_text='Images taken off the other side (or off both, for ``none``).')


class ClassifierHoldoutSerializer(serializers.Serializer):
    """Re-draw the held-out set at a fraction of each side.

    Sampling per side rather than from the pile as a whole: negatives usually
    outnumber positives, and a draw from the pile can hold barely any positives.
    """

    mode = serializers.ChoiceField(choices=('random',))
    fraction = serializers.FloatField(
        required=False,
        default=0.2,
        min_value=0.01,
        max_value=0.9,
        help_text='The share of EACH side to hold out.',
    )


class ClassifierHoldoutResponseSerializer(serializers.Serializer):
    """The held-out set after the draw, per side."""

    val_pos = serializers.IntegerField(help_text='Held-out positive examples.')
    val_neg = serializers.IntegerField(help_text='Held-out negative examples.')
    added = serializers.IntegerField(help_text='Images that joined the held-out set.')
    removed = serializers.IntegerField(help_text='Images that left it.')


def create_main_datasets(classifier: Classifier, author) -> Classifier:
    """Give a classifier the two datasets it owns.

    They are internal: hidden from the datasets list and edited only through the
    classifier, so a workspace with twenty classifiers does not carry forty
    datasets nobody curates directly.
    """
    single_image = ensure_single_image_type()
    for field, side in (('main_pos_dataset', 'positives'), ('main_neg_dataset', 'negatives')):
        if getattr(classifier, field) is not None:
            continue
        dataset = Dataset.objects.create(
            slug=f'{classifier.slug}-{side}',
            name=f'{classifier.name} {side}',
            type=single_image,
            author=author,
            is_internal=True,
            description=f'{side.capitalize()} examples of the "{classifier.name}" classifier.',
        )
        setattr(classifier, field, dataset)
    classifier.save(update_fields=['main_pos_dataset', 'main_neg_dataset', 'date_updated'])
    return classifier


def ensure_val_dataset(classifier: Classifier, author) -> Dataset:
    """The classifier's held-out dataset, created on first use.

    Made only when something is actually held out: most classifiers never will
    be, and a dataset row per classifier that nobody uses is two rows of noise
    per classifier in a table that already carries the main pair.
    """
    if classifier.val_dataset is not None:
        return classifier.val_dataset
    dataset = Dataset.objects.create(
        slug=f'{classifier.slug}-validation',
        name=f'{classifier.name} validation',
        type=ensure_single_image_type(),
        author=author,
        is_internal=True,
        description=(
            f'Held-out examples of the "{classifier.name}" classifier: annotations '
            f'training does not learn from, so its scores measure something it has not seen.'
        ),
    )
    classifier.val_dataset = dataset
    classifier.save(update_fields=['val_dataset', 'date_updated'])
    return dataset


class ClassifierTrainingSerializer(serializers.ModelSerializer):
    """A training run as the Training tab shows it. Everything is read-only:
    rows are created by the train action and updated by the service's report."""

    author = UserSerializer(read_only=True)
    dagster_run_url = serializers.SerializerMethodField()

    def get_dagster_run_url(self, obj) -> str | None:
        return get_runner().run_url(obj.dagster_run_id)

    class Meta:
        model = ClassifierTraining
        fields = (
            'id',
            'status',
            'dagster_run_id',
            'dagster_run_url',
            'model_id',
            'metrics',
            'error',
            'forced',
            'labels_version',
            'code_version',
            'n_pos',
            'n_neg',
            'n_val',
            'author',
            'date_created',
            'date_updated',
        )
        read_only_fields = fields


class ClassifierApplyRunSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    training_id = serializers.UUIDField(read_only=True)
    model_id = serializers.CharField(source='training.model_id', read_only=True)
    dagster_run_url = serializers.SerializerMethodField()

    def get_dagster_run_url(self, obj) -> str | None:
        return get_runner().run_url(obj.dagster_run_id)

    class Meta:
        model = ClassifierApplyRun
        fields = (
            'id',
            'status',
            'dagster_run_id',
            'dagster_run_url',
            'training_id',
            'model_id',
            'target_type',
            'target_value',
            'processed',
            'total',
            'error',
            'author',
            'date_created',
            'date_updated',
        )
        read_only_fields = fields


class ClassifierTrainSerializer(serializers.Serializer):
    """Options for starting a training run."""

    force = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            'Train even if a trained model already exists for the current labelled '
            'datasets. Without it, an unchanged classifier returns its existing '
            'training instead of computing the same model again.'
        ),
    )


class ClassifierApplySerializer(serializers.Serializer):
    """What to score, and with which trained model.

    A target is always one named set: a dataset version, a saved query, a
    source or a tag. Scoring the classifier's own examples is an apply per
    owned dataset, and there is no "everything" target — a run is one
    partition of one set on the runner's side.
    """

    target_type = serializers.ChoiceField(choices=('dataset', 'query', 'source', 'tag'))
    target_value = serializers.CharField(required=False, allow_blank=True, default='')
    training_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text='Which training\'s model to apply. Omit for the latest trained one.',
    )

    def validate(self, attrs):
        if not attrs['target_value']:
            raise serializers.ValidationError({'target_value': 'Required: which dataset, query, source or tag.'})
        return attrs


class ClassifierTrainingReportSerializer(serializers.Serializer):
    """What the classifier service reports back onto a training record."""

    status = serializers.ChoiceField(choices=(TrainingStatus.TRAINED.value, TrainingStatus.FAILED.value))
    model_id = serializers.CharField(required=False, allow_blank=True, default='')
    metrics = serializers.JSONField(required=False, allow_null=True, default=None)
    error = serializers.CharField(required=False, allow_blank=True, default='', trim_whitespace=False)
    # The service's own view of what it ran: which code, and which labelled
    # sets it saw (normally the one Dataroom reported at launch).
    code_version = serializers.CharField(required=False, allow_blank=True, default='')
    labels_version = serializers.CharField(required=False, allow_blank=True, default='')


class ClassifierApplyRunReportSerializer(serializers.Serializer):
    """Progress/terminal reports of an apply run."""

    status = serializers.ChoiceField(
        choices=(ApplyRunStatus.RUNNING.value, ApplyRunStatus.COMPLETED.value, ApplyRunStatus.FAILED.value),
        required=False,
        allow_null=True,
        default=None,
    )
    total = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0)
    processed = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0)
    error = serializers.CharField(required=False, allow_blank=True, default='', trim_whitespace=False)


class ClassifierScoresSerializer(serializers.Serializer):
    """A batch of scores to write onto image documents."""

    scores = serializers.DictField(child=serializers.FloatField(min_value=0.0, max_value=1.0), allow_empty=False)
    run_id = serializers.UUIDField(required=False, allow_null=True, default=None)
