from django.urls import path

from .views import MyTasksView, TaskAssignmentView, TaskDetailView, TaskListCreateView, TaskSubmissionView, TechStacksView

app_name = 'tasks'

urlpatterns = [
	path('', TaskListCreateView.as_view(), name='task-list-create'),
	path('tech-stacks/', TechStacksView.as_view(), name='tech-stacks'),
	path('<int:task_id>/', TaskDetailView.as_view(), name='task-detail'),
	path('<int:task_id>/assign/', TaskAssignmentView.as_view(), name='task-assign'),
	path('<int:task_id>/submit/', TaskSubmissionView.as_view(), name='task-submit'),
]