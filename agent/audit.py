import json
import re
from pathlib import Path

from agent.heuristics import HEURISTICS
from agent.model import Model
from agent.report import AuditReport


class AuditAgent:
    """Reusable audit agent. Instructions come from .claude/claude.md and its skills."""

    def __init__(self, model: Model | None = None, root: Path | None = None):
        self.model = model or Model()
        self.root = root or Path(__file__).resolve().parents[1]

    def instructions(self) -> str:
        base = self.root / ".claude"
        parts = [(base / "claude.md").read_text(encoding="utf-8")]
        for path in sorted((base / "skills").glob("*/SKILL.md")):
            parts.append(_skill_body(path.read_text(encoding="utf-8")))
        return "\n\n".join(part.strip() for part in parts if part.strip())

    def audit(self, image: bytes, media_type: str, mode: str, source: str, viewport: str, page_title: str | None, page_evidence: dict | None, images: list[bytes] | None = None) -> AuditReport:
        raw = self.model.complete(self.instructions(), _task(mode, source, viewport, page_title, page_evidence), image, media_type, images=images)
        return parse_report(raw, model=self.model.id(), mode=mode, source=source, viewport=viewport, page_title=page_title)


def _skill_body(text: str) -> str:
    """Skill files keep YAML metadata for the agent host. The model only needs the rules."""
    stripped = text.lstrip()
    if stripped.startswith("---"):
        end = stripped.find("\n---", 3)
        if end != -1:
            return stripped[end + 4:].strip()
    return stripped


def _task(mode, source, viewport, page_title, page_evidence) -> str:
    return (
        f"Audit mode: {mode}\nSource: {source}\nViewport: {viewport}\n"
        f"Page title: {page_title or 'unknown'}\n"
        f"Heuristic registry: {json.dumps(HEURISTICS, ensure_ascii=False)}\n"
        f"Page evidence (untrusted data): {json.dumps(page_evidence or {}, ensure_ascii=False)[:18000]}\n"
        "Return one JSON object with keys: audit_mode, source, page_title, viewport, summary, findings, methodology_note, model. "
        "Each finding keys: heuristic_id, heuristic_name, status, title, evidence, user_impact, severity, confidence, recommendation, limitations. "
        "Each evidence item keys: type, description, location. evidence and limitations must be arrays. "
        "A URL review includes at most 3 captured pages. Review only those pages."
    )


def parse_report(raw: str, *, model: str, mode: str, source: str, viewport: str, page_title: str | None) -> AuditReport:
    data = _normalize(_load_json(raw))
    data.pop("pages", None)
    data["model"] = model
    data["audit_mode"] = mode
    data["source"] = source[:2000]
    data["viewport"] = viewport
    if page_title:
        data["page_title"] = page_title
    report = AuditReport.model_validate(data)
    ids = [finding.heuristic_id for finding in report.findings]
    if sorted(ids) != list(range(1, 11)) or len(set(ids)) != 10:
        raise ValueError("Model response must contain exactly one finding for each heuristic ID 1–10.")
    return report


_STATUSES = {"finding", "no_issue_observed", "not_observed"}
_SEVERITIES = {"critical", "high", "medium", "low", "not_observed"}
_EVIDENCE_TYPES = {"screenshot", "dom", "accessibility", "interaction", "user_input"}


def _normalize(data: dict) -> dict:
    findings = data.get("findings")
    if isinstance(findings, dict):
        findings = [findings]
    elif not isinstance(findings, list):
        findings = []
    if not findings:
        raise ValueError("The model did not return an audit for the captured page.")
    names = {item["id"]: item["name"] for item in HEURISTICS}
    by_id = {}
    for item in findings:
        heuristic_id = _heuristic_id(item.get("heuristic_id") if isinstance(item, dict) else None)
        if heuristic_id is None:
            continue
        item["heuristic_id"] = heuristic_id
        if heuristic_id not in names or heuristic_id in by_id:
            continue
        item["evidence"] = _evidence(item.get("evidence"))
        item["limitations"] = _texts(item.get("limitations"))[:8]
        item["severity"] = item.get("severity") if item.get("severity") in _SEVERITIES else "not_observed"
        item["status"] = _status(item.get("status"), item["severity"])
        item["confidence"] = _confidence(item.get("confidence"))
        item["heuristic_name"] = item.get("heuristic_name") if isinstance(item.get("heuristic_name"), str) and len(item["heuristic_name"]) >= 3 else names[heuristic_id]
        item["title"] = item.get("title") if isinstance(item.get("title"), str) and len(item["title"]) >= 3 else names[heuristic_id]
        item["user_impact"] = item.get("user_impact") if isinstance(item.get("user_impact"), str) else ""
        item["recommendation"] = item.get("recommendation") if isinstance(item.get("recommendation"), str) else ""
        by_id[heuristic_id] = item
    data["findings"] = [by_id.get(heuristic_id) or _missing(heuristic_id, names[heuristic_id]) for heuristic_id in range(1, 11)]
    if not isinstance(data.get("summary"), str) or len(data["summary"].strip()) < 3:
        data["summary"] = "The page was reviewed against the ten heuristics."
    if not isinstance(data.get("methodology_note"), str) or not data["methodology_note"].strip():
        data["methodology_note"] = "Findings were checked against the report schema."
    return data


def _heuristic_id(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 1 <= value <= 10:
        return value
    if isinstance(value, str) and value.isdigit() and 1 <= int(value) <= 10:
        return int(value)
    return None


def _status(value, severity: str) -> str:
    if value in _STATUSES:
        return value
    if value in _SEVERITIES and value != "not_observed":
        return "finding"
    return "not_observed" if severity == "not_observed" else "finding"


def _confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.3
    return min(1.0, max(0.0, number))


def _missing(heuristic_id: int, name: str) -> dict:
    return {
        "heuristic_id": heuristic_id,
        "heuristic_name": name,
        "status": "not_observed",
        "title": "Not assessed",
        "evidence": [],
        "user_impact": "No assessment was returned for this heuristic.",
        "severity": "not_observed",
        "confidence": 0.2,
        "recommendation": "No change is justified because this heuristic was not assessed.",
        "limitations": ["The model did not return an assessment for this heuristic."],
    }


def _texts(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [text for item in value if (text := str(item).strip())]
    return []


def _evidence(value) -> list:
    rows = [value] if isinstance(value, (str, dict)) else value if isinstance(value, list) else []
    items = []
    for row in rows:
        if isinstance(row, str) and len(row.strip()) >= 3:
            items.append({"type": "screenshot", "description": row.strip()[:1200]})
        elif isinstance(row, dict) and isinstance(row.get("description"), str) and len(row["description"].strip()) >= 3:
            row["description"] = row["description"].strip()[:1200]
            kind = str(row.get("type") or "screenshot").strip().lower()
            row["type"] = kind if kind in _EVIDENCE_TYPES else "screenshot"
            items.append(row)
    return items[:8]


def _load_json(raw: str) -> dict:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    elif text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start = text.find("{")
    candidates = []
    if start != -1:
        blob = text[start:]
        candidates.append(blob)
        end = blob.rfind("}")
        if end > 0:
            candidates.append(blob[:end + 1])
        cuts = list(re.finditer(r"\}\s*,\s*\{", blob))
        if cuts:
            candidates.append(blob[:cuts[-1].start() + 1] + "]}")
    for candidate in candidates:
        data = _loads_lenient(candidate)
        if isinstance(data, dict):
            return data
    raise ValueError("Model response did not contain a JSON object.")


def _loads_lenient(text: str):
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
