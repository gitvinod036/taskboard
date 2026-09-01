"""Seed a deterministic, idempotent demo dataset for local development.

Creates 1 demo admin + 10 demo users, 15 normal tasks (5 EASY, 5 MEDIUM,
5 HARD), task assignments, normal-task submissions (PENDING/APPROVED/REJECTED)
with server-set earned_points AND completed TaskEvaluation rows on APPROVED
submissions, plus a small amount of coding data.

Scoring rules honored exactly:
  - Task.points derived from DIFFICULTY_POINTS (never stored on Task).
  - TaskSubmission.earned_points server-set on APPROVE (idempotent).
  - APPROVED submissions get a COMPLETED TaskEvaluation with the 10-point rubric.
    (best-score rule = MAX eval per user/task at read; we create exactly one
    eval per approved submission and never insert duplicates.)

No Gemini/API calls, no judge execution, no backend logic changes.
Run twice -> identical counts, no duplicates, no unique-constraint violations.
"""
import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from taskflow.models import (
    CodeSubmission,
    CodingProblem,
    Task,
    TaskAssignment,
    TaskEvaluation,
    TaskSubmission,
)

DEMO_PASSWORD = "demo@taskboard"

DEMO_USERS = [
    ("demo_user_01", "Aarav Sharma", "demo01@taskboard.local"),
    ("demo_user_02", "Priya Reddy", "demo02@taskboard.local"),
    ("demo_user_03", "Rahul Kumar", "demo03@taskboard.local"),
    ("demo_user_04", "Ananya Singh", "demo04@taskboard.local"),
    ("demo_user_05", "Vikram Patel", "demo05@taskboard.local"),
    ("demo_user_06", "Sneha Rao", "demo06@taskboard.local"),
    ("demo_user_07", "Arjun Mehta", "demo07@taskboard.local"),
    ("demo_user_08", "Neha Verma", "demo08@taskboard.local"),
    ("demo_user_09", "Kiran Das", "demo09@taskboard.local"),
    ("demo_user_10", "Rohan Nair", "demo10@taskboard.local"),
]
ADMIN_USER = ("demo_admin", "Demo Admin", "demo_admin@taskboard.local")

DEMO_TASKS = [
    ("Write a professional email to a client about a delayed deadline", "EASY"),
    ("Explain the difference between GET and POST in HTTP", "EASY"),
    ("Create a deployment checklist for a small web app", "EASY"),
    ("Design a small REST API for a todo list", "EASY"),
    ("Debug a simple Python function that has an off-by-one error", "EASY"),
    ("Write unit test cases for a password validator", "MEDIUM"),
    ("Explain database normalization (1NF, 2NF, 3NF)", "MEDIUM"),
    ("Design a login/logout flow for a web application", "MEDIUM"),
    ("Create a small data-processing script that reads a CSV", "MEDIUM"),
    ("Design a database schema for a blog platform", "HARD"),
    ("Write documentation for a small Python utility module", "HARD"),
    ("Analyze the time complexity of a nested-loop algorithm", "HARD"),
    ("Design an API rate-limiting strategy for a public API", "HARD"),
    ("Build a small caching layer for a read-heavy service", "HARD"),
    ("Review and improve a code snippet for maintainability", "MEDIUM"),
]

