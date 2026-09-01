"""Normal-task AI evaluation + best-score leaderboard tests.

The AI layer is fully mocked (no network, no Gemini quota usage): the view
level `generate_task_evaluation` seam is patched, so the tests exercise the
real validation, persistence, best-score and leaderboard logic on top of it.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase
from unittest.mock import patch

from taskflow.models import Task, TaskAssignment, TaskEvaluation, TaskSubmission
from taskflow.services import AIClient, leaderboard

User = get_user_model()

VALID_EVAL = {
    "scores": {
        "requirement_completion": 3,
        "correctness": 2,
        "quality": 1,
        "completeness": 1,
        "clarity": 1,
    },
    "total_score": 99,  # deliberately wrong: the backend must recompute (8)
    "summary": "Solid work overall.",
    "strengths": ["Clear structure"],
    "issues": ["Edge case missed"],
    "suggestions": ["Add tests"],
}

LOWER_EVAL = {
    "scores": {"requirement_completion": 1, "correctness": 1, "quality": 1, "completeness": 1, "clarity": 1},
    "total_score": 99,
    "summary": "Weaker attempt.",
    "strengths": [],
    "issues": ["Incomplete"],
    "suggestions": ["Improve"],
}

INVALID_EVAL = {
    "scores": {"requirement_completion": 3, "correctness": 2, "quality": 5, "completeness": 2, "clarity": 1},
    "total_score": 13, "summary": "x", "strengths": [], "issues": [], "suggestions": [],
}


def ai_patch(**kwargs):
    """Patch the AI call seam (AIClient.evaluate_task) under a test API key.

    AIClient.configured checks for a real key; with AI_API_KEY present the
    real `generate_task_evaluation` validation/recompute path runs, so the
    tests prove the backend never trusts an AI-supplied total.
    """
    return patch.object(AIClient, "evaluate_task", **kwargs)


def make_url(submission_id):
    return f"/api/my/tasks/submissions/{submission_id}/evaluation/"


class EvaluationTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="x", email="o@t.local")
        self.other = User.objects.create_user(username="other", password="x", email="o2@t.local")
        self.admin = User.objects.create_user(username="admin1", password="x", email="a@t.local", is_staff=True)
        self.task = Task.objects.create(title="Audit task", description="Do the thing", difficulty="EASY")
        TaskAssignment.objects.create(task=self.task, user=self.owner)
        self.client = APIClient()

    def make_submission(self, user, status=TaskSubmission.Status.APPROVED, points=0, task=None):
        return TaskSubmission.objects.create(
            task=task or self.task, user=user,
            git_url="https://github.com/demo/repo",
            linkedin_url="https://linkedin.com/in/demo",
            status=status, earned_points=points,
        )

    def auth(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")


@override_settings(AI_API_KEY='test')
class EvaluationWorkflowTests(EvaluationTestBase):
    def test_rejected_submission_cannot_be_evaluated(self):
        sub = self.make_submission(self.owner, status=TaskSubmission.Status.REJECTED)
        self.auth(self.owner)
        response = self.client.post(make_url(sub.pk))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(TaskEvaluation.objects.filter(submission=sub).exists())

    def test_pending_submission_cannot_be_evaluated(self):
        sub = self.make_submission(self.owner, status=TaskSubmission.Status.PENDING)
        self.auth(self.owner)
        self.assertEqual(self.client.post(make_url(sub.pk)).status_code, status.HTTP_409_CONFLICT)

    def test_accepted_submission_evaluation_completes(self):
        sub = self.make_submission(self.owner)
        self.auth(self.owner)
        with ai_patch(return_value=VALID_EVAL):
            response = self.client.post(make_url(sub.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["status"], TaskEvaluation.Status.COMPLETED)
        # Backend recomputed the total from the rubric (3+2+1+1+1), ignoring
        # the AI-supplied total_score of 99.
        self.assertEqual(body["total_score"], 8)
        self.assertEqual(body["best_score"], 8)

    def test_out_of_range_category_is_rejected_safely(self):
        sub = self.make_submission(self.owner)
        self.auth(self.owner)
        with ai_patch(return_value=INVALID_EVAL):
            response = self.client.post(make_url(sub.pk))
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        evaluation = TaskEvaluation.objects.get(submission=sub)
        self.assertEqual(evaluation.status, TaskEvaluation.Status.FAILED)
        self.assertEqual(evaluation.total_score, 0)

    def test_provider_failure_marks_failed_and_returns_503(self):
        sub = self.make_submission(self.owner)
        self.auth(self.owner)
        with ai_patch(side_effect=RuntimeError("AI provider request failed")):
            response = self.client.post(make_url(sub.pk))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        evaluation = TaskEvaluation.objects.get(submission=sub)
        self.assertEqual(evaluation.status, TaskEvaluation.Status.FAILED)
        self.assertEqual(evaluation.total_score, 0)

    def test_regeneration_updates_the_existing_row(self):
        sub = self.make_submission(self.owner)
        self.auth(self.owner)
        with ai_patch(return_value=VALID_EVAL):
            self.client.post(make_url(sub.pk))
        with ai_patch(return_value=LOWER_EVAL):
            self.client.post(make_url(sub.pk))
        self.assertEqual(TaskEvaluation.objects.filter(submission=sub).count(), 1)
        self.assertEqual(TaskEvaluation.objects.get(submission=sub).summary, "Weaker attempt.")

    def test_owner_can_read_evaluation(self):
        sub = self.make_submission(self.owner)
        self.auth(self.owner)
        with ai_patch(return_value=VALID_EVAL):
            self.client.post(make_url(sub.pk))
        self.assertEqual(self.client.get(make_url(sub.pk)).status_code, status.HTTP_200_OK)

    def test_other_user_cannot_access_evaluation(self):
        sub = self.make_submission(self.owner)
        self.auth(self.other)
        self.assertEqual(self.client.get(make_url(sub.pk)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(make_url(sub.pk)).status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_read_evaluation(self):
        sub = self.make_submission(self.owner)
        self.auth(self.admin)
        with ai_patch(return_value=VALID_EVAL):
            self.client.post(make_url(sub.pk))
        self.assertEqual(self.client.get(make_url(sub.pk)).status_code, status.HTTP_200_OK)

    def test_anonymous_cannot_access(self):
        sub = self.make_submission(self.owner)
        self.assertEqual(self.client.get(make_url(sub.pk)).status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(AI_API_KEY='test')
class ResubmissionHistoryTests(EvaluationTestBase):
    def test_rejected_attempt_is_preserved_on_resubmission(self):
        rejected = self.make_submission(self.owner, status=TaskSubmission.Status.REJECTED)
        # The resubmit endpoint creates a NEW row; the old attempt must
        # remain untouched regardless of the new payload's validity.
        self.auth(self.owner)
        self.client.post(f"/api/tasks/submissions/{self.task.pk}/", {}, format="json")
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, TaskSubmission.Status.REJECTED)
        self.assertEqual(
            TaskSubmission.objects.filter(task=self.task, user=self.owner).count(), 1,
        )

    def test_best_score_keeps_maximum_across_attempts(self):
        self.make_submission(self.owner)  # task A attempt 1
        attempt2 = self.make_submission(self.owner)  # task A attempt 2
        self.auth(self.owner)
        with ai_patch(return_value=VALID_EVAL):
            self.client.post(make_url(attempt2.pk))
        # Wait: attempt2 is the latest row; evaluate attempt1 too, then a
        # third worse attempt to prove the best is retained.
        attempt1 = TaskSubmission.objects.filter(
            task=self.task, user=self.owner).order_by("id").first()
        with ai_patch(return_value=VALID_EVAL):
            self.client.post(make_url(attempt1.pk))
        attempt3 = self.make_submission(self.owner)
        with ai_patch(return_value=LOWER_EVAL):
            response = self.client.post(make_url(attempt3.pk))
        # Worse attempt (1+1+1+1+1=5) must not reduce the best (8).
        self.assertEqual(response.json()["best_score"], 8)


@override_settings(AI_API_KEY='test')
class ReviewAndLeaderboardTests(EvaluationTestBase):
    def review(self, submission, status_value):
        self.auth(self.admin)
        return self.client.patch(
            f"/api/admin/submissions/{submission.pk}/",
            {"status": status_value, "feedback": "ok"},
            format="json",
        )

    def test_approval_awards_points_once(self):
        sub = self.make_submission(self.owner, status=TaskSubmission.Status.PENDING)
        self.review(sub, "APPROVED")
        sub.refresh_from_db()
        self.assertEqual(sub.earned_points, self.task.points)
        # Re-reviewing must not double-award.
        self.review(sub, "APPROVED")
        sub.refresh_from_db()
        self.assertEqual(sub.earned_points, self.task.points)

    def test_rejection_awards_no_points(self):
        sub = self.make_submission(self.owner, status=TaskSubmission.Status.PENDING)
        self.review(sub, "REJECTED")
        sub.refresh_from_db()
        self.assertEqual(sub.earned_points, 0)

    def test_leaderboard_uses_best_evaluation_score(self):
        # Task A: attempts with evaluations 8 and 8. Task B: evaluation 5.
        task_b = Task.objects.create(title="Second task", description="Other", difficulty="MEDIUM")
        TaskAssignment.objects.create(task=task_b, user=self.owner)
        attempt_a = self.make_submission(self.owner)
        sub_b = self.make_submission(self.owner, task=task_b)
        self.auth(self.owner)
        with ai_patch(return_value=VALID_EVAL):
            self.client.post(make_url(attempt_a.pk))
        eval_b = {**VALID_EVAL, "scores": {"requirement_completion": 1, "correctness": 1, "quality": 1, "completeness": 1, "clarity": 1}}
        with ai_patch(return_value=eval_b):
            self.client.post(make_url(sub_b.pk))
        rows = {row["user_id"]: row for row in leaderboard()}
        mine = rows[self.owner.pk]
        # Best per task: 8 (task A) + 5 (task B) = 13 Ã¢â‚¬â€ never a sum of attempts.
        self.assertEqual(mine["normal_task_points"], 13)
        self.assertEqual(mine["total_points"], mine["coding_points"] + 13)

    def test_leaderboard_ignores_failed_evaluations(self):
        sub = self.make_submission(self.owner)
        TaskEvaluation.objects.create(
            submission=sub, status=TaskEvaluation.Status.FAILED, total_score=0, scores={},
        )
        rows = {row["user_id"]: row for row in leaderboard()}
        self.assertNotIn(self.owner.pk, rows)  # nothing earned anywhere

    def test_leaderboard_total_is_coding_plus_tasks(self):
        for row in leaderboard():
            self.assertEqual(row["total_points"], row["coding_points"] + row["normal_task_points"])
