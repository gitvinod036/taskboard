from django.urls import include, path
from django.http import JsonResponse
from django.contrib import admin


def health_check(request):
    return JsonResponse({"status": "ok", "service": "TaskBoard API"})


urlpatterns = [
    path("", health_check),

    path("admin/", admin.site.urls),

    path("api/auth/", include("taskflow.urls")),
    path("api/tasks/", include("taskflow.task_urls")),
    path("api/my/tasks/", include("taskflow.my_task_urls")),
    path("api/admin/", include("taskflow.admin_urls")),
    path("api/coding/", include("taskflow.coding_urls")),
]