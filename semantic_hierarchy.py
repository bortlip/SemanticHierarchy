#!/usr/bin/env python3
"""Generate semantic hierarchies for English words and expressions.

Install: python -m pip install -r requirements.txt
Usage:   python semantic_hierarchy.py "sign off"
         python semantic_hierarchy.py "sign off" "run" "set"
         python semantic_hierarchy.py --file expressions.txt
         python semantic_hierarchy.py "sign off" --definitions-file definitions.json

Reads OPENAI_API_KEY from the environment. Never writes the key to disk.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from pricing import calculated_cost_usd

DEFAULT_MODEL = "gpt-6-luna"


class Sense(BaseModel):
    meaning: str = Field(description="Specific meaning of the expression")
    construction: str = Field(description="Grammatical pattern, e.g. 'sign off on + noun'")
    example: str = Field(description="Natural English example sentence")


class SubConcept(BaseModel):
    label: str = Field(description="Short category name such as 'approval'")
    concept: str = Field(description="The shared semantic meaning of this group")
    senses: list[Sense] = Field(description="Specific senses belonging to the group")


class Hierarchy(BaseModel):
    expression: str
    top_level_concept: str | None = Field(
        description="Informative common meaning, or null if no useful one exists"
    )
    commonality: Literal["strong", "approximate", "none"]
    explanation: str = Field(description="How well the top-level concept fits the senses")
    sub_concepts: list[SubConcept]
    caveats: list[str] = Field(description="Exceptions, unrelated senses, or ambiguity")


# Keep the analysis instructions editable without changing application logic.
INSTRUCTIONS = (Path(__file__).resolve().parent / "prompts" / "analysis.txt").read_text(
    encoding="utf-8"
)


def load_definitions(path: Path | None) -> dict[str, list[str]]:
    """Load optional {expression: [definition, ...]} mapping."""
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Definitions file must be a JSON object mapping expressions to lists")
    for word, definitions in data.items():
        if (
            not isinstance(word, str)
            or not isinstance(definitions, list)
            or not all(isinstance(d, str) and d.strip() for d in definitions)
        ):
            raise ValueError(f"Invalid definitions entry for {word!r}")
    normalized: dict[str, list[str]] = {}
    for key, values in data.items():
        cleaned_key = key.strip().casefold()
        if not cleaned_key or cleaned_key in normalized:
            raise ValueError(f"Duplicate or empty definitions key: {key!r}")
        if not values:
            raise ValueError(f"Definitions list cannot be empty: {key!r}")
        normalized[cleaned_key] = values
    return normalized


def load_expressions(args: argparse.Namespace) -> list[str]:
    expressions = list(args.expressions)
    if args.file is not None:
        for line in args.file.read_text(encoding="utf-8-sig").splitlines():
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                expressions.append(cleaned)
    # Deduplicate case-insensitively while retaining original spelling and order.
    result: list[str] = []
    seen: set[str] = set()
    for word in expressions:
        cleaned = word.strip()
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            result.append(cleaned)
    return result


def token_usage(usage: object) -> dict[str, int] | None:
    """Read provider usage; unknown usage is not a zero-cost request."""
    if (
        usage is None
        or getattr(usage, "input_tokens", None) is None
        or getattr(usage, "output_tokens", None) is None
    ):
        return None
    details_in = getattr(usage, "input_tokens_details", None)
    details_out = getattr(usage, "output_tokens_details", None)
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "cached_input_tokens": int(getattr(details_in, "cached_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "reasoning_tokens": int(getattr(details_out, "reasoning_tokens", 0) or 0),
    }


def analyze(
    client: object,
    expression: str,
    definitions: list[str],
    reasoning: str,
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 4000,
) -> dict:
    input_text = json.dumps(
        {"expression": expression, "definitions": definitions or None},
        ensure_ascii=False,
    )
    response = client.responses.parse(
        model=model,
        instructions=INSTRUCTIONS,
        input=input_text,
        text_format=Hierarchy,
        reasoning={"effort": reasoning},
        max_output_tokens=max_output_tokens,
        store=False,
    )
    if response.status != "completed" or response.output_parsed is None:
        raise RuntimeError(
            f"No complete structured result for {expression!r}: "
            f"status={response.status}, reason={getattr(response, 'incomplete_details', None)}"
        )
    usage = token_usage(response.usage)
    return {
        "analysis": response.output_parsed.model_dump(),
        "usage": usage,
        "calculated_cost_usd": calculated_cost_usd(usage, model),
    }


def save_results(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expressions", nargs="*", help="One or more quoted words or expressions")
    parser.add_argument("--file", type=Path, help="UTF-8 text file with one expression per line")
    parser.add_argument(
        "--definitions-file",
        type=Path,
        help='Optional JSON mapping expressions to lists of definitions, e.g. {"sign off": ["..."]}',
    )
    parser.add_argument("--output", type=Path, default=Path("results/semantic_results.json"))
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help="OpenAI model ID (default: gpt-6-luna)"
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=4000,
        help="Maximum billable output tokens per request (default: 4000)",
    )
    parser.add_argument(
        "--reasoning",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
        default="low",
        help="Reasoning effort (default: low)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        expressions = load_expressions(args)
        definitions = load_definitions(args.definitions_file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    if not 100 <= args.max_output_tokens <= 10000:
        parser.error("--max-output-tokens must be between 100 and 10000")
    if not expressions:
        parser.error('Provide an expression, e.g. "sign off", or --file expressions.txt')
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is not set in your environment")

    try:
        from openai import OpenAI
    except ImportError:
        parser.error("OpenAI SDK is missing. Run: python -m pip install -r requirements.txt")

    client = OpenAI(
        max_retries=0, timeout=90.0
    )  # Automatically reads OPENAI_API_KEY; no automatic duplicate requests.
    payload = {
        "model": args.model,
        "reasoning_effort": args.reasoning,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": [],
        "errors": [],
        "totals": {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "calculated_cost_usd": 0.0,
        },
    }

    for i, expression in enumerate(expressions, 1):
        print(f"\n[{i}/{len(expressions)}] {expression}", flush=True)
        try:
            result = analyze(
                client,
                expression,
                definitions.get(expression.casefold(), []),
                args.reasoning,
                model=args.model,
                max_output_tokens=args.max_output_tokens,
            )
        except Exception as error:
            # Preserve earlier successful results. A failed/incomplete API request may
            # still consume tokens; we cannot price it without a returned usage object.
            message = f"{type(error).__name__}: {error}"
            payload["errors"].append({"expression": expression, "error": message})
            print(f"  ERROR: {message}", file=sys.stderr)
            save_results(args.output, payload)
            continue

        payload["results"].append(result)
        if result["usage"] is not None:
            for field in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_tokens",
            ):
                payload["totals"][field] += result["usage"][field]
        if result["calculated_cost_usd"] is None:
            payload["totals"]["calculated_cost_usd"] = None
        elif payload["totals"]["calculated_cost_usd"] is not None:
            payload["totals"]["calculated_cost_usd"] += result["calculated_cost_usd"]
        save_results(args.output, payload)

        analysis = result["analysis"]
        print(f"  Core: {analysis['top_level_concept'] or '(no useful shared core)'}")
        print(f"  Commonality: {analysis['commonality']} — {analysis['explanation']}")
        for family in analysis["sub_concepts"]:
            print(f"    - {family['label']}: {family['concept']}")
            for sense in family["senses"]:
                print(f"        {sense['meaning']} [{sense['construction']}]")
                print(f"        Example: {sense['example']}")
        if analysis["caveats"]:
            print("  Caveats: " + "; ".join(analysis["caveats"]))
        u = result["usage"]
        cost = result["calculated_cost_usd"]
        cost_label = f"${cost:.7f}" if cost is not None else "unavailable for this model"
        if u is None:
            print(f"  Tokens: unavailable | Calculated cost: {cost_label}")
        else:
            print(
                f"  Tokens: {u['input_tokens']} in ({u['cached_input_tokens']} cached), "
                f"{u['output_tokens']} out ({u['reasoning_tokens']} reasoning)"
                f" | Calculated cost: {cost_label}"
            )

    total = payload["totals"]["calculated_cost_usd"]
    total_label = f"${total:.6f}" if total is not None else "unavailable for this model"
    print(f"\nSaved: {args.output.resolve()}")
    print(
        f"Successful: {len(payload['results'])}/{len(expressions)}; "
        f"calculated total token cost: {total_label}"
    )
    return 0 if not payload["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
