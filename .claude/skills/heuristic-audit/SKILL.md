---
name: heuristic-audit
description: Audits a website URL capture or screenshot against Jakob Nielsen's 10 usability heuristics. Use when evaluating a page, screenshot, or UX audit.
disable-model-invocation: true
---

# Heuristic audit

Evaluate every heuristic in the supplied registry exactly once. Do not claim an interaction was tested unless interaction evidence is explicitly provided. A static screenshot cannot establish behavior that is not visible.

If evidence is insufficient, use status `not_observed`, severity `not_observed`, confidence at or below 0.5, and explain the limitation. If no issue is visible, use status `no_issue_observed` and state that this does not prove the heuristic is satisfied in every state.

For each finding:

- Cite specific visual, DOM, accessibility, or interaction evidence.
- Distinguish observation from inference.
- Explain plausible user impact without overstating certainty.
- Recommend a concrete, feasible improvement.
- Severity: `critical` means a confirmed major task is blocked; `high` means significant friction or risk; `medium` means a meaningful recoverable problem; `low` means a minor improvement; `not_observed` means insufficient evidence.
- Confidence is 0.0–1.0 for this assessment only, not an overall site score.
- Do not invent benchmark scores or claim legal or accessibility compliance from a screenshot alone.

Return JSON with exactly 10 findings, IDs 1 through 10 once each. Include a concise summary and methodology limitations.
