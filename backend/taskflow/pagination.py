from rest_framework.pagination import PageNumberPagination


class StandardResultsPagination(PageNumberPagination):
	"""Explicit paginator for the project's APIView-based list endpoints.

	Not enabled globally in REST_FRAMEWORK settings — each paginated view
	uses this class explicitly so non-list responses stay untouched.

	Response format (standard DRF):
	    {"count": <int>, "next": <url|null>, "previous": <url|null>,
	     "results": [...]}

	Query parameters:
	    page        1-based page number (default 1)
	    page_size   items per page; default 25, capped at MAX_PAGE_SIZE

	Filtering and ordering are applied to the queryset BEFORE pagination,
	so LIMIT/OFFSET run against the fully filtered, deterministically
	ordered queryset.
	"""

	page_size = 25
	page_size_query_param = 'page_size'
	max_page_size = 100
