"""Deterministic unit tests. These never make an API request."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import semantic_hierarchy as sh


class SemanticHierarchyTests(unittest.TestCase):
    def test_standard_cost(self):
        usage = {
            "input_tokens": 600,
            "cached_input_tokens": 0,
            "output_tokens": 450,
            "reasoning_tokens": 100,
        }
        self.assertAlmostEqual(sh.calculated_cost_usd(usage), 0.000285)

    def test_missing_usage_is_unknown_not_free(self):
        self.assertIsNone(sh.token_usage(None))
        self.assertIsNone(sh.calculated_cost_usd(None))

    def test_partial_usage_is_unknown(self):
        usage = SimpleNamespace(input_tokens=None, output_tokens=100)
        self.assertIsNone(sh.token_usage(usage))

    def test_prompt_is_loaded_from_editable_file(self):
        prompt = Path(__file__).resolve().parents[1] / "prompts/analysis.txt"
        self.assertTrue(prompt.is_file())
        self.assertEqual(sh.INSTRUCTIONS, prompt.read_text(encoding="utf-8"))
        self.assertIn("common", sh.INSTRUCTIONS.lower())

    def test_cached_cost(self):
        usage = {
            "input_tokens": 1000,
            "cached_input_tokens": 800,
            "output_tokens": 0,
            "reasoning_tokens": 0,
        }
        self.assertAlmostEqual(sh.calculated_cost_usd(usage), 0.000028)

    def test_unknown_model_has_no_cost_estimate(self):
        usage = {
            "input_tokens": 600,
            "cached_input_tokens": 0,
            "output_tokens": 450,
            "reasoning_tokens": 100,
        }
        self.assertIsNone(sh.calculated_cost_usd(usage, model="different-model"))

    def test_usage_reasoning_already_counted(self):
        usage = SimpleNamespace(
            input_tokens=100,
            output_tokens=200,
            input_tokens_details=SimpleNamespace(cached_tokens=10),
            output_tokens_details=SimpleNamespace(reasoning_tokens=90),
        )
        self.assertEqual(
            sh.token_usage(usage),
            {
                "input_tokens": 100,
                "cached_input_tokens": 10,
                "output_tokens": 200,
                "reasoning_tokens": 90,
            },
        )

    def test_definitions_are_case_insensitive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "definitions.json"
            path.write_text('{"Sign Off": ["End a call", "Approve a plan"]}', encoding="utf-8")
            self.assertEqual(
                sh.load_definitions(path)["sign off"], ["End a call", "Approve a plan"]
            )

    def test_invalid_definitions_fail_early(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "definitions.json"
            path.write_text('{"word": []}', encoding="utf-8")
            with self.assertRaises(ValueError):
                sh.load_definitions(path)

    def test_deduplicate_preserves_first_and_order(self):
        args = argparse.Namespace(expressions=["Run", "bank", "run", "set", "BANK"], file=None)
        self.assertEqual(sh.load_expressions(args), ["Run", "bank", "set"])

    def test_api_request_schema_and_no_storage(self):
        hierarchy = sh.Hierarchy(
            expression="sign off",
            top_level_concept="ending an activity",
            commonality="approximate",
            explanation="Approval is distinct.",
            sub_concepts=[
                sh.SubConcept(
                    label="communication",
                    concept="ending contact",
                    senses=[
                        sh.Sense(
                            meaning="stop broadcasting",
                            construction="sign off",
                            example="The presenter signed off.",
                        )
                    ],
                )
            ],
            caveats=["Signing off on a plan is approval."],
        )
        response = SimpleNamespace(
            status="completed",
            output_parsed=hierarchy,
            usage=SimpleNamespace(
                input_tokens=200,
                output_tokens=300,
                input_tokens_details=SimpleNamespace(cached_tokens=0),
                output_tokens_details=SimpleNamespace(reasoning_tokens=40),
            ),
        )
        client = Mock()
        client.responses.parse.return_value = response
        result = sh.analyze(
            client, "sign off", [], "low", model="gpt-6-luna", max_output_tokens=1200
        )
        kwargs = client.responses.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-6-luna")
        self.assertEqual(kwargs["max_output_tokens"], 1200)
        self.assertFalse(kwargs["store"])
        self.assertEqual(result["analysis"]["commonality"], "approximate")
        self.assertAlmostEqual(result["calculated_cost_usd"], 0.00017)

    def test_atomic_json_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results" / "data.json"
            sh.save_results(path, {"results": [1]})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"results": [1]})
            self.assertFalse(path.with_name("data.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
