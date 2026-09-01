"""End-to-end notification workflow tests.

All AI calls are mocked at the AIClient.evaluate_task seam (no network, no
provider quota usage). Notification creation is server-side only; every
event is idempotent per (recipient, event_key).
"""
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase
from unittest.mock import patch

from taskflow.models import Notification, Task, TaskAssignment, TaskSubmission
from taskflow.services import AIClient, notify_task_published

User = get_user_model()

VALID_EVAL = {
    "scores": {"requirement_completion": 3, "correctness": 2, "quality": 1, "completeness": 1, "clarity": 1},
    "total_score": 99,  # deliberately wrong; backend must recompute (8)
    "summary": "Solid work.",
    "strengths": [], "issues": [], "suggestions": [],
}


def ai_patch(**kwargs):
    return patch.object(AIClient, "evaluate_task", **kwargs)


class NotificationTestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="worker", password="x", email="w@t.local")
        self.other = User.objects.create_user(username="other", password="x", email="o@t.local")
        self.admin = User.objects.create_user(username="admin1", password="x", email="a@t.local", is_staff=True)
        self.admin2 = User.objects.create_user(username="admin2", password="x", email="a2@t.local", is_staff=True)
        self.task = Task.objects.create(title="Build a REST API", description="Do it", difficulty="EASY")
        TaskAssignment.objects.create(task=self.task, user=self.user)
        self.client = APIClient()

    def auth(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def make_submission(self, user, stat=TaskSubmission.Status.PENDING):
        return TaskSubmission.objects.create(
            task=self.task, user=user,
            git_url="https://github.com/demo/repo",
            linkedin_url="https://linkedin.com/in/demo",
            status=stat,
        )

    def review(self, submission, new_status):
        self.auth(self.admin)
        return self.client.patch(
            f"/api/admin/submissions/{submission.pk}/",
            {"status": new_status, "feedback": "ok"},
            format="json",
        )


@override_settings(AI_API_KEY="test")
class TaskPublishedNotificationTests(NotificationTestBase):
    def test_task_creation_notifies_users_not_creator(self):
        self.auth(self.admin)
        response = self.client.post("/api/tasks/", {
            "title": "Fresh task", "description": "New", "difficulty": "EASY",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Notification.objects.filter(recipient=self.user, title="New Task Available").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.other, title="New Task Available").exists())
        # The creating admin is NOT notified.
        self.assertFalse(Notification.objects.filter(recipient=self.admin, title="New Task Available").exists())
        notification = Notification.objects.get(recipient=self.user, title="New Task Available")
        self.assertEqual(notification.url, "/my-tasks")

    def test_duplicate_publication_event_creates_no_duplicates(self):
        notify_task_published(self.task, creator=self.admin)
        notify_task_published(self.task, creator=self.admin)
        # Only the two normal users; replaying the event adds no rows.
        self.assertEqual(Notification.objects.filter(title="New Task Available").count(), 2)


class SubmissionNotificationTests(NotificationTestBase):
    def test_submission_notifies_admins_with_task_reference(self):
        self.auth(self.user)
        response = self.client.post(f"/api/tasks/{self.task.pk}/submit/", {
            "git_url": "https://github.com/me/repo",
            "linkedin_url": "https://linkedin.com/in/me",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        for admin in (self.admin, self.admin2):
            notification = Notification.objects.get(recipient=admin, title="New Task Submission")
            self.assertEqual(notification.url, "/admin/submissions")
            self.assertIn("worker", notification.message)
            self.assertIn(self.task.title, notification.message)
        self.assertFalse(Notification.objects.filter(recipient=self.user, title="New Task Submission").exists())

    def test_resubmission_sends_improved_submission_notification(self):
        self.make_submission(self.user, TaskSubmission.Status.REJECTED)
        self.auth(self.user)
        response = self.client.post(f"/api/tasks/{self.task.pk}/submit/", {
            "git_url": "https://github.com/me/repo2",
            "linkedin_url": "https://linkedin.com/in/me",
        }, format="json")
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertTrue(Notification.objects.filter(recipient=self.admin, title="Improved Submission").exists())

    def test_review_outcome_notifies_submitter(self):
        submission = self.make_submission(self.user)
        response = self.review(submission, TaskSubmission.Status.REJECTED)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rejected = Notification.objects.get(recipient=self.user, title="Task Rejected")
        self.assertIn(self.task.title, rejected.message)
        response = self.review(submission, TaskSubmission.Status.APPROVED)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Notification.objects.filter(recipient=self.user, title="Task Approved").exists())

    def test_repeat_review_does_not_duplicate(self):
        submission = self.make_submission(self.user)
        self.review(submission, TaskSubmission.Status.APPROVED)
        self.review(submission, TaskSubmission.Status.APPROVED)
        self.assertEqual(Notification.objects.filter(recipient=self.user, title="Task Approved").count(), 1)

    def test_evaluation_success_notifies_with_server_score(self):
        submission = self.make_submission(self.user, TaskSubmission.Status.APPROVED)
        self.auth(self.user)
        with ai_patch(return_value=VALID_EVAL):
            response = self.client.post(f"/api/my/tasks/submissions/{submission.pk}/evaluation/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = Notification.objects.get(recipient=self.user, title="Task Evaluated")
        self.assertIn("8/10", notification.message)  # server-recomputed, not the AI's 99

    def test_failed_evaluation_sends_no_notification(self):
        submission = self.make_submission(self.user, TaskSubmission.Status.APPROVED)
        self.auth(self.user)
        with ai_patch(side_effect=RuntimeError("providers down")):
            response = self.client.post(f"/api/my/tasks/submissions/{submission.pk}/evaluation/")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(Notification.objects.filter(recipient=self.user, title="Task Evaluated").exists())


class NotificationAccessTests(NotificationTestBase):
    def setUp(self):
        super().setUp()
        self.mine = Notification.objects.create(
            recipient=self.user, title="Task Approved", message="m", url="/my-tasks", event_key="k1")
        self.theirs = Notification.objects.create(
            recipient=self.other, title="Task Evaluated", message="m2", url="/my-tasks", event_key="k2")

    def test_list_returns_only_own_notifications(self):
        self.auth(self.user)
        response = self.client.get("/api/auth/me/notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.mine.pk, ids)
        self.assertNotIn(self.theirs.pk, ids)
        self.assertEqual(response.data["unread_count"], 1)

    def test_unauthenticated_list_is_rejected(self):
        response = self.client.get("/api/auth/me/notifications/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_mark_one_read(self):
        self.auth(self.user)
        response = self.client.post("/api/auth/me/notifications/mark-read/", {"id": self.mine.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mine.refresh_from_db()
        self.assertTrue(self.mine.is_read)
        self.assertEqual(response.data["unread_count"], 0)

    def test_mark_all_read(self):
        Notification.objects.create(
            recipient=self.user, title="Task Evaluated", message="m3", url="/my-tasks", event_key="k3")
        self.auth(self.user)
        response = self.client.post("/api/auth/me/notifications/mark-read/", {"all": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.filter(recipient=self.user, is_read=False).count(), 0)
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.is_read)

    def test_cannot_mark_another_users_notification(self):
        self.auth(self.user)
        response = self.client.post("/api/auth/me/notifications/mark-read/", {"id": self.theirs.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["marked"], 0)
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.is_read)

    def test_newest_first_ordering(self):
        newest = Notification.objects.create(
            recipient=self.user, title="Task Evaluated", message="new", url="/my-tasks", event_key="k4")
        self.auth(self.user)
        response = self.client.get("/api/auth/me/notifications/")
        self.assertEqual(response.data["results"][0]["id"], newest.pk)
