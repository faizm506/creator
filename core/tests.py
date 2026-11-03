from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import BoostRequest, Profile

User = get_user_model()


def make(handle, role="creator", **kw):
    u = User.objects.create_user(handle, f"{handle}@x.com", "pass-12345-xyz")
    return Profile.objects.create(user=u, handle=handle, role=role, display_name=handle.title(), **kw)


class RankingTests(TestCase):
    def test_more_followers_and_engagement_rank_higher(self):
        a = make("small", followers=1000, engagement=1)
        b = make("big", followers=500000, engagement=5)
        self.assertGreater(b.rank_score, a.rank_score)

    def test_boost_does_not_change_score(self):
        p = make("boosty", followers=5000, engagement=3)
        before = p.rank_score
        p.boost_until = timezone.now() + timedelta(days=7)
        p.save()
        self.assertEqual(before, p.rank_score)
        self.assertTrue(p.is_boosted)


class BoostTests(TestCase):
    def setUp(self):
        self.p = make("payer")
        self.client.login(username="payer", password="pass-12345-xyz")

    def test_rejects_bad_utr(self):
        r = self.client.post(reverse("boost"), {"plan": "7", "utr": "123"})
        self.assertEqual(BoostRequest.objects.count(), 0)
        self.assertEqual(r.status_code, 200)

    def test_accepts_and_blocks_duplicate_utr(self):
        self.client.post(reverse("boost"), {"plan": "7", "utr": "123456789012"})
        self.client.post(reverse("boost"), {"plan": "30", "utr": "123456789012"})
        self.assertEqual(BoostRequest.objects.count(), 1)
        self.assertFalse(Profile.objects.get(pk=self.p.pk).is_boosted)  # not boosted until admin approves

    def test_amount_comes_from_server_not_client(self):
        self.client.post(reverse("boost"), {"plan": "7", "utr": "111111111111", "amount": "1"})
        self.assertEqual(BoostRequest.objects.get().amount, 99)


class AccessTests(TestCase):
    def test_contact_hidden_from_anonymous(self):
        make("shy", whatsapp="919876543210", show_contact=True)
        r = self.client.get(reverse("creator", args=["shy"]))
        self.assertNotContains(r, "919876543210")

    def test_settings_requires_login(self):
        r = self.client.get(reverse("settings"))
        self.assertEqual(r.status_code, 302)


class ShowcaseTests(TestCase):
    def setUp(self):
        self.p = make("reeler", followers=20000, engagement=4)
        self.client.login(username="reeler", password="pass-12345-xyz")

    def test_reel_link_parsed_and_scores_up(self):
        before = Profile.objects.get(pk=self.p.pk).rank_score
        self.client.post(reverse("showcase_add"), {"url": "https://www.instagram.com/reel/AbC123xyz_/?igsh=1"})
        self.assertEqual(self.p.showcase.get().code, "AbC123xyz_")
        self.assertGreater(Profile.objects.get(pk=self.p.pk).rank_score, before)

    def test_rejects_non_instagram_and_other_accounts(self):
        self.client.post(reverse("showcase_add"), {"url": "https://evil.com/reel/AbC123xyz/"})
        self.client.post(reverse("showcase_add"), {"url": "https://instagram.com/someoneelse/reel/AbC123xyz/"})
        self.assertEqual(self.p.showcase.count(), 0)

    def test_score_never_exceeds_100(self):
        p = make("maxed", followers=500_000_000, engagement=50, verified=True, city="A", niche="food", bio="b", rate_per_post=1)
        self.assertLessEqual(p.compute_score(), 100)

    def test_instagram_redirect_is_fixed_and_counts(self):
        r = self.client.get(reverse("go", args=["reeler"]))
        self.assertEqual(r["Location"], "https://www.instagram.com/reeler/")
        self.assertEqual(Profile.objects.get(pk=self.p.pk).ig_clicks, 1)

    def test_profile_page_counts_views_once_per_session(self):
        make("other")
        c = self.client_class()
        c.get(reverse("creator", args=["other"]))
        c.get(reverse("creator", args=["other"]))
        self.assertEqual(Profile.objects.get(handle="other").views, 1)


class FairnessTests(TestCase):
    def _boosted(self, handle, **kw):
        kw.setdefault("bio", "x"); kw.setdefault("niche", "food"); kw.setdefault("followers", 5000)
        p = make(handle, **kw)
        p.boost_until = timezone.now() + timedelta(days=30)
        p.save()
        return p

    def test_tie_break_followers_then_join_order(self):
        a = make("tie_a", followers=0)
        b = make("tie_b", followers=0)
        order = [p.handle for p in Profile.objects.filter(handle__in=["tie_a", "tie_b"])]
        self.assertEqual(order, ["tie_a", "tie_b"])

    def test_shelf_rotates_least_shown_first(self):
        from django.test import RequestFactory
        from .views import featured_shelf
        ps = [self._boosted(f"fx{i}") for i in range(5)]
        seen = set()
        for i in range(5):
            req = RequestFactory().get("/", REMOTE_ADDR=f"10.0.0.{i}")
            seen.update(p.handle for p in featured_shelf(req, 2))
        self.assertEqual(len(seen), 5)  # everyone got shown, none starved

    def test_full_niche_blocks_new_boost(self):
        from django.test import override_settings
        with override_settings(FEATURED_SLOTS_PER_NICHE=2):
            self._boosted("s1"); self._boosted("s2")
            late = make("late", niche="food")
            self.client.login(username="late", password="pass-12345-xyz")
            self.client.post(reverse("boost"), {"plan": "7", "utr": "999999999999"})
            self.assertEqual(BoostRequest.objects.filter(user=late.user).count(), 0)

    def test_empty_profiles_never_featured(self):
        from django.test import RequestFactory
        from .views import featured_shelf
        p = make("blank", niche="food")  # no bio, no followers
        p.boost_until = timezone.now() + timedelta(days=30)
        p.save()
        self.assertEqual(featured_shelf(RequestFactory().get("/"), 4), [])
