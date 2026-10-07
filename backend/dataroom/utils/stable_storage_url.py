import contextvars
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

# The frozen instant for the current thread / task, None outside the context. A
# context variable, not a module global: botocore and django-storages are shared by
# every request in the process, and a real upload signed while another request was
# minting stable URLs used to go out stamped midnight, which S3 rejects as
# RequestTimeTooSkewed once the day is more than 15 minutes old.
_frozen: contextvars.ContextVar[datetime | None] = contextvars.ContextVar('stable_signing_time', default=None)


class _Clock(datetime):
    """A ``datetime.datetime`` whose ``utcnow()`` is frozen only inside
    ``stable_signing_time()``; everything else is inherited unchanged."""

    @classmethod
    def utcnow(cls):
        frozen = _frozen.get()
        return frozen if frozen is not None else datetime.now(UTC).replace(tzinfo=None)


# Installed once, for the life of the process. Outside the context the clock is the
# real one, so this is a no-op for every other caller.
# botocore.auth references the datetime *module* (datetime.datetime.utcnow()).
botocore.auth.datetime = types.SimpleNamespace(datetime=_Clock)
# storages.backends.s3 imports the datetime *class* (from datetime import datetime).
s3_storage.datetime = _Clock


@contextmanager
def stable_signing_time():
    """Sign storage URLs as of midnight UTC so each object yields one stable URL per day.

    Callers should pair this with ``expire=STABLE_URL_VALID_SECONDS`` on the
    ``storage.url(...)`` call so the URL's lifetime is stable too. Only this
    thread's (or task's) signing is affected.
    """
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    token = _frozen.set(start_of_day)
    try:
        yield
    finally:
        _frozen.reset(token)
