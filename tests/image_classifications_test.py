import pytest
import requests

from backend.dataroom.models.os_image import OSImage
from backend.dataroom.opensearch import OS


@pytest.fixture
def scored(image_logo, image_girl, image_perfume, image_logo_alt):
    for image, score in ((image_logo, 0.9), (image_girl, 0.6), (image_perfume, 0.2)):
        image.classifications = {'studio/1': score}
        image.save(fields=['classifications'])
    OS.client.indices.refresh(index=OSImage.INDEX)
    return [image_logo, image_girl, image_perfume, image_logo_alt]


@pytest.mark.django_db
def test_classifications_readable_opt_in(live_server, token, scored):
    headers = {'Authorization': f'Token {token.key}'}
    url = f'{live_server.url}/api/images/{scored[0].id}/'
    assert 'classifications' not in requests.get(url, headers=headers).json()
    image = requests.get(f'{url}?fields=id,classifications', headers=headers).json()
    assert image['classifications'] == {'studio/1': 0.9}


@pytest.mark.django_db
def test_classifications_score_filter(live_server, token, scored):
    headers = {'Authorization': f'Token {token.key}'}

    def count(params):
        return requests.get(f'{live_server.url}/api/images/count/?{params}', headers=headers).json()['count']

    assert count('classifications=studio/1__gte:0.5') == 2
    assert count('classifications=studio/1__gte:0.85') == 1
    assert count('classifications=studio/1__lte:0.5') == 1
    assert count('classifications=studio/1__gt:0.9') == 0
    assert count('classifications=studio/1__eq:0.6') == 1
    assert count('classifications=studio/1:0.6') == 1
    assert count('has_classifications=studio/1') == 3
    assert count('lacks_classifications=studio/1') == 1

    for bad in ('studio/1__between:0.5', 'studio/1:high'):
        response = requests.get(f'{live_server.url}/api/images/count/?classifications={bad}', headers=headers)
        assert response.status_code == 400
