from django.db import connection
from django.http import HttpResponse


class HealthCheckMiddleware:
    """
    For HTTP or HTTPS health check requests, the host header contains the IP address of the load balancer node and the
    listener port, not the IP address of the target and the health check port.
    We don't know the Load Balancer IP address. Also, this IP can be changed after some time. Therefore, we cannot add
    the Load Balancer host to the ALLOWED_HOSTS.
    This is why this middleware is needed and must come before SecurityMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/_health/":
            # Check DB connection is healthy
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

            return HttpResponse("OK")

        return self.get_response(request)
