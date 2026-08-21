from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('taskflow.urls')),
    path('api/tasks/', include('taskflow.task_urls')),
    path('api/my/tasks/', include('taskflow.my_task_urls')),
    path('api/admin/', include('taskflow.admin_urls')),
]
