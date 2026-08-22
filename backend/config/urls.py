# from django.contrib import admin
# from django.urls import include, path
# from django.http import JsonResponse

# urlpatterns = [
#     path("health/", health_check),
#     path('admin/', admin.site.urls),
#     path('api/auth/', include('taskflow.urls')),
#     path('api/tasks/', include('taskflow.task_urls')),
#     path('api/my/tasks/', include('taskflow.my_task_urls')),
#     path('api/admin/', include('taskflow.admin_urls')),
# ]


# def health_check(request):
#     return JsonResponse({
#         "status": "ok",
#         "service": "TaskBoard API"
#     })

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "TaskBoard API"
    })


urlpatterns = [
    path("", health_check),

    path("admin/", admin.site.urls),

    path("api/auth/", include("taskflow.urls")),
    path("api/tasks/", include("taskflow.task_urls")),
    path("api/my/tasks/", include("taskflow.my_task_urls")),
    path("api/admin/", include("taskflow.admin_urls")),
]