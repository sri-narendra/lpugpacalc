import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class LoginErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_login_returns_json_when_backend_fetch_fails(self):
        original_get_page = main.get_page_with_turnstile

        def fail_fetch():
            raise RuntimeError("upstream unavailable")

        main.get_page_with_turnstile = fail_fetch
        try:
            response = self.client.post(
                "/login",
                json={"userid": "student", "password": "secret"},
            )
        finally:
            main.get_page_with_turnstile = original_get_page

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertEqual(
            response.get_json(),
            {
                "ok": False,
                "error": "Failed to fetch login page: upstream unavailable",
            },
        )

    def test_login_returns_json_when_data_fetch_fails_after_successful_login(self):
        originals = {
            "get_page_with_turnstile": main.get_page_with_turnstile,
            "parse_form_fields": main.parse_form_fields,
            "login": main.login,
            "fetch_all_data": main.fetch_all_data,
        }

        main.get_page_with_turnstile = lambda: "<html></html>"
        main.parse_form_fields = lambda html: {
            "turnstile_token": "token",
            "password_field": "password",
        }
        main.login = lambda sess, userid, password, fields: True

        def fail_data_fetch(sess):
            raise RuntimeError("dashboard api unavailable")

        main.fetch_all_data = fail_data_fetch
        try:
            response = self.client.post(
                "/login",
                json={"userid": "student", "password": "secret"},
            )
        finally:
            for name, value in originals.items():
                setattr(main, name, value)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertEqual(
            response.get_json(),
            {
                "ok": False,
                "error": "Failed to fetch dashboard data: dashboard api unavailable",
            },
        )


if __name__ == "__main__":
    unittest.main()
