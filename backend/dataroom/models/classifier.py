from django.db import models

from backend.common.base_model import BaseModel
from backend.dataroom.choices import ApplyRunStatus, TrainingStatus
from backend.dataroom.models.dataset import Dataset, DatasetVersionManager


class Classifier(BaseModel):
    """A binary classifier: the single_image datasets holding its positive and negative
    examples, so annotating is ordinary dataset work and training is optional.

    Versioned like Dataset. A version pins its example datasets by slug_version, so a
    trained version stays as it was while newer versions collect more examples.

    embedding_space says which embedding a model is trained on, vectors from different
    spaces are not comparable.
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    version = models.PositiveIntegerField()
    slug_version = models.CharField(max_length=110, unique=True)
    description = models.TextField(blank=True, default='')
    # What this VERSION is, as opposed to what the classifier is: why it was
    # branched, what changed in its examples. `description` carries forward to
    # every version and describes the classifier; this does not and describes
    # one version, which is what makes a version list readable later.
    version_note = models.TextField(blank=True, default='')
    author = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)

    # The two datasets this classifier OWNS: created with it, edited only
    # through it, hidden from the datasets list (Dataset.is_internal), and
    # copied when a new version branches. Annotating writes here.
    main_pos_dataset = models.ForeignKey(
        Dataset, on_delete=models.PROTECT, null=True, blank=True, related_name='classifier_main_pos'
    )
    main_neg_dataset = models.ForeignKey(
        Dataset, on_delete=models.PROTECT, null=True, blank=True, related_name='classifier_main_neg'
    )
    # Ordinary datasets someone else curates, borrowed as extra examples. They
    # are referenced, never copied or frozen — this classifier does not own them.
    extra_pos_datasets = models.ManyToManyField(Dataset, blank=True, related_name='classifiers_extra_pos')
    extra_neg_datasets = models.ManyToManyField(Dataset, blank=True, related_name='classifiers_extra_neg')

    # The held-out examples: a third dataset this classifier owns, whose members
    # are ALSO members of a main set. It says "do not train on this", nothing
    # more — which side an image is on still comes from the main datasets, so
    # one dataset covers both sides and an image can never be held out as a
    # positive while being labelled a negative.
    #
    # Created on first use rather than with the classifier: every classifier
    # made before this existed has none, so the null case has to work anyway.
    val_dataset = models.ForeignKey(
        Dataset, on_delete=models.PROTECT, null=True, blank=True, related_name='classifier_val'
    )

    embedding_space = models.CharField(max_length=64, blank=True, default='')
    is_frozen = models.BooleanField(default=False)

    # Slug-keyed and model-agnostic; see the Dataset docstring.
    objects = DatasetVersionManager()

    class Meta:
        ordering = ('slug', '-version')
        constraints = [models.UniqueConstraint(fields=['slug', 'version'], name='classifier_slug_version_idx')]

    def __str__(self):
        return self.slug_version

    def save(self, *args, **kwargs):
        if not self.version:
            self.version = Classifier.objects.get_next_version(self.slug)
        self.slug_version = self.get_slug_version()
        super().save(*args, **kwargs)

    def get_slug_version(self):
        return f'{self.slug}/{self.version}'

    def main_datasets(self):
        """The two sides an image is labelled into — and only those.

        Labelling takes an image off every side except the one it was put on,
        and works off this list. The held-out set must NOT be in it: marking an
        image positive would then silently un-hold-out an image whose side has
        not changed at all.
        """
        return [dataset for dataset in (self.main_pos_dataset, self.main_neg_dataset) if dataset is not None]

    def owned_datasets(self):
        """Every dataset this classifier owns — the ones a lock freezes.

        The held-out set is one of them: a locked version whose validation set
        could still change would not have reproducible metrics, which is the
        point of locking.

        Extra datasets are deliberately excluded: they belong to whoever curates
        them, and freezing someone else's dataset because a classifier borrowed
        it would be a surprising amount of reach.
        """
        return [*self.main_datasets(), *([self.val_dataset] if self.val_dataset is not None else [])]

    def freeze(self):
        self.is_frozen = True
        self.save()

    def unfreeze(self):
        self.is_frozen = False
        self.save()

    def labelled_datasets(self) -> dict:
        """The datasets a version trains on, by role: what the classifier
        service is told and what ``labels_version`` fingerprints.

        Owned and borrowed alike, by slug_version — a dataset version is the
        unit of change here. Editing a dataset version in place does not show
        up; that is the user opting out of lineage, and the way back is a
        forced retrain.
        """
        pos = [self.main_pos_dataset, *self.extra_pos_datasets.all()]
        neg = [self.main_neg_dataset, *self.extra_neg_datasets.all()]
        return {
            'pos': [dataset.slug_version for dataset in pos if dataset is not None],
            'neg': [dataset.slug_version for dataset in neg if dataset is not None],
            'val': self.val_dataset.slug_version if self.val_dataset is not None else '',
            'embedding_space': self.embedding_space,
        }

    def labels_version(self) -> str:
        """One string for "what this version trains on": the backbone and the
        sorted slug_versions of every labelled dataset. Dataroom reports it as
        the data version of the Dagster ``labels`` asset, the training reports
        it back, and equality is what decides whether a retrain is needed.
        """
        labels = self.labelled_datasets()
        datasets = [*labels['pos'], *labels['neg'], *([labels['val']] if labels['val'] else [])]
        return f"{labels['embedding_space']}:{','.join(sorted(datasets))}"


class ClassifierTraining(BaseModel):
    """One training run of a classifier version, filled in from what the service reports.

    model_id is the service's handle for the trained model, apply sends it back.
    labels_version is what the version trained on (Classifier.labels_version at
    launch); train reuses an existing trained run with the same labels_version
    unless forced. code_version is the training code's version as the service
    reported it. n_pos, n_neg and n_val are the example counts at launch, for
    the page.
    """

    classifier = models.ForeignKey(Classifier, on_delete=models.CASCADE, related_name='trainings')
    author = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=16, choices=TrainingStatus.choices, default=TrainingStatus.TRAINING)
    dagster_run_id = models.CharField(max_length=64, blank=True, default='')
    model_id = models.CharField(max_length=64, blank=True, default='')
    metrics = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default='')
    forced = models.BooleanField(default=False)
    labels_version = models.CharField(max_length=1024, blank=True, default='')
    code_version = models.CharField(max_length=64, blank=True, default='')
    n_pos = models.PositiveIntegerField(default=0)
    n_neg = models.PositiveIntegerField(default=0)
    n_val = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('-date_created',)

    def __str__(self):
        return f'{self.classifier.slug_version} training {self.id} ({self.status})'


class ClassifierApplyRun(BaseModel):
    """One apply run: a trained model scoring a target, the Apply tab's rows.

    The service reports progress as it writes scores back
    (``classifications["slug/v"] = score`` on the image documents), so
    ``processed``/``total`` is a live progress bar, not an estimate.
    """

    classifier = models.ForeignKey(Classifier, on_delete=models.CASCADE, related_name='apply_runs')
    training = models.ForeignKey(ClassifierTraining, on_delete=models.CASCADE, related_name='apply_runs')
    author = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=16, choices=ApplyRunStatus.choices, default=ApplyRunStatus.LAUNCHED)
    dagster_run_id = models.CharField(max_length=64, blank=True, default='')
    # dataset | query | source | tag | all, plus its value — the diagram's targets.
    target_type = models.CharField(max_length=16)
    target_value = models.CharField(max_length=255, blank=True, default='')
    processed = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('-date_created',)

    def __str__(self):
        return f'{self.classifier.slug_version} apply {self.id} ({self.status})'
