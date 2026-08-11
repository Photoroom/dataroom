
# Installation

```
pip install dataroom-client
```


# Usage

After getting an account you can find your API key on the settings page.

The API is grouped into resource namespaces: `images`, `groups`, `datasets`,
`group_types`, `roles`, `queries` and `tags`.

```
from dataroom_client import DataRoomClient

DataRoom = DataRoomClient(api_key='YOUR_SECRET_API_KEY_HERE', api_url='YOUR_API_URL_HERE')

# landscape images from one ingest source
images = await DataRoom.images.list(sources=['local_dataset'], aspect_ratio__gt=1.5, limit=100)

# one image with its metadata
image = await DataRoom.images.get(images[0]['id'])

# every version of one dataset
datasets = await DataRoom.datasets.list(slug='training-set')
```

`DataRoomClientSync` exposes the same namespaces with blocking calls (no
`await`). The pre-namespace flat methods (`get_images()`, `create_dataset()`,
...) still work and are thin aliases of the namespace methods.

Worked examples, one notebook per area:
[client_example](../notebooks/client_example.ipynb) (images and tags),
[groups_example](../notebooks/groups_example.ipynb),
[datasets_example](../notebooks/datasets_example.ipynb),
[queries_example](../notebooks/queries_example.ipynb) and
[loader_example](../notebooks/loader_example.ipynb) (bulk upload).


# Developing

Follow the instructions in the main [README](../README.md).
