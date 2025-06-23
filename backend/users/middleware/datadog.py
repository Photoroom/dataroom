from ddtrace import tracer
from django.utils.deprecation import MiddlewareMixin


class DatadogUserEmailMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            root_span = tracer.current_root_span()
            if root_span:
                root_span.set_tag("user.email", request.user.email)
