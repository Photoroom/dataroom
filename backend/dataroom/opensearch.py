import os
from collections import namedtuple

import boto3
from django.conf import settings
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.helpers import bulk
from requests_aws4auth import AWS4Auth


class OSClass:
    """
    OpenSearch client wrapper.

    Usage:

        from dataroom.opensearch import OS
        from dataroom.models.os_image import OSImage

        OS.client.search(index=OSImage.INDEX, body={'query': {'match_all': {}}})
        OS.client.count(index=OSImage.INDEX)

    Manual requests:

        OS.client.transport.perform_request('GET', '/_cluster/health')

    """

    def __init__(self):
        self.boto_session = None
        self.connection_pool_size = 120

        if settings.AWS_OPEN_SEARCH_UNAUTHENTICATED_REQUESTS or os.environ.get('IS_BUILD_PROCESS', False):
            # Create the OpenSearch client
            self.client = OpenSearch(
                hosts=settings.AWS_OPEN_SEARCH_URL,
                maxsize=self.connection_pool_size,
                timeout=60,
            )
        else:
            # Check if explicit credentials are provided in settings
            has_explicit_credentials = (
                hasattr(settings, 'AWS_OPEN_SEARCH_ACCESS_KEY_ID')
                and hasattr(settings, 'AWS_OPEN_SEARCH_SECRET_ACCESS_KEY')
                and settings.AWS_OPEN_SEARCH_ACCESS_KEY_ID
                and settings.AWS_OPEN_SEARCH_SECRET_ACCESS_KEY
            )

            if has_explicit_credentials:
                # Use explicit credentials with auto-refresh
                self.boto_session = boto3.Session(
                    aws_access_key_id=settings.AWS_OPEN_SEARCH_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_OPEN_SEARCH_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_OPEN_SEARCH_REGION_NAME,
                )
                credentials = self.boto_session.get_credentials()
            else:
                # Use default credential chain (IAM roles, env vars, etc.)
                self.boto_session = boto3.Session(
                    region_name=settings.AWS_OPEN_SEARCH_REGION_NAME,
                )
                credentials = self.boto_session.get_credentials()

            # Set up AWS4Auth with refreshable credentials
            self.awsauth = AWS4Auth(
                refreshable_credentials=credentials, region=settings.AWS_OPEN_SEARCH_REGION_NAME, service='es'
            )

            # Create the OpenSearch client
            self.client = OpenSearch(
                hosts=settings.AWS_OPEN_SEARCH_URL,
                http_auth=self.awsauth,
                connection_class=RequestsHttpConnection,
                use_ssl=True,
                verify_certs=True,
                maxsize=self.connection_pool_size,
                timeout=60,
            )


OS = OSClass()


OSDoc = namedtuple('OSDoc', ('index', 'doc_id', 'body'))


class OSBulkIndex:
    """
    OpenSearch bulk index context manager.

    Usage:

        from dataroom.opensearch import OSBulkIndex
        from dataroom.models.os_image import OSImage

        with OSBulkIndex() as os_bulk:
            for image in my_unsaved_images:
                image.save(fields=['source'], bulk_index=os_bulk)
                # or directly:
                os_bulk.index(index=OSImage.INDEX, doc_id='1', body={'field': 'value'})

    """

    def __init__(self, bulk_size=100, refresh=settings.OPENSEARCH_DEFAULT_REFRESH, timeout=25):
        self._docs = []
        self.bulk_size = bulk_size
        self.refresh = 'true' if refresh else 'false'
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._flush()

    def _flush(self):
        if len(self._docs):
            body = [
                {
                    "_index": doc.index,
                    "_id": doc.doc_id,
                    "doc": doc.body,
                    # perform an update or insert
                    "_op_type": "update",
                    'doc_as_upsert': True,
                }
                for doc in self._docs
            ]
            bulk(
                client=OS.client,
                actions=body,
                params={
                    'timeout': self.timeout,
                    'refresh': self.refresh,
                },
            )
            self._docs = []

    def index(self, index, doc_id, body):
        self._docs.append(OSDoc(index=index, doc_id=doc_id, body=body))
        if len(self._docs) >= self.bulk_size:
            self._flush()
