from django.core.management.base import BaseCommand

from core.models import Profile


class Command(BaseCommand):
    help = "Recalculate every rank score (run after changing the formula)."

    def handle(self, *args, **opts):
        n = 0
        for p in Profile.objects.all():
            p.save()
            n += 1
        self.stdout.write(self.style.SUCCESS(f"Recomputed {n} profiles."))
