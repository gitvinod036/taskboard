from django.urls import path

from .views import (
	CodingLeaderboardView, CodingProblemDetailView, CodingProblemListView, CodingProblemRunView,
	CodingProblemSubmitView, CodingSubmissionDetailView, CodingSubmissionListView,
	SubmissionAnalysisView,
)

app_name = 'coding'

urlpatterns = [
    path('problems/', CodingProblemListView.as_view(), name='coding-problem-list'),
    path('problems/<int:problem_id>/', CodingProblemDetailView.as_view(), name='coding-problem-detail'),
    path('problems/<int:problem_id>/run/', CodingProblemRunView.as_view(), name='coding-problem-run'),
    path('problems/<int:problem_id>/submissions/', CodingProblemSubmitView.as_view(), name='coding-problem-submit'),
    path('submissions/', CodingSubmissionListView.as_view(), name='coding-submission-list'),
    path('submissions/<int:submission_id>/', CodingSubmissionDetailView.as_view(), name='coding-submission-detail'),
    path('submissions/<int:submission_id>/analyze/', SubmissionAnalysisView.as_view(), name='coding-submission-analyze'),
    path('leaderboard/', CodingLeaderboardView.as_view(), name='coding-leaderboard'),
]