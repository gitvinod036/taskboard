from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_tech_stacks(apps, schema_editor):
	TechStack = apps.get_model('taskflow', 'TechStack')
	from taskflow.tech_stacks import TECH_STACK_NAMES
	TechStack.objects.bulk_create([TechStack(name=name) for name in TECH_STACK_NAMES], ignore_conflicts=True)


class Migration(migrations.Migration):
	dependencies = [
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
		('taskflow', '0002_taskassignment'),
	]

	operations = [
		migrations.CreateModel(
			name='TechStack',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('name', models.CharField(max_length=100, unique=True)),
			],
			options={'ordering': ('name',)},
		),
		migrations.CreateModel(
			name='UserTechStack',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('tech_stack', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_tech_stacks', to='taskflow.techstack')),
				('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_tech_stacks', to=settings.AUTH_USER_MODEL)),
			],
			options={
				'indexes': [models.Index(fields=['user'], name='taskflow_uts_user_id_idx'), models.Index(fields=['tech_stack'], name='taskflow_uts_tech_id_idx')],
				'constraints': [models.UniqueConstraint(fields=('user', 'tech_stack'), name='unique_user_tech_stack')],
			},
		),
		migrations.RunPython(seed_tech_stacks, migrations.RunPython.noop),
	]