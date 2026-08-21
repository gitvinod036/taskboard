from django.urls import path

from .views import MyTasksView

urlpatterns = [
	path('', MyTasksView.as_view(), name='my-tasks'),
]