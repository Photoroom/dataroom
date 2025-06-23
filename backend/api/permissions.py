from rest_framework.permissions import BasePermission


class DataroomAccessPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.has_perm('users.dataroom_access')


class OpensearchProxyPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.has_perm('users.opensearch_proxy')
