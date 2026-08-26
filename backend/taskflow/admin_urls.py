from django.urls import path

from .views import (
    AdminAssignmentsView, AdminCodeSubmissionDetailView, AdminCodingProblemDetailView,
    AdminCodingProblemsView, AdminCodingSubmissionsView, AdminDashboardView,
    AdminSubmissionReviewView, AdminSubmissionsView, AdminTechStacksView,
    AdminUserDetailView, AdminUserTaskDeleteView, AdminUserTasksView,
    AdminUsersView, CodingProblemGenerateView,
)

urlpatterns = [
	path('users/', AdminUsersView.as_view(), name='admin-users'),
	path('tech-stacks/', AdminTechStacksView.as_view(), name='admin-tech-stacks'),
	path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
	path('users/<int:user_id>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
	path('users/<int:user_id>/tasks/', AdminUserTasksView.as_view(), name='admin-user-tasks'),
	path('users/<int:user_id>/tasks/<int:task_id>/', AdminUserTaskDeleteView.as_view(), name='admin-user-task-delete'),
	path('assignments/', AdminAssignmentsView.as_view(), name='admin-assignments'),
	path('submissions/', AdminSubmissionsView.as_view(), name='admin-submissions'),
	path('submissions/<int:submission_id>/', AdminSubmissionReviewView.as_view(), name='admin-submission-review'),
	path('coding/problems/', AdminCodingProblemsView.as_view(), name='admin-coding-problems'),
	path('coding/problems/<int:problem_id>/', AdminCodingProblemDetailView.as_view(), name='admin-coding-problem-detail'),
	path('coding/problems/generate/', CodingProblemGenerateView.as_view(), name='admin-coding-problem-generate'),
	path('coding/submissions/', AdminCodingSubmissionsView.as_view(), name='admin-coding-submissions'),
	path('coding/submissions/<int:submission_id>/', AdminCodeSubmissionDetailView.as_view(), name='admin-coding-submission-detail'),
]