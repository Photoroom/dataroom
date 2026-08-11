"""Trace filters for Datadog APM.

``ddtrace.filters.FilterRequestsOnUrl`` was removed in ddtrace 3.0 (along with
the whole ``ddtrace.filters`` module). This reimplements the only one we used —
dropping traces for health-check requests — as a ``TraceFilter`` plugged into
``tracer.configure(trace_processors=...)`` (the v3 replacement for the old
``settings={'FILTERS': [...]}``).
"""

import re

from ddtrace.ext import http
from ddtrace.trace import TraceFilter


class FilterRequestsOnUrl(TraceFilter):
    """Drop a trace when its root span's ``http.url`` matches any regex."""

    def __init__(self, regexps):
        if isinstance(regexps, str):
            regexps = [regexps]
        self._regexps = [re.compile(regexp) for regexp in regexps]

    def process_trace(self, trace):
        for span in trace:
            url = span.get_tag(http.URL)
            if span.parent_id is None and url is not None:
                for regexp in self._regexps:
                    if regexp.match(url):
                        return None
        return trace
