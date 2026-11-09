# Security and privacy

This is a **local, single-user application**, not an authenticated public service. Bind the server to `127.0.0.1` only. Do not use `--host 0.0.0.0`, port forwarding, tunnels, or a public reverse proxy without a separate security review and authentication, access controls, and rate limits.

Supply `OPENAI_API_KEY` in the process environment, not source code. The backend sends expressions and optional definitions to the model API. Avoid private or copyrighted definitions unless you may transmit them.

The browser stores tab history in `sessionStorage`, and explicit export saves it to disk. Browsers may restore closed tabs. Failed API calls may still incur charges without usable token counts.

Trusted-host, Origin, and content-security checks are defense in depth, **not authentication**. Local processes and users may still access the localhost server.

For sensitive reports, use private vulnerability reporting in the repository's Security tab if available; do not publish credentials or exploit details in an issue.
