import types
from contextlib import contextmanager
from datetime import UTC, datetime

import botocore.auth
import storages.backends.s3 as s3_storage

# A stable URL is signed as of the start of the current UTC day and stays valid for
# this many days. With 2 days, a URL minted any time today is valid until the end of
# tomorrow (e.g. minted Monday 08:00 -> valid through the end of Tuesday).
STABLE_URL_VALID_DAYS = 2
# Pass this as ``default_storage.url(name, expire=STABLE_URL_VALID_SECONDS)`` so the
# signed URL expires a stable number of seconds after the frozen midnight signing time.
STABLE_URL_VALID_SECONDS = STABLE_URL_VALID_DAYS * 24 * 60 * 60

# botocore.auth references the datetime *module* (datetime.datetime.utcnow()).
_AUTH_DATETIME_ORIGINAL = botocore.auth.datetime
# storages.backends.s3 imports the datetime *class* (from datetime import datetime).
_S3_DATETIME_ORIGINAL = s3_storage.datetime


def _frozen_clock(frozen):
    """A ``datetime.datetime`` subclass whose ``utcnow()`` returns a fixed instant.

    Everything else (``strptime`` etc.) is inherited unchanged, so it is a drop-in
    replacement for the ``datetime`` references used while signing storage URLs.
    """

    class _Clock(datetime):
        @classmethod
        def utcnow(cls):
            return frozen

    return _Clock


@contextmanager
def stable_signing_time():
    """Sign storage URLs as of midnight UTC so each object yields one stable URL per day.

    Callers should pair this with ``expire=STABLE_URL_VALID_SECONDS`` on the
    ``storage.url(...)`` call so the URL's lifetime is stable too.
    """
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    clock = _frozen_clock(start_of_day)

    botocore.auth.datetime = types.SimpleNamespace(datetime=clock)
    s3_storage.datetime = clock
    try:
        yield
    finally:
        botocore.auth.datetime = _AUTH_DATETIME_ORIGINAL
        s3_storage.datetime = _S3_DATETIME_ORIGINAL
