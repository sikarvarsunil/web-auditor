import base64
import os
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from agent.audit import AuditAgent
from agent.heuristics import HEURISTICS
from agent.model import ModelConfigError, ModelRequestError, _fit_image, describe_model
from agent.report import AuditReport, ReviewedPage
from app.schemas.audit import UrlAuditRequest
from app.services.browser_capture import BrowserCaptureError, capture_website, UnsafeUrlError

def _attach_pages(report: AuditReport, shots: list[dict]) -> AuditReport:
    pages = []
    for shot in shots[:3]:
        image, media_type = _fit_image(shot["image"], shot.get("media_type") or "image/png")
        pages.append(ReviewedPage(
            url=str(shot.get("url") or "Reviewed page")[:2000],
            title=(str(shot["title"])[:300] if shot.get("title") else None),
            image=f"data:{media_type};base64,{base64.b64encode(image).decode('ascii')}",
        ))
    report.pages = pages
    return report

router = APIRouter()
ALLOWED_MEDIA = {"image/png", "image/jpeg"}

@router.get("/heuristics")
async def get_heuristics():
    return HEURISTICS

@router.get("/provider")
async def get_provider():
    return describe_model()

@router.post("/audits/screenshot", response_model=AuditReport)
async def audit_screenshot(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_MEDIA:
        raise HTTPException(415, "Upload a PNG or JPEG image.")
    limit = int(os.getenv("MAX_UPLOAD_MB", "8")) * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(413, f"Image exceeds {limit // (1024 * 1024)} MB limit.")
    try:
        with Image.open(BytesIO(raw)) as image:
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            if image.width > 12000 or image.height > 12000 or image.width * image.height > 40_000_000:
                raise HTTPException(413, "Image dimensions are too large.")
            image_format = image.format
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "The uploaded file is not a valid image.")
    media_type = "image/png" if image_format == "PNG" else "image/jpeg"
    try:
        report = AuditAgent().audit(raw, media_type, "screenshot", "Uploaded screenshot", "unknown", None, None)
        return _attach_pages(report, [{"image": raw, "media_type": media_type, "url": "Uploaded screenshot", "title": file.filename}])
    except ModelConfigError as exc:
        raise HTTPException(503, str(exc))
    except ModelRequestError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Audit provider failed or returned invalid output: {type(exc).__name__}")

@router.post("/audits/url", response_model=AuditReport)
async def audit_url(request: UrlAuditRequest):
    url = str(request.url)
    try:
        captured = await capture_website(url, request.viewport)
        report = AuditAgent().audit(
            captured["image"], "image/png", "url", captured["final_url"],
            request.viewport, captured.get("page_title"), captured.get("page_evidence"),
            images=captured.get("images"),
        )
        meta = (captured.get("page_evidence") or {}).get("pages") or []
        shots = []
        for index, image in enumerate(captured.get("images") or [captured["image"]]):
            page = meta[index] if index < len(meta) else {}
            shots.append({"image": image, "url": page.get("url") or captured.get("final_url"), "title": page.get("title")})
        return _attach_pages(report, shots)
    except UnsafeUrlError as exc:
        raise HTTPException(400, str(exc))
    except BrowserCaptureError as exc:
        raise HTTPException(502, str(exc))
    except ModelConfigError as exc:
        raise HTTPException(503, str(exc))
    except ModelRequestError as exc:
        raise HTTPException(502, str(exc))
    except HTTPException:
        raise
    except ValidationError:
        raise HTTPException(502, "The model returned a report that could not be read. Run the audit again.")
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"URL audit failed: {type(exc).__name__}")
