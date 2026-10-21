# Website UX Auditor — Starter Kit

A runnable starter for auditing a website URL or screenshot against Jakob Nielsen's 10 usability heuristics.

The project is published at https://github.com/sikarvarsunil/web-auditor. Other people run it on their own computer with the Docker steps below, then open http://localhost:5173. GitHub can show this repository, but it cannot host the running auditor: the app has no login and it opens whatever site a visitor submits. Read `docs/SECURITY.md` before putting it on the public internet.

## What is included
- React + TypeScript + Vite UI with URL and screenshot input modes.
- FastAPI backend with Pydantic response models.
- Playwright URL capture (screenshot + limited page evidence).
- A reusable audit agent in `agent/`, instructed by `.claude/claude.md` and `.claude/skills`.
- One model wrapper. Swap the provider, model name, API key, or base URL.
- Docker Compose, tests, and security/deployment documentation.

## Requirements
- Docker + Docker Compose **or** Node.js 20+ and Python 3.11+.
- A model provider. Claude needs `ANTHROPIC_API_KEY`. Ollama and other local servers need a vision-capable model. Without a configured provider, the API returns a configuration error rather than fake findings.

## Quick start (Docker)
1. Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.
2. Run `docker compose up --build`.
3. Open http://localhost:5173.

The frontend uses `/api` and Vite proxies to the backend in local development. For the Docker setup, the frontend dev server is configured to proxy to `backend:8000`.

## Quick start (local)
Backend:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
playwright install chromium
PYTHONPATH=.:.. uvicorn app.main:app --reload --port 8000
```
Frontend, in another terminal:
```bash
cd apps/web
npm install
npm run dev
```
Open http://localhost:5173.

## Model provider
Set `AUDIT_PROVIDER` in `.env`.

Claude, the default:

```bash
AUDIT_PROVIDER=anthropic
ANTHROPIC_API_KEY=replace_me
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

Any vision model served by Ollama:

```bash
AUDIT_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llava
ollama pull llava
```

Other examples: `llama3.2-vision`, `qwen2.5vl`, `gemma3`. The model must accept images. When the backend runs in Docker and Ollama runs on the host, use `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

Any OpenAI-compatible server, including Ollama’s `/v1` endpoint, LM Studio, vLLM, LocalAI, and llama.cpp:

```bash
AUDIT_PROVIDER=openai
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=llava
OPENAI_API_KEY=not-required
```

`GET /api/provider` reports which provider and model are active.

Use the agent without the API:

```python
from agent import AuditAgent, Model

agent = AuditAgent(Model(provider="ollama", model="llava"))
report = agent.audit(image_bytes, "image/png", "screenshot", "upload.png", "desktop", None, None)
```

`Model` accepts `provider`, `model`, `api_key`, and `base_url`. Leave any of them unset to read the environment variables above. The agent loads `.claude/claude.md` and every skill in `.claude/skills`.

## Current MVP behavior
- Screenshot mode accepts PNG/JPEG and submits it to the configured vision model.
- URL mode validates the URL, captures the page with Playwright, and submits the screenshot plus extracted page evidence.
- The report evaluates all 10 heuristics and can mark a heuristic `not_observed` when evidence is insufficient.
- The report is returned to the browser; persistence, authentication, PDF export, and multi-page crawling are not included yet.

## API
- `GET /health`
- `GET /api/heuristics`
- `GET /api/provider`
- `POST /api/audits/screenshot` — multipart `file`
- `POST /api/audits/url` — JSON `{ "url": "https://example.com", "viewport": "desktop" }`

## Important security note
This is a development starter, not a production-hardened public URL scanner. Read `docs/SECURITY.md` before exposing it to the internet. Browser isolation, strict egress firewalling, rate limits, authentication, DNS-rebinding protections, storage controls, and abuse monitoring are required for production.
