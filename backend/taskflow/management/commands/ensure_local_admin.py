from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create or repair the local development Admin account.'

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(username='Admin')
        user.email = 'vinodsannapaneni036@gmail.com'
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password('admin@123')
        user.save()
        action = 'created' if created else 'updated'
        self.stdout.write(self.style.SUCCESS(f'Local Admin account {action}: username={user.username}, role=ADMIN'))
