from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination, _positive_int

API_PAGE_SIZE = 100
API_MAX_PAGE_SIZE = 2000


class CustomCursorPagination(CursorPagination):
    page_size = API_PAGE_SIZE
    max_page_size = API_MAX_PAGE_SIZE
    ordering = 'id'
    cursor_query_param = 'cursor'
    page_size_query_param = 'page_size'

    def get_ordering(self, request, queryset, view):
        if hasattr(view, 'ordering'):
            return view.ordering
        return super().get_ordering(request, queryset, view)

    def get_page_size(self, request):
        if self.page_size_query_param:
            try:
                page_size = _positive_int(
                    request.query_params[self.page_size_query_param],
                    strict=True,
                    cutoff=None,
                )
            except (KeyError, ValueError):
                pass
            else:
                if page_size > self.max_page_size:
                    raise ValidationError(
                        f'Page size should be at most {self.max_page_size}.',
                    )
                return page_size

        return self.page_size
