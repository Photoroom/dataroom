# Rename the typed datasets to just "datasets" now that the classic image-Dataset
# is gone (0017 dropped it, freeing the name + the dataroom_dataset table).
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dataroom', '0017_delete_dataset'),
    ]

    operations = [
        migrations.RenameModel(old_name='TypedDataset', new_name='Dataset'),
        migrations.RenameModel(old_name='TypedDatasetMembership', new_name='DatasetMembership'),
    ]
