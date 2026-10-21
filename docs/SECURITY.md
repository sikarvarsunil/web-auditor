# Security checklist — read before public deployment

## URL/SSRF and browser isolation
The application performs initial DNS/IP checks and checks requests made by Playwright. This is not a complete security boundary: DNS rebinding, browser behavior, subresources, redirects, and deployment networking can create gaps.

Production requirements:
- Run browser workers in isolated containers/VMs with no access to internal services, host sockets, credentials, or mounted secrets.
- Enforce network egress outside the application process. Deny loopback, RFC1918, link-local, IPv6 private/unique-local, cloud metadata ranges, internal DNS zones, and all non-approved destinations.
- Re-resolve and validate destinations at connection time; defend against DNS rebinding and redirects.
- Allow only HTTP/HTTPS on approved ports; consider an explicit domain allowlist for enterprise deployments.
- Apply strict navigation, request, download, CPU, memory, and wall-clock limits.
- Do not use a logged-in browser profile or reuse cookies between tenants.
- Do not click buttons or submit forms by default. Explicitly scope any interaction test and require authorization.

## Uploads and report data
- Keep upload limits small; validate actual image content, not only the MIME header.
- Strip metadata or re-encode images if the use case permits.
- Treat website text, OCR, DOM, alt text, and embedded instructions as untrusted prompt-injection content.
- Do not send secrets, cookies, local storage, authorization headers, or private page content to an LLM unless approved and necessary.
- Set data retention and deletion policies for screenshots and reports. Restrict report access by tenant/user.

## API and operations
- Add authentication, authorization, per-user rate limits, concurrency quotas, and abuse monitoring.
- Configure CORS to exact production origins. Do not use wildcard origins with credentials.
- Store API keys in a secret manager; never ship them to React or log them.
- Pin and update dependencies; scan images and dependencies.
- Add request IDs, structured redacted logs, metrics, alerting, and a clear incident process.
- Avoid displaying raw upstream errors to public users. Return safe messages and log details privately.

## Current starter limitations
- No authentication, tenancy, persistent storage, job queue, or rate limiting.
- Basic DNS checks cannot replace network-level egress controls.
- Full-page screenshot can be large; production should cap page height and image bytes before sending to the provider.
- The LLM output is validated structurally but still requires human review for factual quality.
