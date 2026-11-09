"""Offline web app and pricing tests; never contact the OpenAI API."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import pricing
import web_app


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.usage = {
            "input_tokens": 708,
            "cached_input_tokens": 0,
            "output_tokens": 579,
            "reasoning_tokens": 94,
        }

    def test_sol_standard_price_uses_real_usage(self):
        self.assertAlmostEqual(pricing.calculated_cost_usd(self.usage, "gpt-6-sol"), 0.007206)

    def test_sol_cached_input_rate(self):
        usage = {
            "input_tokens": 1000,
            "cached_input_tokens": 800,
            "output_tokens": 0,
            "reasoning_tokens": 0,
        }
        self.assertAlmostEqual(pricing.calculated_cost_usd(usage, "gpt-6-sol"), 0.00056)

    def test_luna_price(self):
        self.assertAlmostEqual(pricing.calculated_cost_usd(self.usage, "gpt-6-luna"), 0.0003603)

    def test_cached_tokens_are_not_double_charged(self):
        usage = {
            "input_tokens": 1000,
            "cached_input_tokens": 800,
            "output_tokens": 50,
            "reasoning_tokens": 25,
        }
        self.assertAlmostEqual(pricing.calculated_cost_usd(usage, "gpt-6-luna"), 0.000053)

    def test_unknown_pricing_is_not_guessed(self):
        self.assertIsNone(pricing.calculated_cost_usd(self.usage, "made-up-model"))

    def test_catalog_does_not_contain_keys(self):
        for item in pricing.public_catalog():
            self.assertNotIn("api_key", item)
            self.assertIn("input", item)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(web_app.app, base_url="http://127.0.0.1:8000")

    def test_home_and_assets(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("Semantic Hierarchy", home.text)
        self.assertEqual(self.client.get("/static/style.css").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertIn("script-src 'self'", home.headers["content-security-policy"])

    def test_config_contains_supported_models_but_no_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}):
            result = self.client.get("/api/config")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["has_api_key"])
        self.assertNotIn("test-secret", result.text)
        self.assertEqual(result.json()["max_words"], 12)

    def test_refuse_cross_origin(self):
        response = self.client.post(
            "/api/analyze",
            headers={"Origin": "https://attacker.example"},
            json={"expression": "bank"},
        )
        self.assertEqual(response.status_code, 403)

    def test_reject_unsupported_model(self):
        response = self.client.post(
            "/api/analyze", json={"expression": "bank", "model": "injected"}
        )
        self.assertEqual(response.status_code, 422)

    def test_reject_incompatible_effort(self):
        response = self.client.post(
            "/api/analyze", json={"expression": "bank", "model": "gpt-6.1-sol", "reasoning": "none"}
        )
        self.assertEqual(response.status_code, 422)

    def test_no_key_does_not_call_api(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post("/api/analyze", json={"expression": "bank"})
        self.assertEqual(response.status_code, 503)

    def test_backend_passes_through_structured_result(self):
        fake_result = {
            "analysis": {
                "expression": "bank",
                "top_level_concept": None,
                "commonality": "none",
                "explanation": "Distinct senses",
                "sub_concepts": [],
                "caveats": [],
            },
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 200,
                "reasoning_tokens": 0,
            },
            "calculated_cost_usd": 0.00011,
        }
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}),
            patch.object(web_app, "get_client", return_value=object()),
            patch.object(web_app, "analyze", return_value=fake_result) as analyze,
        ):
            response = self.client.post(
                "/api/analyze",
                json={"expression": "bank", "model": "gpt-6-luna", "reasoning": "low"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cost_kind"], "calculated_from_usage")
        self.assertEqual(response.json()["analysis"]["commonality"], "none")
        self.assertEqual(analyze.call_count, 1)

    def test_missing_usage_does_not_claim_calculated_cost(self):
        fake_result = {
            "analysis": {
                "expression": "bank",
                "top_level_concept": None,
                "commonality": "none",
                "explanation": "Different senses",
                "sub_concepts": [],
                "caveats": [],
            },
            "usage": None,
            "calculated_cost_usd": None,
        }
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}),
            patch.object(web_app, "get_client", return_value=object()),
            patch.object(web_app, "analyze", return_value=fake_result),
        ):
            response = self.client.post("/api/analyze", json={"expression": "bank"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cost_kind"], "unavailable")
        self.assertIsNone(response.json()["calculated_cost_usd"])

    def test_upstream_errors_are_sanitized(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}),
            patch.object(web_app, "get_client", return_value=object()),
            patch.object(web_app, "analyze", side_effect=RuntimeError("secret-user-path-internal")),
        ):
            response = self.client.post("/api/analyze", json={"expression": "bank"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret-user-path-internal", response.text)

    def test_no_external_host(self):
        response = self.client.get("/api/config", headers={"host": "external.example"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
