"""
Leaderboard display and ordering tests.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from taskflow.models import (
    CodingProblem, CodingProblemTestCase, CodeSubmission,
    Task, TaskSubmission, TaskEvaluation,
)
from taskflow.services import leaderboard

User = get_user_model()


class LeaderboardOrderingTests(TestCase):
    """Leaderboard uses best-score-per-problem rule and orders by total_points."""

    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pw")
        self.bob = User.objects.create_user(username="bob", password="pw")
        self.carol = User.objects.create_user(username="carol", password="pw")

        self.problem = CodingProblem.objects.create(
            title="Two Sum", description="d", difficulty="EASY",
            input_format="in", output_format="out", constraints="c",
            starter_code={}, allowed_languages=["python"],
            status=CodingProblem.Status.PUBLISHED,
        )
        CodingProblemTestCase.objects.create(
            problem=self.problem, input="1", expected_output="2",
            is_hidden=False, order=1,
        )

    def solve(self, user, problem):
        return CodeSubmission.objects.create(
            user=user, problem=problem, language="python", source_code="pass",
            status=CodeSubmission.Status.ACCEPTED, mode=CodeSubmission.Mode.SUBMIT,
        )

    def test_leaderboard_orders_by_total_points_desc(self):
        self.solve(self.alice, self.problem)
        self.solve(self.bob, self.problem)
        self.solve(self.bob, self.problem)  # should not double-score
        rows = {r["username"]: r for r in leaderboard()}
        self.assertEqual(rows["alice"]["coding_points"], 10)
        self.assertEqual(rows["bob"]["coding_points"], 10)
        self.assertEqual(rows["alice"]["problems_solved"], 1)
        self.assertEqual(rows["bob"]["problems_solved"], 1)
        # carol has no points yet, so she is not ranked (leaderboard only
        # contains members who have earned points).
        self.assertNotIn("carol", rows)
        # total_points is coding + normal, never inflated.
        for row in leaderboard():
            self.assertEqual(
                row["total_points"],
                row["coding_points"] + row["normal_task_points"],
            )

    def test_better_attempt_does_not_reduce_score(self):
        # Normal-task best-score rule: the leaderboard uses the MAX completed
        # evaluation per (user, task) — a better second attempt raises the
        # score but is never summed with the earlier attempt (no 6 + 8 = 14).
        task = Task.objects.create(title="B", description="d", difficulty="MEDIUM")
        first = TaskSubmission.objects.create(
            task=task, user=self.alice,
            git_url="https://github.com/a/b", linkedin_url="https://linkedin.com/in/a",
            status=TaskSubmission.Status.APPROVED,
        )
        improved = TaskSubmission.objects.create(
            task=task, user=self.alice,
            git_url="https://github.com/a/b", linkedin_url="https://linkedin.com/in/a",
            status=TaskSubmission.Status.APPROVED,
        )
        TaskEvaluation.objects.create(
            submission=first, status=TaskEvaluation.Status.COMPLETED,
            total_score=6, scores={},
        )
        TaskEvaluation.objects.create(
            submission=improved, status=TaskEvaluation.Status.COMPLETED,
            total_score=8, scores={},
        )
        rows = {r["username"]: r for r in leaderboard()}
        self.assertEqual(rows["alice"]["normal_task_points"], 8)
        self.assertNotEqual(rows["alice"]["normal_task_points"], 14)
        self.assertNotEqual(rows["alice"]["normal_task_points"], 6)
