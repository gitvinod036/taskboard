"""
Add difficulty to Task and earned_points to TaskSubmission.

Existing tasks get the safe EASY default so pre-existing rows remain valid.
Diff is additive only; no existing data is altered.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('taskflow', '0012_submissionanalysis'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='difficulty',
            field=models.CharField(
                choices=[('EASY', 'Easy'), ('MEDIUM', 'Medium'), ('HARD', 'Hard')],
                default='EASY',
                help_text='Primary difficulty level of the task.',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='tasksubmission',
            name='earned_points',
            field=models.PositiveIntegerField(default=0),
        ),
    ]