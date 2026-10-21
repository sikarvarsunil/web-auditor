# Implementation plan

## Phase 0 — Baseline and product scope
- Agree on target users, page types, supported image formats, audit objectives, and retention.
- Define success as finding precision, evidence quality, and recommendation usefulness—not a made-up single score.
- Keep the first release single-page and read-only. Do not submit forms, click destructive actions, or crawl arbitrary links by default.

## Phase 1 — Screenshot MVP (included)
1. Build the React input form and report dashboard.
2. Validate PNG/JPEG uploads, file size, and dimensions.
3. Send screenshot and rubric to a vision model.
4. Require exactly ten heuristic results and validate with Pydantic.
5. Render findings, evidence, severity, confidence, and limitations.
6. Export JSON for review and regression testing.

Acceptance criteria:
- All ten heuristic IDs appear exactly once.
- Unsupported claims are marked not_observed.
- Each issue includes evidence, user impact, recommendation, severity, and confidence.
- Provider errors are visible; the system never invents a successful report.

## Phase 2 — URL audit (included as starter)
1. Validate URL syntax and public DNS addresses.
2. Capture desktop or mobile viewport with Playwright.
3. Collect screenshot, page title, headings, buttons, links, form controls, image alt coverage, and document language.
4. Submit the image and limited DOM evidence to the vision model.
5. Validate and display the report.
6. Add controlled handling for timeouts, blocked pages, huge pages, and redirects.

Before internet exposure: run browser capture in a separate sandbox/container with enforced egress rules. URL/DNS checks in application code are defense in depth, not a complete SSRF defense.

## Phase 3 — Better evidence and UX
- Multi-page page selection and bounded crawl depth.
- Separate desktop/mobile reports and comparison view.
- Screenshot annotation with element bounding boxes and issue markers.
- Accessibility checks using axe-core plus DOM semantics; treat automated checks as separate evidence from heuristic findings.
- Optional interaction tests against an explicit, safe action plan; use staging/test accounts only.
- Add evidence links and source excerpts for each finding.

## Phase 4 — Production readiness
- Authentication and per-user authorization.
- Async job queue, status endpoint, cancellation, retry policy, and idempotency keys.
- MongoDB report persistence and object storage for screenshots with retention/deletion.
- Redis rate limiting/caching only if needed.
- Strict egress firewall, isolated browser workers, CPU/memory/time limits, request limits, DNS rebinding defense.
- Secret management, audit logs, structured logging, metrics, tracing, error reporting.
- CI with lint, typecheck, tests, dependency scanning, container scanning, and image pinning.
- Human review and periodic benchmark evaluation of audit quality.

## Suggested API evolution
- POST /api/audits/screenshot -> report for MVP; later return job ID.
- POST /api/audits/url -> report for MVP; later return job ID.
- GET /api/audits/{id} -> persisted report.
- GET /api/audits/{id}/status -> async status.
- GET /api/heuristics -> registry.

## Evaluation plan
Build a benchmark set of representative websites and screenshots. Have at least two UX reviewers label issues, severity, and evidence. Track precision/recall by heuristic, severity agreement, unsupported-claim rate, evidence coverage, and reviewer acceptance of recommendations. Re-run this benchmark when prompts or models change.
