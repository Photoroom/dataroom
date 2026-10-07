import logging
import random

import django_filters
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from backend.api.classifiers.serializers import (
    ClassifierApplyRunReportSerializer,
    ClassifierApplyRunSerializer,
    ClassifierApplySerializer,
    ClassifierHoldoutResponseSerializer,
    ClassifierHoldoutSerializer,
    ClassifierLabelResponseSerializer,
    ClassifierLabelSerializer,
    ClassifierNewVersionSerializer,
    ClassifierScoresSerializer,
    ClassifierSerializer,
    ClassifierTrainingReportSerializer,
    ClassifierTrainingSerializer,
    ClassifierTrainSerializer,
    batch_example_counts,
    ensure_val_dataset,
)
from backend.api.datasets.views import sync_dataset_copy
from backend.dataroom.choices import ApplyRunStatus, TrainingStatus
from backend.dataroom.classifiers.runner import RunnerError, RunnerNotConfiguredError, get_runner
from backend.dataroom.datasets.single_image import (
    SingleImageGroupNameConflictError,
    add_images_to_dataset,
    remove_images_from_dataset,
)
from backend.dataroom.exceptions import SaveConflictError
from backend.dataroom.models.classifier import Classifier, ClassifierApplyRun, ClassifierTraining
from backend.dataroom.models.dataset import Dataset
from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OSBulkIndex

# A scores batch is one OS bulk write; the classifier service sends chunks of
# this size. Higher than the images API's bulk limits because a score is one
# tiny field, not a document rewrite.
SCORES_BULK_LIMIT = 500

MIN_EXAMPLES_PER_SIDE = 4
# What Train holds out per side when nobody sampled a validation set; the UI's default share.
DEFAULT_HOLDOUT_FRACTION = 0.2

logger = logging.getLogger(__name__)


def _sync_labels(classifier) -> None:
    """Tell the runner what this version trains on, if there is a runner.

    Best effort: the labels are reported again, and required, before every
    launch, so a failure here costs nothing but the stale flag in Dagster's
    UI until then.
    """
    try:
        get_runner().report_labels(classifier)
    except RunnerNotConfiguredError:
        pass
    except RunnerError as exc:
        logger.warning('could not report the labels of %s to the classifier runner: %s', classifier, exc)


def _lock(classifier) -> None:
    """Freeze a version and the datasets it owns, as one step."""
    with transaction.atomic():
        for dataset in classifier.owned_datasets():
            dataset.freeze()
        classifier.freeze()


def _member_image_ids(dataset) -> list[str]:
    """The image ids in a ``single_image`` dataset.

    One member group is one image and the group is named after it, so this is a
    Postgres read of the group names — no OpenSearch round trip to list what a
    classifier has.
    """
    if dataset is None:
        return []
    return list(dataset.active_groups().order_by('name').values_list('name', flat=True))


def _holdout_response(classifier, added: int, removed: int):
    """The held-out set as it now stands, read back from Postgres."""
    counts = batch_example_counts([classifier])[classifier.id]
    serializer = ClassifierHoldoutResponseSerializer(
        data={'val_pos': counts['val_pos'], 'val_neg': counts['val_neg'], 'added': added, 'removed': removed}
    )
    serializer.is_valid(raise_exception=True)
    return Response(serializer.data)


def _draw_holdout(classifier, fraction: float) -> list[str]:
    """Sample each side separately, leaving enough behind to train on."""
    picks: list[str] = []
    for dataset, side in ((classifier.main_pos_dataset, 'positive'), (classifier.main_neg_dataset, 'negative')):
        image_ids = _member_image_ids(dataset)
        if len(image_ids) <= MIN_EXAMPLES_PER_SIDE:
            raise ValidationError(
                f"Classifier '{classifier.slug_version}' has {len(image_ids)} {side} example(s). Holding any "
                f'back would leave fewer than the {MIN_EXAMPLES_PER_SIDE} per side training needs.'
            )
        # At least one per side, and never so many that the remainder cannot
        # be trained on.
        count = max(1, min(round(len(image_ids) * fraction), len(image_ids) - MIN_EXAMPLES_PER_SIDE))
        picks.extend(random.sample(image_ids, count))
    return picks


