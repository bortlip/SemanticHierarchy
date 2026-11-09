# Contributing

Semantic Hierarchy favors readable code and careful linguistic explanations. Its model-generated concepts are hypotheses, not dictionary facts.

## Development

Use Python 3.10 or newer and an isolated virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On Linux/macOS use `python3` and `.venv/bin/python`. All these checks work offline without API credentials.

## Code map

- `prompts/analysis.txt`: editable linguistic instructions
- `semantic_hierarchy.py`: shared analysis function, schema, and CLI
- `pricing.py`: model catalog and nominal token-cost math
- `web_app.py`: local HTTP API and validation
- `static/`: browser UI without a build step
- `scripts/`: local launcher
- `tests/`: mocked tests; never real API calls

See [architecture](docs/architecture.md) for the request flow.

## Pull requests

Describe behavior changes and include tests. For prompt edits, mention representative expressions and possible regressions. For model pricing, check the provider's published input, cached-input, and output rates and update the reviewed date.

Do not commit API credentials, .env files, personal definitions, generated analyses, or usage exports. Please keep new dependencies and abstractions proportional to the application's small scope.
