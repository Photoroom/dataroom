import datetime
from urllib.parse import parse_qs, urlparse

import botocore.auth
import storages.backends.s3 as s3_storage
from freezegun import freeze_time
from storages.backends.s3boto3 import S3Boto3Storage

from backend.config.storage import OverwriteStorage
from backend.dataroom.utils.stable_storage_url import (
    STABLE_URL_VALID_DAYS,
    STABLE_URL_VALID_SECONDS,
    stable_signing_time,
)


def _s3_storage():
    # A real S3 storage; boto3 presigns offline (HMAC only), so no network is needed.
    return S3Boto3Storage(
        bucket_name='test-bucket',
        access_key='AKIAIOSFODNN7EXAMPLE',
        secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        region_name='us-east-1',
        querystring_auth=True,
        querystring_expire=60 * 60 * 24,  # 24h configured default
        signature_version='s3v4',
    )


def _params(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_signs_as_of_start_of_day():
    storage = _s3_storage()
    # Monday 8 o'clock.
    with freeze_time('2026-06-15 08:00:00'):
        with stable_signing_time():
            url = storage.url('image.jpg', expire=STABLE_URL_VALID_SECONDS)

    params = _params(url)
    # Signed as of the start of the day (midnight), not 08:00.
    assert params['X-Amz-Date'] == '20260615T000000Z'
    # Valid for the full 2-day window.
    assert params['X-Amz-Expires'] == str(STABLE_URL_VALID_DAYS * 24 * 60 * 60)


def test_monday_url_is_valid_until_end_of_tuesday():
    storage = _s3_storage()
    with freeze_time('2026-06-15 08:00:00'):  # Monday
        with stable_signing_time():
            url = storage.url('image.jpg', expire=STABLE_URL_VALID_SECONDS)

    params = _params(url)
    signed_at = datetime.datetime.strptime(params['X-Amz-Date'], '%Y%m%dT%H%M%SZ')
    expires_at = signed_at + datetime.timedelta(seconds=int(params['X-Amz-Expires']))

    # End of Tuesday == start of Wednesday.
    assert expires_at == datetime.datetime(2026, 6, 17, 0, 0, 0)


def test_url_is_stable_throughout_the_day():
    storage = _s3_storage()

    with freeze_time('2026-06-15 00:00:01'):  # Monday, just after midnight
        with stable_signing_time():
            early = storage.url('image.jpg', expire=STABLE_URL_VALID_SECONDS)

    with freeze_time('2026-06-15 23:59:59'):  # Monday, just before midnight
        with stable_signing_time():
            late = storage.url('image.jpg', expire=STABLE_URL_VALID_SECONDS)

    assert early == late


def test_url_changes_across_days():
    storage = _s3_storage()

    with freeze_time('2026-06-15 12:00:00'):  # Monday
        with stable_signing_time():
            monday = storage.url('image.jpg', expire=STABLE_URL_VALID_SECONDS)

    with freeze_time('2026-06-16 12:00:00'):  # Tuesday
        with stable_signing_time():
            tuesday = storage.url('image.jpg', expire=STABLE_URL_VALID_SECONDS)

    assert monday != tuesday


def test_the_clock_is_only_frozen_inside_the_context():
    # The patched clock stays installed for the life of the process; outside the
    # context it must report the real time, so nothing else sees a frozen clock.
    with freeze_time('2026-06-15 08:00:00'):
        with stable_signing_time():
            assert botocore.auth.datetime.datetime.utcnow() == datetime.datetime(2026, 6, 15, 0, 0, 0)
            assert s3_storage.datetime.utcnow() == datetime.datetime(2026, 6, 15, 0, 0, 0)
        assert botocore.auth.datetime.datetime.utcnow() == datetime.datetime(2026, 6, 15, 8, 0, 0)
        assert s3_storage.datetime.utcnow() == datetime.datetime(2026, 6, 15, 8, 0, 0)


def test_cloudfront_signed_url_is_valid_until_end_of_tomorrow():
    # CloudFront signing uses storages.backends.s3.datetime.utcnow() rather than boto3,
    # so verify it is frozen too. A fake signer records the expiration it is handed.
    seen = {}

    class _FakeCloudFrontSigner:
        def generate_presigned_url(self, url, date_less_than):
            seen['expiration'] = date_less_than
            return url

    storage = _s3_storage()
    storage.custom_domain = 'cdn.example.com'
    storage.cloudfront_signer = _FakeCloudFrontSigner()

    with freeze_time('2026-06-15 08:00:00'):  # Monday
        with stable_signing_time():
            storage.url('image.jpg', expire=STABLE_URL_VALID_SECONDS)

    # Signed at midnight Monday + 2 days == end of Tuesday.
    assert seen['expiration'] == datetime.datetime(2026, 6, 17, 0, 0, 0)


def test_filesystem_storage_accepts_expire():
    # default_storage in tests/local is OverwriteStorage (filesystem); it must accept the
    # S3-only ``expire`` argument (ignoring it) so callers can pass it uniformly.
    storage = OverwriteStorage()
    url = storage.url('image.jpg', expire=STABLE_URL_VALID_SECONDS)
    assert url.endswith('image.jpg')


def test_a_concurrent_request_outside_the_context_signs_with_the_real_time():
    """The frozen clock is per thread: a request signing a real upload while another
    request mints stable URLs must not be stamped midnight (S3: RequestTimeTooSkewed)."""
    import threading

    storage = _s3_storage()
    inside = threading.Event()
    release = threading.Event()
    other: dict = {}

    def mint_stable_urls():
        with stable_signing_time():
            inside.set()
            release.wait(5)

    def sign_outside():
        inside.wait(5)
        other['url'] = storage.url('upload.npy', expire=60)
        release.set()

    with freeze_time('2026-06-15 19:23:00'):
        threads = [threading.Thread(target=mint_stable_urls), threading.Thread(target=sign_outside)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)

    assert _params(other['url'])['X-Amz-Date'] == '20260615T192300Z'
