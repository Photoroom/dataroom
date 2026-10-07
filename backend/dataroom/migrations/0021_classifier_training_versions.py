# Which code trained a model and which labelled sets it saw, as the classifier
# service reports them. Dataroom compares them with the current ones instead of
# counting examples to decide whether a version needs retraining.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('dataroom', '0020_classifiers'),
    ]

    operations = [
        migrations.AddField(
            model_name='classifiertraining',
            name='labels_version',
            field=models.CharField(blank=True, default='', max_length=1024),
        ),
        migrations.AddField(
            model_name='classifiertraining',
            name='code_version',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