# (username, task_title, status, earned_points, eval_total)
# Exactly one entry per (username, task_title) — no duplicate pairs.
# earned_points is only nonzero for APPROVED (mirrors server-side award logic).
SUBMISSION_PLAN = [
    ("demo_user_01", "Write a professional email to a client about a delayed deadline", TaskSubmission.Status.APPROVED, 10, 8),
    ("demo_user_01", "Design a small REST API for a todo list", TaskSubmission.Status.APPROVED, 20, 9),
    ("demo_user_01", "Design a database schema for a blog platform", TaskSubmission.Status.APPROVED, 30, 10),
    ("demo_user_01", "Explain the difference between GET and POST in HTTP", TaskSubmission.Status.REJECTED, 0, 0),
    ("demo_user_02", "Create a deployment checklist for a small web app", TaskSubmission.Status.APPROVED, 10, 7),
    ("demo_user_02", "Write unit test cases for a password validator", TaskSubmission.Status.APPROVED, 20, 6),
    ("demo_user_03", "Design a login/logout flow for a web application", TaskSubmission.Status.APPROVED, 20, 8),
    ("demo_user_03", "Debug a simple Python function that has an off-by-one error", TaskSubmission.Status.REJECTED, 0, 0),
    ("demo_user_03", "Explain database normalization (1NF, 2NF, 3NF)", TaskSubmission.Status.APPROVED, 20, 9),
    ("demo_user_04", "Create a small data-processing script that reads a CSV", TaskSubmission.Status.APPROVED, 20, 5),
    ("demo_user_04", "Analyze the time complexity of a nested-loop algorithm", TaskSubmission.Status.PENDING, 0, 0),
    ("demo_user_05", "Design an API rate-limiting strategy for a public API", TaskSubmission.Status.APPROVED, 30, 10),
    ("demo_user_05", "Build a small caching layer for a read-heavy service", TaskSubmission.Status.APPROVED, 30, 8),
    ("demo_user_06", "Write documentation for a small Python utility module", TaskSubmission.Status.APPROVED, 30, 7),
    ("demo_user_07", "Review and improve a code snippet for maintainability", TaskSubmission.Status.APPROVED, 20, 6),
    ("demo_user_07", "Design a database schema for a blog platform", TaskSubmission.Status.APPROVED, 30, 9),
    ("demo_user_08", "Explain database normalization (1NF, 2NF, 3NF)", TaskSubmission.Status.REJECTED, 0, 0),
    ("demo_user_09", "Create a small data-processing script that reads a CSV", TaskSubmission.Status.APPROVED, 20, 4),
    ("demo_user_10", "Debug a simple Python function that has an off-by-one error", TaskSubmission.Status.PENDING, 0, 0),
]

_SUMMARIES = [
    "Solid solution that meets the core requirements",
    "Good approach with minor quality improvements possible",
    "Strong submission with minor gaps",
    "Incomplete or flawed attempt",
    "Excellent work demonstrating clear understanding",
]

# Users who attempted coding problems.
CODING_PLAN = ["demo_user_01", "demo_user_03", "demo_user_05", "demo_user_07"]


def _scores_for_total(total):
    limits = {"requirement_completion": 3, "correctness": 2, "quality": 2,
              "completeness": 2, "clarity": 1}
    scores = {}
    remaining = total
    for cat, mx in limits.items():
        scores[cat] = min(mx, remaining)
        remaining -= scores[cat]
    return scores


def _upsert_user(username, full_name, email, is_superuser=False, is_staff=False):
    User = get_user_model()
    first, _, last = full_name.partition(" ")
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "first_name": first, "last_name": last,
                  "is_active": True, "is_staff": is_staff, "is_superuser": is_superuser})
    if not created:
        user.email = email
        user.first_name = first
        user.last_name = last
        user.is_active = True
        user.is_staff = is_staff or user.is_staff
        user.is_superuser = is_superuser or user.is_superuser
        user.save(update_fields=["email", "first_name", "last_name", "is_active",
                                 "is_staff", "is_superuser"])
    if not user.has_usable_password():
        user.set_password(DEMO_PASSWORD)
        user.save(update_fields=["password"])
    return user


