from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import BoostRequest, Offer, Profile, Review, ShopPhoto

User = get_user_model()


def make(handle, role="creator", **kw):
    u = User.objects.create_user(handle, f"{handle}@x.com", "pass-12345-xyz")
    return Profile.objects.create(user=u, handle=handle, role=role, display_name=handle.title(), **kw)


class RankingTests(TestCase):
    def test_more_followers_and_engagement_rank_higher(self):
        a = make("small", followers=1000, engagement=1)
        b = make("big", followers=500000, engagement=5)
        self.assertGreater(b.rank_score, a.rank_score)

    @override_settings(BOOST_ENABLED=True)
    def test_boost_does_not_change_score(self):
        p = make("boosty", followers=5000, engagement=3)
        before = p.rank_score
        p.boost_until = timezone.now() + timedelta(days=7)
        p.save()
        self.assertEqual(before, p.rank_score)
        self.assertTrue(p.is_boosted)


@override_settings(BOOST_ENABLED=True)
class BoostTests(TestCase):
    def setUp(self):
        self.p = make("payer", niche="food")
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


@override_settings(BOOST_ENABLED=True)
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


class HiringTests(TestCase):
    def setUp(self):
        cache.clear()
        self.brand = make("acme", role="brand")
        self.cr = make("star", followers=9000, engagement=3, whatsapp="919800000001")
        self.other = make("nosy")
        self.data = {"title": "Reel", "deliverables": "1 reel", "budget": "5000", "message": "Hi"}

    def _send(self):
        self.client.login(username="acme", password="pass-12345-xyz")
        self.client.post(reverse("offer_new", args=["star"]), self.data)
        return Offer.objects.get()

    def test_brand_can_send_creator_cannot(self):
        self._send()
        self.client.login(username="nosy", password="pass-12345-xyz")
        self.client.post(reverse("offer_new", args=["star"]), self.data)
        self.assertEqual(Offer.objects.count(), 1)

    def test_only_participants_can_open_offer(self):
        o = self._send()
        self.client.login(username="nosy", password="pass-12345-xyz")
        self.assertEqual(self.client.get(reverse("offer", args=[o.pk])).status_code, 404)

    def test_accept_reveals_whatsapp_and_only_creator_can_accept(self):
        o = self._send()
        self.client.post(reverse("offer_action", args=[o.pk, "accept"]))  # brand tries
        self.assertEqual(Offer.objects.get().status, "pending")
        self.client.login(username="star", password="pass-12345-xyz")
        self.client.post(reverse("offer_action", args=[o.pk, "accept"]))
        self.assertEqual(Offer.objects.get().status, "accepted")
        self.client.login(username="acme", password="pass-12345-xyz")
        self.assertContains(self.client.get(reverse("creator", args=["star"])), "919800000001")

    def test_no_messages_after_decline(self):
        o = self._send()
        self.client.login(username="star", password="pass-12345-xyz")
        self.client.post(reverse("offer_action", args=[o.pk, "decline"]))
        self.client.post(reverse("message_send", args=[o.pk]), {"body": "hello"})
        self.assertEqual(o.messages.count(), 0)


class SecurityTests(TestCase):
    def test_delete_requires_correct_password(self):
        p = make("goner")
        self.client.login(username="goner", password="pass-12345-xyz")
        self.client.post(reverse("delete_account"), {"password": "wrong"})
        self.assertTrue(User.objects.filter(username="goner").exists())
        self.client.post(reverse("delete_account"), {"password": "pass-12345-xyz"})
        self.assertFalse(User.objects.filter(username="goner").exists())


class LaunchModeTests(TestCase):
    """Boost is off while the platform is free."""

    def test_boost_page_is_404_and_nothing_is_featured(self):
        make("freebie")
        self.client.login(username="freebie", password="pass-12345-xyz")
        self.assertEqual(self.client.get(reverse("boost")).status_code, 404)

    def test_old_boost_never_shows_when_disabled(self):
        p = make("oldboost", bio="x", niche="food", followers=100)
        p.boost_until = timezone.now() + timedelta(days=30)
        p.save()
        self.assertFalse(Profile.objects.get(pk=p.pk).is_boosted)


class HardeningTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_security_headers_present(self):
        r = self.client.get(reverse("home"))
        self.assertIn("default-src 'self'", r["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertIn("Permissions-Policy", r)

    def test_login_locks_after_repeated_failures(self):
        make("locky")
        for _ in range(8):
            self.client.post(reverse("login"), {"username": "locky", "password": "wrong-wrong-1"})
        r = self.client.post(reverse("login"), {"username": "locky", "password": "pass-12345-xyz"})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_page_has_both_role_cards_and_creates_profile(self):
        r = self.client.get(reverse("signup"))
        self.assertContains(r, "Creator")
        self.assertContains(r, "Brand")
        self.client.post(reverse("signup"), {
            "role": "brand", "display_name": "Chai Corner", "username": "chaicorner", "email": "c@x.com",
            "password1": "S0me-long-pass-99", "password2": "S0me-long-pass-99"})
        self.assertEqual(Profile.objects.get(handle="chaicorner").role, "brand")

    def test_password_reset_does_not_reveal_accounts(self):
        make("known")
        a = self.client.post(reverse("password_reset"), {"email": "known@x.com"})
        b = self.client.post(reverse("password_reset"), {"email": "nobody@x.com"})
        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(a["Location"], b["Location"])

    def test_robots_and_humans(self):
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /inbox/")
        self.assertContains(self.client.get("/humans.txt"), "Zyrac")

    def test_footer_credit_links_to_zyrac_instagram(self):
        r = self.client.get(reverse("home"))
        self.assertContains(r, 'href="https://www.instagram.com/zyrac__/"')
        self.assertContains(r, 'rel="noopener noreferrer"')


class PagesAndCampaignTests(TestCase):
    def setUp(self):
        cache.clear()
        from .models import Campaign
        self.brand = make("brandy", role="brand")
        self.cr = make("makerx", followers=5000, engagement=3)
        self.c = Campaign.objects.create(brand=self.brand.user, title="Cafe reels", description="Visit us",
                                         niche="food", city="Ahmedabad", budget=9000, deliverables="2 reels + 3 stories")

    def test_about_page_credits_zyrac(self):
        r = self.client.get(reverse("about"))
        self.assertContains(r, "zyrac__")
        self.assertContains(r, "Zyrac")

    def test_campaign_list_and_detail_render(self):
        self.assertContains(self.client.get(reverse("campaigns")), "Cafe reels")
        self.assertContains(self.client.get(reverse("campaign", args=[self.c.pk])), "2 reels")

    def test_apply_flow_and_owner_sees_proposal(self):
        self.client.login(username="makerx", password="pass-12345-xyz")
        self.client.post(reverse("campaign_apply", args=[self.c.pk]), {"budget": "8000", "message": "I love cafes"})
        self.assertEqual(Offer.objects.filter(campaign=self.c, initiator="creator").count(), 1)
        self.client.login(username="brandy", password="pass-12345-xyz")
        page = self.client.get(reverse("campaign", args=[self.c.pk]))
        self.assertContains(page, "I love cafes")
        self.assertContains(page, "Accept")
        self.client.login(username="makerx", password="pass-12345-xyz")
        self.assertNotContains(self.client.get(reverse("campaign", args=[self.c.pk])), "Close campaign")

    def test_inbox_and_chat_pages_render(self):
        self.client.login(username="brandy", password="pass-12345-xyz")
        self.client.post(reverse("offer_new", args=["makerx"]),
                         {"title": "Reel", "deliverables": "1 reel", "budget": "5000", "message": "Hello there"})
        o = Offer.objects.get()
        self.assertContains(self.client.get(reverse("inbox")), "Hello there")
        self.assertContains(self.client.get(reverse("offer", args=[o.pk])), "Hello there")


class ProposalFlowTests(TestCase):
    """Brand posts a campaign, the creator sends a price, the brand accepts."""

    def setUp(self):
        cache.clear()
        from .models import Campaign
        self.brand = make("shopco", role="brand", whatsapp="919811111111")
        self.cr = make("maker", followers=8000, engagement=4, whatsapp="919822222222")
        self.c = Campaign.objects.create(brand=self.brand.user, title="Diwali sale", description="Promote us",
                                         niche="fashion", city="Ahmedabad", budget=10000, deliverables="1 reel")

    def _propose(self):
        self.client.login(username="maker", password="pass-12345-xyz")
        self.client.post(reverse("campaign_apply", args=[self.c.pk]), {"budget": "7500", "message": "Count me in"})
        return Offer.objects.get()

    def test_proposal_is_creator_initiated_with_their_price(self):
        o = self._propose()
        self.assertEqual((o.initiator, o.budget, o.status), ("creator", 7500, "pending"))

    def test_creator_cannot_accept_own_proposal_but_brand_can(self):
        o = self._propose()
        self.client.post(reverse("offer_action", args=[o.pk, "accept"]))
        self.assertEqual(Offer.objects.get().status, "pending")
        self.client.login(username="shopco", password="pass-12345-xyz")
        self.client.post(reverse("offer_action", args=[o.pk, "accept"]))
        self.assertEqual(Offer.objects.get().status, "accepted")
        self.assertContains(self.client.get(reverse("offer", args=[o.pk])), "919822222222")

    def test_brand_sees_accept_buttons_and_creator_does_not(self):
        o = self._propose()
        self.assertNotContains(self.client.get(reverse("offer", args=[o.pk])), "Accept this proposal?")
        self.client.login(username="shopco", password="pass-12345-xyz")
        self.assertContains(self.client.get(reverse("offer", args=[o.pk])), "Accept this proposal?")

    def test_no_double_proposal(self):
        self._propose()
        self.client.post(reverse("campaign_apply", args=[self.c.pk]), {"budget": "6000", "message": "Again"})
        self.assertEqual(Offer.objects.count(), 1)

    def test_creator_can_pitch_a_brand_directly(self):
        self.client.login(username="maker", password="pass-12345-xyz")
        self.client.post(reverse("offer_new", args=["shopco"]),
                         {"title": "Collab idea", "deliverables": "2 reels", "budget": "9000", "message": "Hi!"})
        o = Offer.objects.get()
        self.assertEqual((o.initiator, o.brand_id, o.creator_id), ("creator", self.brand.user_id, self.cr.user_id))

    def test_brand_cannot_hire_another_brand(self):
        make("otherbrand", role="brand")
        self.client.login(username="shopco", password="pass-12345-xyz")
        self.client.post(reverse("offer_new", args=["otherbrand"]),
                         {"title": "x", "deliverables": "y", "budget": "5000", "message": "z"})
        self.assertEqual(Offer.objects.count(), 0)


class ReviewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.brand = make("revbrand", role="brand")
        self.cr = make("revmaker", followers=9000, engagement=3)
        self.o = Offer.objects.create(brand=self.brand.user, creator=self.cr.user, title="T", deliverables="d",
                                      budget=5000, message="m", status="accepted")

    def _login(self, name):
        self.client.login(username=name, password="pass-12345-xyz")

    def test_cannot_review_before_finished(self):
        self._login("revbrand")
        self.client.post(reverse("review_add", args=[self.o.pk]), {"rating": "5"})
        self.assertEqual(Review.objects.count(), 0)

    def test_finishing_counts_deals_for_both_and_unlocks_reviews(self):
        self._login("revmaker")
        self.client.post(reverse("offer_action", args=[self.o.pk, "complete"]))
        self.assertEqual(Offer.objects.get().status, "completed")
        self.assertEqual(Profile.objects.get(handle="revmaker").deals_done, 1)
        self.assertEqual(Profile.objects.get(handle="revbrand").deals_done, 1)
        self.assertContains(self.client.get(reverse("offer", args=[self.o.pk])), "How was it working with")

    def _finish(self):
        Offer.objects.filter(pk=self.o.pk).update(status="completed")

    def test_good_review_raises_and_bad_review_lowers_rank_score(self):
        self._finish()
        base = Profile.objects.get(handle="revmaker").rank_score
        self._login("revbrand")
        self.client.post(reverse("review_add", args=[self.o.pk]), {"rating": "5", "comment": "Great work"})
        up = Profile.objects.get(handle="revmaker")
        self.assertGreater(up.rank_score, base)
        self.assertEqual((up.rating_count, up.rating_avg), (1, 5))
        self.client.post(reverse("review_add", args=[self.o.pk]), {"rating": "1", "comment": "Late"})
        down = Profile.objects.get(handle="revmaker")
        self.assertLess(down.rank_score, base)
        self.assertEqual(Review.objects.count(), 1)  # a newer review replaces the old one

    def test_creator_can_review_brand_and_brand_rank_moves(self):
        self._finish()
        base = Profile.objects.get(handle="revbrand").rank_score
        self._login("revmaker")
        self.client.post(reverse("review_add", args=[self.o.pk]), {"rating": "5"})
        self.assertGreater(Profile.objects.get(handle="revbrand").rank_score, base)

    def test_outsider_cannot_review(self):
        self._finish()
        make("rando")
        self._login("rando")
        r = self.client.post(reverse("review_add", args=[self.o.pk]), {"rating": "5"})
        self.assertEqual(r.status_code, 404)

    def test_reviews_show_on_profile(self):
        self._finish()
        self._login("revbrand")
        self.client.post(reverse("review_add", args=[self.o.pk]), {"rating": "4", "comment": "Very professional"})
        self.assertContains(self.client.get(reverse("creator", args=["revmaker"])), "Very professional")

    def test_scores_stay_within_100(self):
        b = make("maxbrand", role="brand", verified=True, deals_done=50, rating_avg=5, rating_count=50, city="A", address="B", bio="x", niche="food")
        self.assertLessEqual(b.compute_score(), 100)


import io
import os
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ShopTests(TestCase):
    def setUp(self):
        cache.clear()
        self.b = make("shopby", role="brand", address="CG Road", city="Ahmedabad", bio="Cafe")
        self.client.login(username="shopby", password="pass-12345-xyz")

    def _png(self, name="shop.png"):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), "orange").save(buf, "PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def test_photo_is_reencoded_as_jpeg_and_served(self):
        self.client.post(reverse("photo_add"), {"image": self._png()})
        ph = ShopPhoto.objects.get()
        self.assertTrue(ph.image.name.endswith(".jpg"))
        r = self.client.get(ph.image.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/jpeg")
        b"".join(r.streaming_content)

    def test_non_images_are_rejected(self):
        self.client.post(reverse("photo_add"), {"image": SimpleUploadedFile("evil.png", b"<script>alert(1)</script>")})
        self.assertEqual(ShopPhoto.objects.count(), 0)

    def test_media_view_refuses_other_files(self):
        self.assertEqual(self.client.get("/media/passwd").status_code, 404)
        self.assertEqual(self.client.get("/media/nope.jpg").status_code, 404)

    def test_max_six_photos(self):
        for _ in range(7):
            self.client.post(reverse("photo_add"), {"image": self._png()})
        self.assertEqual(ShopPhoto.objects.count(), 6)

    def test_brand_page_shows_map_photos_and_address(self):
        self.client.post(reverse("photo_add"), {"image": self._png()})
        page = self.client.get(reverse("creator", args=["shopby"]))
        self.assertContains(page, "CG+Road")
        self.assertContains(page, "google.com/maps")
        self.assertContains(page, "shop photo 1")

    def test_verification_needs_address_and_photo_first(self):
        self.client.post(reverse("verify_request"))
        self.assertFalse(Profile.objects.get(handle="shopby").verify_requested)
        self.client.post(reverse("photo_add"), {"image": self._png()})
        self.client.post(reverse("verify_request"))
        self.assertTrue(Profile.objects.get(handle="shopby").verify_requested)

    def test_brands_leaderboard_lists_brands_not_creators(self):
        make("justcreator")
        page = self.client.get(reverse("leaderboard") + "?kind=brands")
        self.assertContains(page, "Shopby")
        self.assertNotContains(page, "Justcreator")


class HomeFeedTests(TestCase):
    def setUp(self):
        from .models import Campaign
        cache.clear()
        self.cr = make("starmaker", followers=20000, engagement=4, verified=True, bio="I make food reels", niche="food", city="Ahmedabad")
        self.br = make("tastycafe", role="brand", bio="A cosy cafe", city="Ahmedabad")
        Campaign.objects.create(brand=self.br.user, title="Monsoon menu launch", description="Taste and share",
                                niche="food", city="Ahmedabad", budget=12000, deliverables="2 reels + 1 story")

    def test_guest_home_loads_with_tabs_and_join_button(self):
        r = self.client.get(reverse("home"))
        self.assertEqual(r.status_code, 200)
        for word in ("For you", "Creators", "Brands", "Campaigns", "Join free"):
            self.assertContains(r, word)

    def test_each_tab_shows_its_own_content(self):
        self.assertContains(self.client.get(reverse("home") + "?feed=creators"), "Starmaker")
        self.assertNotContains(self.client.get(reverse("home") + "?feed=creators"), "Monsoon menu launch")
        self.assertContains(self.client.get(reverse("home") + "?feed=brands"), "Tastycafe")
        self.assertContains(self.client.get(reverse("home") + "?feed=campaigns"), "Monsoon menu launch")
        everything = self.client.get(reverse("home"))
        for word in ("Starmaker", "Tastycafe", "Monsoon menu launch"):
            self.assertContains(everything, word)

    def test_bad_feed_value_falls_back_to_for_you(self):
        self.assertEqual(self.client.get(reverse("home") + "?feed=<script>").status_code, 200)

    def test_signed_in_home_has_dashboard_strip_and_plus_button(self):
        self.client.login(username="tastycafe", password="pass-12345-xyz")
        r = self.client.get(reverse("home"))
        self.assertContains(r, "Dashboard")
        self.assertContains(r, reverse("campaign_new"))  # brands get the + button for campaigns

    def test_verified_uses_kite_mark_not_a_blue_tick(self):
        for url in (reverse("home"), reverse("creator", args=["starmaker"]), reverse("leaderboard")):
            page = self.client.get(url)
            self.assertContains(page, "kmark")
            self.assertNotContains(page, 'class="tick')


class LiveAndFunTests(TestCase):
    def setUp(self):
        cache.clear()
        self.brand = make("livebrand", role="brand")
        self.cr = make("livemaker", followers=3000, engagement=2)
        self.o = Offer.objects.create(brand=self.brand.user, creator=self.cr.user, title="Live", deliverables="1 reel",
                                      budget=5000, message="Hello first", status="accepted")

    def _login(self, name):
        self.client.login(username=name, password="pass-12345-xyz")

    def test_chat_box_sends_json_without_reload(self):
        self._login("livebrand")
        r = self.client.post(reverse("message_send", args=[self.o.pk]), {"body": "Hi there"}, HTTP_X_KYTO="chat")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(self.o.messages.get().pk, data["id"])

    def test_chat_box_errors_are_json_too(self):
        self._login("livebrand")
        self.assertEqual(self.client.post(reverse("message_send", args=[self.o.pk]), {"body": "  "}, HTTP_X_KYTO="chat").status_code, 400)
        Offer.objects.filter(pk=self.o.pk).update(status="declined")
        r = self.client.post(reverse("message_send", args=[self.o.pk]), {"body": "late"}, HTTP_X_KYTO="chat")
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()["ok"])

    def test_normal_form_post_still_redirects_for_no_javascript(self):
        self._login("livebrand")
        r = self.client.post(reverse("message_send", args=[self.o.pk]), {"body": "plain"})
        self.assertEqual(r.status_code, 302)

    def test_chat_page_gives_every_bubble_an_id_for_live_updates(self):
        self._login("livemaker")
        self.client.post(reverse("message_send", args=[self.o.pk]), {"body": "reply"})
        page = self.client.get(reverse("offer", args=[self.o.pk]))
        self.assertContains(page, 'data-id="0"')
        self.assertContains(page, "data-chat")
        self.assertContains(page, 'data-status="accepted"')

    def test_unread_badge_endpoint(self):
        self.assertEqual(self.client.get(reverse("unread_count")).status_code, 401)
        self._login("livebrand")
        self.client.post(reverse("message_send", args=[self.o.pk]), {"body": "from brand"})
        self._login("livemaker")
        r = self.client.get(reverse("unread_count"))
        self.assertEqual(r.json()["count"], 1)
        self.assertIn("no-store", r["Cache-Control"])

    def test_private_pages_are_not_cached_by_the_browser(self):
        self._login("livemaker")
        for url in (reverse("inbox"), reverse("settings"), reverse("offer", args=[self.o.pk])):
            self.assertIn("no-store", self.client.get(url)["Cache-Control"])

    def test_404_is_a_meme(self):
        r = self.client.get("/definitely-not-a-page/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "chai", status_code=404)
        self.assertContains(r, "meme", status_code=404)

    def test_niche_circles_have_icons_and_page_has_admin_hook_for_navigation(self):
        page = self.client.get(reverse("home"))
        self.assertContains(page, 'hl-circle"><svg')
        self.assertContains(page, "data-admin=")

    def test_inbox_and_proposals_are_live_regions(self):
        self._login("livemaker")
        self.assertContains(self.client.get(reverse("inbox")), 'data-region="threads"')
