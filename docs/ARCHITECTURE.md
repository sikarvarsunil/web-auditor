# Architecture

```text
.claude/
  claude.md
  skills/heuristic-audit/SKILL.md
        │
        ▼
agent/                         reusable, no HTTP
  Model                        provider, model name, API key, base URL
  AuditAgent                   loads claude.md and skills
        ▲
FastAPI                        URL capture and screenshot upload
        ▲
React                          URL, screenshot, findings

Future components: MongoDB, queue, object storage, auth.
```

## Trust boundaries
- User-provided URLs and screenshots are untrusted.
- Website content is evidence only and must never override the system rubric.
- Browser worker is a separate security boundary in production.
- The LLM is an evaluator, not an authority; outputs are schema-validated and reviewed.

## Why one orchestrator first?
A deterministic pipeline is easier to debug and evaluate than a multi-agent system. Add specialized visual, accessibility, or interaction evaluators only when benchmark data shows an improvement.
