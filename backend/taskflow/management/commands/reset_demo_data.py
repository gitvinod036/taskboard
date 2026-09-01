"""Remove ONLY records created by `seed_demo_data`.

Scoped strictly to:
  - users whose username starts with `demo_`
  - tasks whose titles exactly match the deterministic demo-task titles

This NEVER flushes the database and NEVER touches real application data.
Deletion is ordered child-first to respect FK constraints.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

# Exact titles created by `seed_demo_data`. Real tasks never use these titles,
# so matching by this exact set is safe and removes ALL demo tasks.
DEMO_TASK_TITLES = [
    "Write a professional email to a client about a delayed deadline",
    "Explain the difference between GET and POST in HTTP",
    "Create a deployment checklist for a small web app",
    "Design a small REST API for a todo list",
    "Debug a simple Python function that has an off-by-one error",
    "Write unit test cases for a password validator",
    "Explain database normalization (1NF, 2NF, 3NF)",
    "Design a login/logout flow for a web application",
    "Create a small data-processing script that reads a CSV",
    "Design a database schema for a blog platform",
    "Write documentation for a small Python utility module",
    "Analyze the time complexity of a nested-loop algorithm",
    "Design an API rate-limiting strategy for a public API",
    "Build a small caching layer for a read-heavy service",
    "Review and improve a code snippet for maintainability",
]


def _demo_user_queryset():
    User = get_user_model()
    return User.objects.filter(username__startswith="demo_")


class Command(BaseCommand):
    help = "Remove only the demo dataset created by seed_demo_data. Safe, scoped to demo namespace."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report counts without deleting.")

    def handle(self, *args, **options):
        from django.db import transaction
        from taskflow.models import (
            CodeSubmission,
            NotificationPreference,
            SubmissionAnalysis,
            Task,
            TaskAssignment,
            TaskSubmission,
        )
        dry = options["dry_run"]

        users = _demo_user_queryset()
        uids = list(users.values_list("pk", flat=True))

        analysis_qs = SubmissionAnalysis.objects.filter(submission__user_id__in=uids)
        code_qs = CodeSubmission.objects.filter(user_id__in=uids)
        sub_qs = TaskSubmission.objects.filter(user_id__in=uids)
        assign_qs = TaskAssignment.objects.filter(user_id__in=uids)
        task_qs = Task.objects.filter(title__in=DEMO_TASK_TITLES)
        pref_qs = NotificationPreference.objects.filter(user_id__in=uids)

        if dry:
            self.stdout.write(self.style.WARNING("DRY RUN - would remove:"))
            self.stdout.write("  SubmissionAnalysis: %d" % analysis_qs.count())
            self.stdout.write("  CodeSubmission:     %d" % code_qs.count())
            self.stdout.write("  TaskSubmission:     %d" % sub_qs.count())
            self.stdout.write("  TaskAssignment:     %d" % assign_qs.count())
            self.stdout.write("  Task:               %d" % task_qs.count())
            self.stdout.write("  NotificationPref:   %d" % pref_qs.count())
            self.stdout.write("  User:               %d" % users.count())
            return

        with transaction.atomic():
            # Child-first deletion to honour FK constraints.
            analysis_count = analysis_qs.delete()[0]
            code_count = code_qs.delete()[0]
            sub_count = sub_qs.delete()[0]
            assign_count = assign_qs.delete()[0]
            task_count = task_qs.delete()[0]
            pref_count = pref_qs.delete()[0]
            user_count = users.delete()[0]

        self.stdout.write(self.style.WARNING("Resetting demo data..."))
        self.stdout.write("Removed SubmissionAnalysis: %d" % analysis_count)
        self.stdout.write("Removed CodeSubmission:     %d" % code_count)
        self.stdout.write("Removed TaskSubmission:     %d" % sub_count)
        self.stdout.write("Removed TaskAssignment:     %d" % assign_count)
        self.stdout.write("Removed Task:               %d" % task_count)
        self.stdout.write("Removed NotificationPref:   %d" % pref_count)
        self.stdout.write("Removed demo users:         %d" % user_count)
        self.stdout.write(self.style.SUCCESS("Real application data untouched."))
        self.stdout.write(self.style.SUCCESS("Demo reset complete."))
