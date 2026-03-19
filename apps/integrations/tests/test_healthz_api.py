from django.test import SimpleTestCase


class HealthzApiTests(SimpleTestCase):
    def test_healthz_returns_ok(self):
        response = self.client.get("/api/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
