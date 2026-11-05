import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from kyto.core.models import Campaign, Profile

User = get_user_model()

PEOPLE = [
    ("Aarav Shah", "aarav.eats", "food", "Ahmedabad"), ("Mira Patel", "mira.wears", "fashion", "Ahmedabad"),
    ("Kabir Mehta", "kabir.moves", "fitness", "Surat"), ("Anaya Joshi", "anaya.glow", "beauty", "Vadodara"),
    ("Ishaan Rao", "ishaan.codes", "tech", "Bengaluru"), ("Diya Desai", "diya.wanders", "travel", "Ahmedabad"),
    ("Vihaan Gupta", "vihaan.laughs", "comedy", "Mumbai"), ("Saanvi Nair", "saanvi.learns", "education", "Kochi"),
    ("Reyansh Jain", "reyansh.plays", "gaming", "Pune"), ("Tara Bose", "tara.lives", "lifestyle", "Kolkata"),
    ("Neel Trivedi", "neel.bites", "food", "Rajkot"), ("Riya Kapoor", "riya.styles", "fashion", "Delhi"),
]


class Command(BaseCommand):
    help = "Create demo creators and one demo brand (remove before launch)."

    def handle(self, *args, **opts):
        random.seed(7)
        for name, handle, niche, city in PEOPLE:
            if User.objects.filter(username=handle).exists():
                continue
            u = User.objects.create_user(handle, f"{handle}@example.com")
            u.set_unusable_password()
            u.save()
            Profile.objects.create(
                user=u, handle=handle, display_name=name, niche=niche, city=city,
                bio=f"{niche.title()} creator from {city}. Open to collaborations.",
                followers=random.choice([4200, 12800, 31000, 56000, 120000, 340000, 910000]),
                engagement=round(random.uniform(1.2, 7.8), 2), rate_per_post=random.choice([2000, 5000, 12000, 30000]),
                verified=random.random() > 0.6,
            )
        if not User.objects.filter(username="demo.brand").exists():
            b = User.objects.create_user("demo.brand", "brand@example.com")
            b.set_unusable_password()
            b.save()
            Profile.objects.create(user=b, handle="demo.brand", role=Profile.BRAND, display_name="Demo Brand", city="Ahmedabad", address="SG Highway, Ahmedabad")
            Campaign.objects.create(
                brand=b, title="Cafe launch reels", niche="food", city="Ahmedabad", budget=15000,
                deliverables="2 reels + 3 stories", description="We're opening a new cafe on SG Highway and want local food creators to visit and share their experience.",
            )
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
