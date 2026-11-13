"""Load test. Install with `pip install locust`, then:
    locust -f scripts/locustfile.py --host https://your-site
Set KYTO_USER and KYTO_PASS to a real test account (create one on a staging copy, not production)."""
import os
import re

from locust import HttpUser, between, task


class Member(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        page = self.client.get("/login/")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text).group(1)
        self.client.post("/login/", {"username": os.environ["KYTO_USER"], "password": os.environ["KYTO_PASS"],
                                     "csrfmiddlewaretoken": token, "remember": "on"}, headers={"Referer": self.host + "/login/"})

    @task(5)
    def feed(self):
        self.client.get("/")

    @task(3)
    def explore(self):
        self.client.get("/leaderboard/")

    @task(2)
    def campaigns(self):
        self.client.get("/campaigns/")

    @task(2)
    def inbox(self):
        self.client.get("/inbox/?partial=1", name="/inbox/?partial=1")

    @task(4)
    def badge(self):
        self.client.get("/api/unread/")

    @task(1)
    def health(self):
        self.client.get("/readyz/")
