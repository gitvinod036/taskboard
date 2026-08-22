from django.urls import path

from .views import AdminAssignmentsView, AdminDashboardView, AdminSubmissionReviewView, AdminSubmissionsView, AdminTechStacksView, AdminUserDetailView, AdminUserTaskDeleteView, AdminUserTasksView, AdminUsersView

urlpatterns = [
	path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
	path('users/', AdminUsersView.as_view(), name='admin-users'),
	path('tech-stacks/', AdminTechStacksView.as_view(), name='admin-tech-stacks'),
	path('users/<int:user_id>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
	path('users/<int:user_id>/tasks/', AdminUserTasksView.as_view(), name='admin-user-tasks'),
	path('users/<int:user_id>/tasks/<int:task_id>/', AdminUserTaskDeleteView.as_view(), name='admin-user-task-delete'),
	path('assignments/', AdminAssignmentsView.as_view(), name='admin-assignments'),
	path('submissions/', AdminSubmissionsView.as_view(), name='admin-submissions'),
	path('submissions/<int:submission_id>/', AdminSubmissionReviewView.as_view(), name='admin-submission-review'),
]