def _apply_holdout(classifier, user, fraction: float) -> tuple[int, int]:
    """Draw a fresh held-out set of ``fraction`` per side and make it THE set:
    returns (added, removed). The validation dataset is created on first use,
    and the labelled sets are reported to the runner when that happens."""
    picks = _draw_holdout(classifier, fraction)
    had_val_dataset = classifier.val_dataset is not None
    val_dataset = ensure_val_dataset(classifier, user)
    if not had_val_dataset:
        _sync_labels(classifier)  # the labelled sets gained a dataset
    # A draw replaces the set, which is what keeps the fraction meaning what it says.
    stale = [image_id for image_id in _member_image_ids(val_dataset) if image_id not in set(picks)]
    removed = remove_images_from_dataset(val_dataset, stale) if stale else 0
    try:
        added = add_images_to_dataset(val_dataset, picks)
    except SingleImageGroupNameConflictError as exc:
        raise ValidationError({'image_ids': str(exc)}) from exc
    return added, removed


class ClassifierServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'The classifier runner is not configured (CLASSIFIER_RUNNER / DAGSTER_URL).'


class ClassifierFilter(FilterSet):
    name__prefix = django_filters.CharFilter(field_name='name', lookup_expr='istartswith')

    class Meta:
        model = Classifier
        fields = ('slug', 'is_frozen', 'embedding_space', 'name__prefix')


