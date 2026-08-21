from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
	message = 'Admin access is required.'

	def has_permission(self, request, view):
		return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))


class IsNormalUser(BasePermission):
	message = 'Normal user access is required.'

	def has_permission(self, request, view):
		return bool(request.user and request.user.is_authenticated and not request.user.is_staff and not request.user.is_superuser)
