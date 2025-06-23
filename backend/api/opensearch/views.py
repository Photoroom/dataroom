from opensearchpy import TransportError
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.api.permissions import DataroomAccessPermission, OpensearchProxyPermission
from backend.dataroom.opensearch import OS


class OpenSearchAPIView(APIView):
    permission_classes = [DataroomAccessPermission, OpensearchProxyPermission]

    def get(self, request, path=""):
        path = f"/{path}"
        params = request.query_params.dict()
        try:
            result = OS.client.transport.perform_request('GET', path, params=params)
        except TransportError as e:
            response = e.info if isinstance(e.info, dict) else {'error': str(e.error)}
            return Response(response, status=e.status_code)
        return Response(result)