class Command(BaseCommand):
    help = "Seed deterministic demo data for local TaskBoard development."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report counts without writing.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        users = {}

        if dry:
            users["demo_admin"] = None
            for row in DEMO_USERS:
                users[row[0]] = None
            self.stdout.write("DRY RUN: would ensure users and tasks.")
        else:
            users["demo_admin"] = _upsert_user(*ADMIN_USER, is_superuser=True, is_staff=True)
            for row in DEMO_USERS:
                users[row[0]] = _upsert_user(row[0], row[1], row[2])
            self.stdout.write(self.style.SUCCESS(
                "Users ready: %d (1 admin + %d demo users)" % (len(users), len(DEMO_USERS))))

            with transaction.atomic():
                tasks = {}
                for title, difficulty in DEMO_TASKS:
                    t, _ = Task.objects.get_or_create(
                        title=title,
                        defaults={"description": "Demo task: %s" % title, "difficulty": difficulty})
                    tasks[t.title] = t
            self.stdout.write(self.style.SUCCESS("Tasks ready: %d" % len(tasks)))
        tasks = {}
        if not dry:
            with transaction.atomic():
                for title, difficulty in DEMO_TASKS:
                    t, _ = Task.objects.get_or_create(
                        title=title,
                        defaults={"description": "Demo task: %s" % title, "difficulty": difficulty})
                    tasks[t.title] = t

        coding_count = 0
        coding_problem = None
        if not dry:
            coding_problem = CodingProblem.objects.filter(
                status=CodingProblem.Status.PUBLISHED).order_by("difficulty", "-created_at").first()
            if coding_problem is None:
                coding_problem = CodingProblem.objects.filter(status=CodingProblem.Status.DRAFT).first()
            if coding_problem is not None:
                now = datetime.datetime.now(datetime.timezone.utc)
                for uname in CODING_PLAN:
                    u = users.get(uname)
                    if u is None:
                        continue
                    existing = CodeSubmission.objects.filter(
                        user=u, problem=coding_problem, language="python").order_by("-created_at").first()
                    if existing is None:
                        CodeSubmission.objects.create(
                            user=u, problem=coding_problem, language="python",
                            source_code="# demo solution\n",
                            status=CodeSubmission.Status.ACCEPTED,
                            mode=CodeSubmission.Mode.SUBMIT,
                            verdict=CodeSubmission.Status.ACCEPTED,
                            completed_at=now)
                        coding_count += 1
                    else:
                        existing.status = CodeSubmission.Status.ACCEPTED
                        existing.mode = CodeSubmission.Mode.SUBMIT
                        existing.verdict = CodeSubmission.Status.ACCEPTED
                        existing.completed_at = now
                        existing.save(update_fields=["status", "mode", "verdict", "completed_at"])
            self.stdout.write(self.style.SUCCESS("Coding submissions ready: %d" % coding_count))

        sub_count = 0
        eval_count = 0
        if dry:
            self.stdout.write("DRY RUN: would ensure submissions + evaluations.")
        else:
            with transaction.atomic():
                for uname, ttitle, status, earned, etotal in SUBMISSION_PLAN:
                    u = users.get(uname)
                    task = tasks.get(ttitle)
                    if u is None or task is None:
                        continue
                    TaskAssignment.objects.get_or_create(task=task, user=u)
                    # unique_together is (task, user) — lookup on those only.
                    sub, created = TaskSubmission.objects.get_or_create(
                        task=task, user=u,
                        defaults={
                            "git_url": "https://github.com/demo/demo-repo",
                            "linkedin_url": "https://linkedin.com/in/demo",
                            "note": "Demo submission (%s)" % status,
                            "status": status,
                            "earned_points": earned if status == TaskSubmission.Status.APPROVED else 0,
                        })
                    if not created:
                        sub.status = status
                        sub.note = "Demo submission (%s)" % status
                        if status == TaskSubmission.Status.APPROVED and sub.earned_points < earned:
                            sub.earned_points = earned
                        sub.save(update_fields=["status", "note", "earned_points"])
                    sub_count += 1

                    if status == TaskSubmission.Status.APPROVED and etotal > 0:
                        scores = _scores_for_total(etotal)
                        TaskEvaluation.objects.update_or_create(
                            submission=sub,
                            defaults={
                                "status": TaskEvaluation.Status.COMPLETED,
                                "scores": scores,
                                "total_score": sum(scores.values()),
                                "summary": _SUMMARIES[etotal % len(_SUMMARIES)],
                                "strengths": ["Clear structure"],
                                "issues": [] if etotal >= 7 else ["Minor improvements needed"],
                                "suggestions": ["Add tests"],
                            })
                        eval_count += 1
            self.stdout.write(self.style.SUCCESS("Task submissions ready: %d" % sub_count))
            self.stdout.write(self.style.SUCCESS("Task evaluations ready: %d" % eval_count))

        if dry:
            self.stdout.write(self.style.WARNING("DRY RUN: would print leaderboard preview."))
        else:
            from taskflow.services import leaderboard
            self.stdout.write(self.style.SUCCESS("---- Leaderboard preview ----"))
            owned = set(u.username for u in users.values() if u)
            for entry in leaderboard()[:10]:
                star = "  <- YOU" if entry["username"] in owned else ""
                self.stdout.write(
                    "%2d  %-20s  coding=%-4d  tasks=%-4d  total=%-4d%s" % (
                        entry["rank"], entry["username"],
                        entry["coding_points"], entry["normal_task_points"],
                        entry["total_points"], star))

        self.stdout.write(self.style.SUCCESS("Demo data seeding complete."))