class ClassifierViewSet(ModelViewSet):
    """Versioned binary classifier definitions: the example sets to train on."""

    serializer_class = ClassifierSerializer
    ordering = ['slug', '-version']
    lookup_field = 'slug_version'
    lookup_value_regex = r'[^/.]+\/[0-9]+'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = ClassifierFilter
    search_fields = ['slug', 'slug_version', 'name']

    def get_queryset(self):
        return (
            Classifier.objects.all()
            .select_related('author', 'main_pos_dataset', 'main_neg_dataset', 'val_dataset')
            .prefetch_related('extra_pos_datasets', 'extra_neg_datasets')
        )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        _sync_labels(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        _sync_labels(serializer.instance)

    def list(self, request, *args, **kwargs):
        # Batch both sides' example counts for the whole page (two grouped
        # queries) instead of two per card — mirrors DatasetViewSet.list.
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        classifiers = page if page is not None else list(queryset)
        context = {**self.get_serializer_context(), 'example_counts': batch_example_counts(classifiers)}
        serializer = self.get_serializer(classifiers, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    # request=None: lock takes no body, so the generated clients do not ask
    # callers to invent one.
    @extend_schema(request=None, responses=None, methods=['POST'])
    @action(detail=True, methods=['post'])
    def lock(self, request, slug_version=None):
        """Make this version final: freeze it AND its example datasets."""
        _lock(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=ClassifierLabelSerializer, responses=ClassifierLabelResponseSerializer, methods=['POST'])
    @action(detail=True, methods=['post'])
    def label(self, request, slug_version=None):
        """Put images on one side of this classifier, off the other."""
        classifier = self.get_object()
        options = ClassifierLabelSerializer(data=request.data)
        options.is_valid(raise_exception=True)
        image_ids = options.validated_data['image_ids']
        side = options.validated_data['side']

        add_to = {'positive': classifier.main_pos_dataset, 'negative': classifier.main_neg_dataset, 'none': None}[side]
        if side != 'none' and add_to is None:
            raise ValidationError(f"Classifier '{classifier.slug_version}' has no main {side} dataset to label into.")
        remove_from = [dataset for dataset in classifier.main_datasets() if dataset != add_to]
        # Unlabelling drops the hold-out with it: the held-out set is a subset
        # of the examples, and an image that is no longer an example of either
        # side cannot be a validation example of one.
        if side == 'none' and classifier.val_dataset is not None:
            remove_from.append(classifier.val_dataset)
        # Frozen is checked up front, over every dataset the call would touch: a
        # locked classifier must not half-apply a label, leaving the image added
        # to one side and still sitting on the other.
        if any(dataset.is_frozen for dataset in [*remove_from, add_to] if dataset is not None):
            raise ValidationError(
                f"Classifier '{classifier.slug_version}' is locked, so its examples cannot change. POST to its "
                f'new-version endpoint to carry on labelling in a fresh version, or unlock this one.'
            )

        # Remove first: an image moving sides is briefly on neither, never on
        # both, so a failure between the two writes leaves it unlabelled rather
        # than contradicting itself.
        removed = sum(remove_images_from_dataset(dataset, image_ids) for dataset in remove_from)
        try:
            added = add_images_to_dataset(add_to, image_ids) if add_to is not None else 0
        except SingleImageGroupNameConflictError as exc:
            raise ValidationError({'image_ids': str(exc)}) from exc
        response = ClassifierLabelResponseSerializer(data={'added': added, 'removed': removed})
        response.is_valid(raise_exception=True)
        return Response(response.data)

    @extend_schema(request=ClassifierHoldoutSerializer, responses=ClassifierHoldoutResponseSerializer, methods=['POST'])
    @action(detail=True, methods=['post'])
    def holdout(self, request, slug_version=None):
        """Re-draw which examples training must not learn from.

        A held-out image stays on its side: it is added to a third dataset
        that means "do not train on this". Only the main datasets are drawn
        from, since borrowed extras can change underneath this classifier.
        """
        classifier = self.get_object()
        options = ClassifierHoldoutSerializer(data=request.data)
        options.is_valid(raise_exception=True)

        if classifier.is_frozen:
            raise ValidationError(
                f"Classifier '{classifier.slug_version}' is locked, so its held-out set cannot change. POST to its "
                f'new-version endpoint to carry on in a fresh version, or unlock this one.'
            )

        added, removed = _apply_holdout(classifier, request.user, options.validated_data['fraction'])
        return _holdout_response(classifier, added=added, removed=removed)

    @extend_schema(request=None, responses=None, methods=['POST'])
    @action(detail=True, methods=['post'])
    def unlock(self, request, slug_version=None):
        """Undo a lock, on the classifier and its example datasets."""
        classifier = self.get_object()
        with transaction.atomic():
            for dataset in classifier.owned_datasets():
                dataset.unfreeze()
            classifier.unfreeze()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=ClassifierNewVersionSerializer, responses=ClassifierSerializer, methods=['POST'])
    @action(detail=True, methods=['post'], url_path='new-version')
    def new_version(self, request, slug_version=None):
        """Carry on from this version in a fresh, editable one."""
        options = ClassifierNewVersionSerializer(data=request.data)
        options.is_valid(raise_exception=True)
        copy_examples = options.validated_data['copy_examples']
        source = self.get_object()
        # Carrying over is a choice per dataset, so the request names the ones to
        # keep. Omitting a side keeps all of it: the common case is continuing
        # with the same borrowed sets.
        extras = {}
        for field in ('extra_pos_datasets', 'extra_neg_datasets'):
            available = {dataset.slug_version: dataset for dataset in getattr(source, field).all()}
            requested = options.validated_data.get(field)
            if requested is None:
                extras[field] = list(available.values())
                continue
            unknown = sorted(set(requested) - set(available))
            if unknown:
                raise ValidationError(
                    {field: f'{", ".join(unknown)} is not an additional dataset of {source.slug_version}.'}
                )
            extras[field] = [available[slug_version] for slug_version in requested]
        new_classifier = Classifier.objects.create(
            slug=source.slug,
            name=source.name,
            description=source.description,
            # Per-version, so it starts as whatever this branch is for rather
            # than repeating the source's note.
            version_note=options.validated_data['version_note'],
            embedding_space=source.embedding_space,
            author=request.user,
        )
        # The owned datasets are copied, so the new version has writable buckets
        # holding the work so far. Borrowed ones are referenced as they were:
        # they belong to whoever curates them, and duplicating someone else's
        # dataset per classifier version would be both surprising and expensive.
        for field in ('main_pos_dataset', 'main_neg_dataset', 'val_dataset'):
            source_dataset = getattr(source, field)
            if source_dataset is None:
                continue
            fresh = Dataset.objects.create(
                slug=source_dataset.slug,
                name=source_dataset.name,
                description=source_dataset.description,
                type=source_dataset.type,
                author=request.user,
                is_internal=True,
            )
            if copy_examples:
                with transaction.atomic():
                    fresh.copy_groups_from(source_dataset)
                copied = list(fresh.memberships.filter(deleted_at__isnull=True).values_list('group_id', flat=True))
                sync_dataset_copy(fresh, copied)
            setattr(new_classifier, field, fresh)
        new_classifier.save(update_fields=['main_pos_dataset', 'main_neg_dataset', 'val_dataset', 'date_updated'])
        new_classifier.extra_pos_datasets.set(extras['extra_pos_datasets'])
        new_classifier.extra_neg_datasets.set(extras['extra_neg_datasets'])
        _sync_labels(new_classifier)

        serializer = self.get_serializer(new_classifier)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ClassifierTrainSerializer, responses=ClassifierTrainingSerializer, methods=['POST'])
    @action(detail=True, methods=['post'])
    def train(self, request, slug_version=None):
        """Train a model on this version's examples, on the classifier service."""
        classifier = self.get_object()
        options = ClassifierTrainSerializer(data=request.data)
        options.is_valid(raise_exception=True)
        force = options.validated_data['force']

        counts = batch_example_counts([classifier])[classifier.id]
        for side in ('pos', 'neg'):
            if counts[side] < MIN_EXAMPLES_PER_SIDE:
                raise ValidationError(
                    f'Classifier {classifier.slug_version!r} has {counts[side]} {side} example(s); '
                    f'training needs at least {MIN_EXAMPLES_PER_SIDE} per side.'
                )
        # The runner picks the model by its precision on the held-out set and
        # refuses to train without one on each side. A version nobody sampled
        # for gets the default draw here, and keeps it: the set is fixed from
        # now on, so metrics of later retrains stay comparable. Whoever wants a
        # particular set samples before pressing Train.
        if not counts['val_pos'] or not counts['val_neg']:
            if classifier.is_frozen:
                raise ValidationError(
                    f'Classifier {classifier.slug_version!r} has no held-out examples on both sides and is locked, '
                    f'so none can be drawn. Unlock it, or sample a validation set in a new version.'
                )
            _apply_holdout(classifier, request.user, DEFAULT_HOLDOUT_FRACTION)
            counts = batch_example_counts([classifier])[classifier.id]

        # What a training is OF is the version's labelled datasets, by
        # slug_version: the same list as the last trained run means the same
        # model, unless forced. Editing a dataset version in place does not
        # move this string on purpose (see Classifier.labelled_datasets); the
        # version is frozen once it trains, so that takes an unlock and a
        # forced retrain, both deliberate.
        labels_version = classifier.labels_version()
        if not force:
            existing = classifier.trainings.filter(status=TrainingStatus.TRAINED, labels_version=labels_version).first()
            if existing is not None:
                return Response(ClassifierTrainingSerializer(existing).data)

        training = ClassifierTraining.objects.create(
            classifier=classifier,
            author=request.user,
            forced=force,
            labels_version=labels_version,
            n_pos=counts['pos'],
            n_neg=counts['neg'],
            n_val=counts['val_pos'] + counts['val_neg'],
        )
        try:
            run_id = get_runner().launch_train(classifier, training)
        except RunnerNotConfiguredError as exc:
            training.delete()
            raise ClassifierServiceUnavailable() from exc
        except RunnerError as exc:
            training.status = TrainingStatus.FAILED
            training.error = str(exc)
            training.save(update_fields=['status', 'error', 'date_updated'])
            return Response(ClassifierTrainingSerializer(training).data, status=status.HTTP_502_BAD_GATEWAY)
        training.dagster_run_id = run_id
        training.save(update_fields=['dagster_run_id', 'date_updated'])
        # A trained version has exactly one set of labels: the run is reading
        # them now, and the model it produces is only reproducible if they stay.
        # Carrying on labelling means a new version, which copies them.
        _lock(classifier)
        return Response(ClassifierTrainingSerializer(training).data, status=status.HTTP_201_CREATED)

    # pagination_class=None: the response is a plain array (newest 50), and
    # without it the schema generator wraps the action in the global paginator
    # envelope that the implementation does not use.
    @extend_schema(responses=ClassifierTrainingSerializer(many=True), methods=['GET'])
    @action(detail=True, methods=['get'], pagination_class=None)
    def trainings(self, request, slug_version=None):
        """This version's training runs, newest first."""
        classifier = self.get_object()
        queryset = classifier.trainings.select_related('author')[:50]
        return Response(ClassifierTrainingSerializer(queryset, many=True).data)

    @extend_schema(request=ClassifierTrainingReportSerializer, responses=ClassifierTrainingSerializer, methods=['POST'])
    @action(detail=True, methods=['post'], url_path=r'trainings/(?P<training_id>[^/]+)/report')
    def training_report(self, request, slug_version=None, training_id=None):
        """The classifier service's callback: the terminal state of a training."""
        classifier = self.get_object()
        training = get_object_or_404(ClassifierTraining, id=training_id, classifier=classifier)
        options = ClassifierTrainingReportSerializer(data=request.data)
        options.is_valid(raise_exception=True)
        data = options.validated_data

        training.status = data['status']
        training.model_id = data['model_id']
        training.metrics = data['metrics']
        training.error = data['error']
        training.code_version = data['code_version']
        if data['labels_version']:
            training.labels_version = data['labels_version']
        # n_pos/n_neg stay as they were at launch: the number of EXAMPLES this
        # training was given, held-out ones included. The service reports the
        # smaller number it learned from (it drops the validation split, and
        # any image it could not fetch), and that number lives in `metrics` —
        # overwriting the example counts with it would make every training look
        # permanently out of date against the classifier's own counts, and
        # would stop the retrain cache below from ever matching.
        training.save(
            update_fields=['status', 'model_id', 'metrics', 'error', 'code_version', 'labels_version', 'date_updated']
        )
        return Response(ClassifierTrainingSerializer(training).data)

    @extend_schema(request=ClassifierApplySerializer, responses=ClassifierApplyRunSerializer, methods=['POST'])
    @action(detail=True, methods=['post'])
    def apply(self, request, slug_version=None):
        """Score a target with a trained model of this version."""
        classifier = self.get_object()
        options = ClassifierApplySerializer(data=request.data)
        options.is_valid(raise_exception=True)
        data = options.validated_data

        trainings = classifier.trainings.filter(status=TrainingStatus.TRAINED)
        if data['training_id'] is not None:
            training = trainings.filter(id=data['training_id']).first()
            if training is None:
                raise ValidationError({'training_id': 'No trained training with this id on this classifier.'})
        else:
            training = trainings.first()
            if training is None:
                raise ValidationError(
                    f'Classifier {classifier.slug_version!r} has no trained model yet; train it first.'
                )

        apply_run = ClassifierApplyRun.objects.create(
            classifier=classifier,
            training=training,
            author=request.user,
            target_type=data['target_type'],
            target_value=data['target_value'],
        )
        try:
            run_id = get_runner().launch_apply(classifier, apply_run, training.model_id)
        except RunnerNotConfiguredError as exc:
            apply_run.delete()
            raise ClassifierServiceUnavailable() from exc
        except RunnerError as exc:
            apply_run.status = ApplyRunStatus.FAILED
            apply_run.error = str(exc)
            apply_run.save(update_fields=['status', 'error', 'date_updated'])
            return Response(ClassifierApplyRunSerializer(apply_run).data, status=status.HTTP_502_BAD_GATEWAY)
        apply_run.dagster_run_id = run_id
        apply_run.save(update_fields=['dagster_run_id', 'date_updated'])
        return Response(ClassifierApplyRunSerializer(apply_run).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=ClassifierApplyRunSerializer(many=True), methods=['GET'])
    @action(detail=True, methods=['get'], pagination_class=None)
    def runs(self, request, slug_version=None):
        """This version's apply runs, newest first."""
        classifier = self.get_object()
        queryset = classifier.apply_runs.select_related('author', 'training')[:50]
        return Response(ClassifierApplyRunSerializer(queryset, many=True).data)

    @extend_schema(request=ClassifierApplyRunReportSerializer, responses=ClassifierApplyRunSerializer, methods=['POST'])
    @action(detail=True, methods=['post'], url_path=r'runs/(?P<run_id>[^/]+)/report')
    def run_report(self, request, slug_version=None, run_id=None):
        """The classifier service's callback: apply-run progress and outcome."""
        classifier = self.get_object()
        apply_run = get_object_or_404(ClassifierApplyRun, id=run_id, classifier=classifier)
        options = ClassifierApplyRunReportSerializer(data=request.data)
        options.is_valid(raise_exception=True)
        data = options.validated_data

        update_fields = ['date_updated']
        for field in ('status', 'total', 'processed', 'error'):
            if data[field] not in (None, ''):
                setattr(apply_run, field, data[field])
                update_fields.append(field)
        apply_run.save(update_fields=update_fields)
        return Response(ClassifierApplyRunSerializer(apply_run).data)

    @extend_schema(request=ClassifierScoresSerializer, responses=None, methods=['POST'])
    @action(detail=True, methods=['post'])
    def scores(self, request, slug_version=None):
        """Write a batch of this classifier's scores onto image documents."""
        classifier = self.get_object()
        options = ClassifierScoresSerializer(data=request.data)
        options.is_valid(raise_exception=True)
        scores = options.validated_data['scores']
        if len(scores) > SCORES_BULK_LIMIT:
            raise ValidationError(f'At most {SCORES_BULK_LIMIT} scores per call.')

        images = OSImage.objects.get_multiple(list(scores), fields=['id'], number=SCORES_BULK_LIMIT)
        try:
            with OSBulkIndex() as os_bulk:
                for image in images:
                    image.classifications = {classifier.slug_version: scores[image.id]}
                    image.save(fields=['classifications'], bulk_index=os_bulk)
        except SaveConflictError as exc:
            return Response({'error': exc.description}, status=status.HTTP_409_CONFLICT)

        run_id = options.validated_data['run_id']
        if run_id is not None:
            updated = ClassifierApplyRun.objects.filter(id=run_id, classifier=classifier).update(
                processed=F('processed') + len(images), status=ApplyRunStatus.RUNNING
            )
            if not updated:
                raise ValidationError({'run_id': 'No apply run with this id on this classifier.'})

        missing = sorted(set(scores) - {image.id for image in images})
        return Response({'written': len(images), 'missing': missing})
