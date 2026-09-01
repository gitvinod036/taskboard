from django.urls import path

from .views import AdminCheckView, GoogleCallbackView, GoogleLoginView, GoogleTokenExchangeView, LoginView, LogoutView, MeTechStackView, MeView, NotificationListView, NotificationMarkReadView, NotificationPreferenceView, PasswordResetConfirmView, PasswordResetRequestView, RegisterView, TaskDraftAIView

app_name = 'taskflow'

urlpatterns = [
	path('register/', RegisterView.as_view(), name='register'),
	path('login/', LoginView.as_view(), name='login'),
	path('google/', GoogleLoginView.as_view(), name='google-login'),
	path('google/callback/', GoogleCallbackView.as_view(), name='google-callback'),
	path('google/exchange/', GoogleTokenExchangeView.as_view(), name='google-exchange'),
	path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
	path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
	path('logout/', LogoutView.as_view(), name='logout'),
	path('me/', MeView.as_view(), name='me'),
	path('me/tech-stack/', MeTechStackView.as_view(), name='me-tech-stack'),
	path('me/notification-preferences/', NotificationPreferenceView.as_view(), name='me-notification-preferences'),
	path('me/notifications/', NotificationListView.as_view(), name='me-notifications'),
	path('me/notifications/mark-read/', NotificationMarkReadView.as_view(), name='me-notifications-mark-read'),
	path('admin-check/', AdminCheckView.as_view(), name='admin-check'),
	path('ai/task-draft/', TaskDraftAIView.as_view(), name='ai-task-draft'),
]

