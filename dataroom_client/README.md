
# Installation

```
pip install dataroom-client
```


# Usage

After getting an account you can find your API key on the settings page.

```
from dataroom_client import DataRoomClient

DataRoom = DataRoomClient(api_key='YOUR_SECRET_API_KEY_HERE', api_url='YOUR_API_URL_HERE')

images = await DataRoom.get_images()
```

For more examples see [client_example.ipynb](./notebooks/client_example.ipynb).


# Developing

Follow the instructions in the main [README](../README.md).
