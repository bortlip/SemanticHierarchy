"""Local-only FastAPI interface to the semantic hierarchy analyzer."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pricing import MODELS, PRICING_CHECKED, PRICING_SOURCE, public_catalog
from semantic_hierarchy import analyze

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
MAX_WORDS = 12
MAX_DEFINITIONS = 30
MAX_DEFINITION_CHARS = 8000

app = FastAPI(
    title="Semantic Hierarchy",
    description="Local API for exploratory semantic analysis",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AnalysisRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=120)
    model: str = "gpt-6-luna"
    reasoning: str = "low"
    max_output_tokens: int = Field(default=4000, ge=500, le=8000)
    definitions: list[str] = Field(default_factory=list, max_length=MAX_DEFINITIONS)

    @field_validator("expression")
    @classmethod
    def clean_expression(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Expression cannot be blank")
        return value

    @field_validator("definitions")
    @classmethod
    def clean_definitions(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("Definitions must be nonempty strings")
        if sum(len(value) for value in values) > MAX_DEFINITION_CHARS:
            raise ValueError("Definitions are too long")
        return [value.strip() for value in values]


@lru_cache(maxsize=1)
def get_client():
    from openai import OpenAI

    return OpenAI(max_retries=0, timeout=90.0)


def valid_origin(request: Request) -> bool:
    """Reject cross-origin browser requests, even when directed to localhost."""
    origin = request.headers.get("origin")
    if not origin:
        return True  # Scripts and curl normally omit Origin.
    try:
        parsed = urlsplit(origin)
        expected = urlsplit(str(request.base_url))
        return (
            parsed.scheme == expected.scheme
            and parsed.hostname == expected.hostname
            and parsed.port == expected.port
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    return response


@app.get("/")
async def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
async def config():
    return {
        "models": public_catalog(),
        "default_model": "gpt-6-luna",
        "has_api_key": bool(os.getenv("OPENAI_API_KEY")),
        "max_words": MAX_WORDS,
        "pricing_checked": PRICING_CHECKED,
        "pricing_source": PRICING_SOURCE,
    }


@app.post("/api/analyze")
async def analyze_expression(payload: AnalysisRequest, request: Request):
    if not valid_origin(request):
        raise HTTPException(status_code=403, detail="Cross-origin requests are disabled")
    model = MODELS.get(payload.model)
    if model is None:
        raise HTTPException(status_code=422, detail="Unsupported model")
    if payload.reasoning not in model["efforts"]:
        raise HTTPException(
            status_code=422, detail="Reasoning effort is not supported by this model"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="Set OPENAI_API_KEY in the server environment")

    try:
        result = await run_in_threadpool(
            analyze,
            get_client(),
            payload.expression,
            payload.definitions,
            payload.reasoning,
            payload.model,
            payload.max_output_tokens,
        )
    except Exception as error:
        # Never leak server paths, key material, upstream request content, or
        # verbose SDK exceptions to a browser. Failed calls may still be billed.
        raise HTTPException(
            status_code=502,
            detail=f"Model request failed ({type(error).__name__}). Check server logs or model access.",
        ) from None
    return JSONResponse(
        {
            "expression": payload.expression,
            "model": payload.model,
            "reasoning": payload.reasoning,
            "analysis": result["analysis"],
            "usage": result["usage"],
            "calculated_cost_usd": result["calculated_cost_usd"],
            "cost_kind": (
                "calculated_from_usage"
                if result["calculated_cost_usd"] is not None
                else "unavailable"
            ),
        }
    )
