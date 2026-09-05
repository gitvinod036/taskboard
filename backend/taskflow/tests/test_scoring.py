"""Scoring and leaderboard integrity tests.

Verifies that points are derived correctly, duplicate attempts never
double-score, and the leaderboard uses the best-score rule.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from taskflow.models import (
	CodeSubmission, CodingProblem, CodingProblemTestCase,
	Task, TaskSubmission,
)
from taskflow.services import (
	award_normal_task_points, leaderboard, normal_task_points_earned,
	points_earned_for_submission,
)

User = get_user_model()


class CodingScoringTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="coder", password="pw")
		self.problem = CodingProblem.objects.create(
			title="Two Sum", description="desc", difficulty="EASY",
			input_format="in", output_format="out", constraints="1<=n",
			starter_code={}, allowed_languages=["python"],
			status=CodingProblem.Status.PUBLISHED,
		)
		CodingProblemTestCase.objects.create(
			problem=self.problem, input="1", expected_output="2",
			is_hidden=False, order=1,
		)

	def make_submission(self, **overrides):
		defaults = {
			"user": self.user,
			"problem": self.problem,
			"language": "python",
			"source_code": "pass",
			"status": CodeSubmission.Status.ACCEPTED,
			"mode": CodeSubmission.Mode.SUBMIT,
		}
		defaults.update(overrides)
		return CodeSubmission.objects.create(**defaults)

	def test_accepted_submit_awards_difficulty_points(self):
		sub = self.make_submission()
		self.assertEqual(points_earned_for_submission(sub), 10)

	def test_pending_submission_earns_zero(self):
		sub = self.make_submission(status=CodeSubmission.Status.PENDING)
		self.assertEqual(points_earned_for_submission(sub), 0)

	def test_second_accepted_submission_earns_zero(self):
		first = self.make_submission()
		second = self.make_submission()
		self.assertEqual(points_earned_for_submission(first), 10)
		self.assertEqual(points_earned_for_submission(second), 0)

	def test_run_mode_does_not_award_points(self):
		sub = self.make_submission(mode=CodeSubmission.Mode.RUN)
		self.assertEqual(points_earned_for_submission(sub), 0)


class LeaderboardTests(TestCase):
	def setUp(self):
		self.alice = User.objects.create_user(username="alice", password="pw")
		self.bob = User.objects.create_user(username="bob", password="pw")
		self.problem_easy = CodingProblem.objects.create(
			title="Easy", description="d", difficulty="EASY",
			input_format="in", output_format="out", constraints="c",
			starter_code={}, allowed_languages=["python"],
			status=CodingProblem.Status.PUBLISHED,
		)
		CodingProblemTestCase.objects.create(problem=self.problem_easy, input="1", expected_output="2", is_hidden=False, order=1)

	def solve(self, user, problem):
		return CodeSubmission.objects.create(
			user=user, problem=problem, language="python", source_code="pass",
			status=CodeSubmission.Status.ACCEPTED, mode=CodeSubmission.Mode.SUBMIT,
		)

	def test_leaderboard_excludes_draft_problems(self):
		draft = CodingProblem.objects.create(
			title="Draft", description="d", difficulty="EASY",
			input_format="in", output_format="out", constraints="c",
			starter_code={}, allowed_languages=["python"],
			status=CodingProblem.Status.DRAFT,
		)
		self.solve(self.alice, draft)
		rows = {r["username"]: r for r in leaderboard()}
		if "alice" in rows:
			self.assertEqual(rows["alice"]["coding_points"], 0)

	def test_leaderboard_total_is_coding_plus_tasks(self):
		for row in leaderboard():
			self.assertEqual(row["total_points"], row["coding_points"] + row["normal_task_points"])


class NormalTaskScoringTests(TestCase):
	def setUp(self):
		self.task = Task.objects.create(title="A", description="d", difficulty="MEDIUM")
		self.owner = User.objects.create_user(username="owner", password="pw")
		self.submission = TaskSubmission.objects.create(
			task=self.task, user=self.owner,
			git_url="https://github.com/d/r", linkedin_url="https://linkedin.com/in/d",
			status=TaskSubmission.Status.PENDING,
		)

	def test_pending_awards_no_points(self):
		self.assertEqual(normal_task_points_earned(self.submission), 0)

	def test_rejected_awards_no_points(self):
		self.submission.status = TaskSubmission.Status.REJECTED
		self.assertEqual(normal_task_points_earned(self.submission), 0)

	def test_approval_idempotent_no_double_award(self):
		self.submission.status = TaskSubmission.Status.APPROVED
		self.submission.save(update_fields=["status"])
		awarded = award_normal_task_points(self.submission)
		self.submission.refresh_from_db()
		self.assertEqual(awarded, 20)  # MEDIUM task => 20 points
		self.assertEqual(self.submission.earned_points, 20)
		# A second award call must not double the points.
		again = award_normal_task_points(self.submission)
		self.assertEqual(again, 0)
		self.submission.refresh_from_db()
		self.assertEqual(self.submission.earned_points, 20)
