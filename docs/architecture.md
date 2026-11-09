# Architecture

Semantic Hierarchy is a small Python and browser application with no database or JavaScript build pipeline.

```text
Browser (static/) -> FastAPI (web_app.py) -> analyze() (semantic_hierarchy.py)
                     |                          |
                     | validate input           +-> prompts/analysis.txt
                     |                          +-> OpenAI Responses API
                     |                                      |
                     +-> pricing.py <-------------- token usage + result

CLI (semantic_hierarchy.py) -> same analyzer and pricing table
```

- `prompts/analysis.txt` holds editable semantic-grouping instructions.
- `semantic_hierarchy.py` defines the structured result and makes one model request per expression. The CLI processes multiple terms sequentially and saves output under ignored `results/`.
- `pricing.py` calculates a nominal standard USD charge from API usage: uncached input, cached input, and output (including reasoning tokens). No exact per-response dollar invoice is available.
- `web_app.py` serves local-only routes and sanitizes upstream errors. The browser limits submissions to 12 expressions, but the server has no user accounts or durable cost quotas.
- `static/app.js` renders model output as text rather than injected HTML and keeps history in tab-scoped storage. Stop prevents future requests, not in-flight charges.
- `scripts/start.py` starts a local server and opens the browser after readiness; `scripts/start.cmd` is the Windows double-click wrapper.

Automated tests mock API responses. See [CONTRIBUTING.md](../CONTRIBUTING.md). Live tests are manual and billable.
