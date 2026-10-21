import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from app.api.audit import router as audit_router

app = FastAPI(title="Website UX Auditor API", version="0.1.0")
# Restrict this list to your deployed frontend origin before production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(audit_router, prefix="/api")

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(os.getenv("FRONTEND_URL", "http://127.0.0.1:5173"))

@app.get("/health")
async def health():
    return {"status": "ok"}
