from django.urls import path

from .views import MyTasksView, TaskSubmissionEvaluationView

urlpatterns = [
	path('', MyTasksView.as_view(), name='my-tasks'),
	path('submissions/<int:submission_id>/evaluation/', TaskSubmissionEvaluationView.as_view(), name='task-submission-evaluation'),
]