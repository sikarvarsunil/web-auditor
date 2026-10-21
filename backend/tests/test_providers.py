import json
from pathlib import Path

import httpx
import pytest

from agent.audit import AuditAgent, parse_report
from agent.model import Model, ModelConfigError, ModelRequestError, describe_model

ROOT = Path(__file__).resolve().parents[2]


def _report():
    return {
        "audit_mode": "screenshot",
        "source": "model-source",
        "page_title": "From the model",
        "viewport": "model-viewport",
        "summary": "The captured page was reviewed against ten heuristics.",
        "findings": [
            {
                "heuristic_id": i,
                "heuristic_name": f"Heuristic {i}",
                "status": "not_observed",
                "title": f"Not enough evidence {i}",
                "evidence": [],
                "user_impact": "Impact is unknown from this capture.",
                "severity": "not_observed",
                "confidence": 0.2,
                "recommendation": "Collect another state before changing this area.",
                "limitations": ["Only one screenshot was available."],
            }
            for i in range(1, 11)
        ],
        "methodology_note": "Static evidence only.",
        "model": "should-be-replaced",
    }


def test_agent_loads_claude_instructions():
    text = AuditAgent(model=Model(provider="ollama", model="llava"), root=ROOT).instructions()
    assert "untrusted evidence" in text
    assert "Evaluate every heuristic" in text
    assert "name: heuristic-audit" not in text


def test_parse_keeps_server_source_and_requires_ten_ids():
    raw = "Here is the audit:\n```json\n" + json.dumps(_report()) + "\n```"
    report = parse_report(raw, model="ollama:llava", mode="url", source="https://example.com", viewport="mobile", page_title="Example")
    assert report.model == "ollama:llava"
    assert report.audit_mode == "url"
    assert report.source == "https://example.com"
    assert report.viewport == "mobile"
    assert [finding.heuristic_id for finding in report.findings] == list(range(1, 11))


def test_parse_accepts_string_evidence_and_fills_a_missing_heuristic():
    payload = _report()
    payload["findings"] = payload["findings"][:9]
    payload["findings"][0]["evidence"] = "The header shows two competing calls to action."
    payload["findings"][0]["limitations"] = "Only the desktop screenshot was available."
    report = parse_report(json.dumps(payload), model="ollama:gemma3:4b", mode="url", source="https://sagaraihub.com/", viewport="desktop", page_title="SagarAIhub")
    assert len(report.findings) == 10
    assert report.findings[0].evidence[0].type == "screenshot"
    assert report.findings[0].evidence[0].description.startswith("The header")
    assert report.findings[0].limitations == ["Only the desktop screenshot was available."]
    assert report.findings[9].heuristic_id == 10
    assert report.findings[9].status == "not_observed"


def test_parse_repairs_status_and_evidence_type():
    payload = _report()
    payload["findings"][0]["status"] = "high"
    payload["findings"][0]["evidence"] = [{"type": "DOM", "description": "The header navigation is visible."}]
    report = parse_report(json.dumps(payload), model="m", mode="url", source="https://sagaraihub.com/", viewport="desktop", page_title="SagarAIhub")
    assert report.findings[0].status == "finding"
    assert report.findings[0].evidence[0].type == "dom"


def test_parse_ignores_model_supplied_screenshots():
    payload = _report()
    payload["pages"] = [{"url": "https://example.com", "image": "data:image/png;base64,aaaa"}]
    report = parse_report(json.dumps(payload), model="m", mode="screenshot", source="Uploaded screenshot", viewport="unknown", page_title=None)
    assert report.pages == []


def test_parse_rejects_a_report_with_no_findings():
    raw = json.dumps({"page_title": "403 Forbidden", "model": "ollama:gemma3:4b"})
    with pytest.raises(ValueError, match="did not return an audit"):
        parse_report(raw, model="ollama:gemma3:4b", mode="url", source="https://example.com/", viewport="desktop", page_title="403 Forbidden")


def test_parse_repairs_pretty_printed_truncated_json():
    raw = json.dumps(_report(), indent=2)
    broken = raw[:raw.rfind("}")]
    report = parse_report(broken, model="m", mode="url", source="https://sagaraihub.com/", viewport="desktop", page_title="SagarAIhub")
    assert len(report.findings) == 10
    assert report.findings[0].title != "Not assessed"


def test_parse_repairs_a_truncated_findings_list():
    raw = json.dumps(_report())
    separator = raw.rfind("}, {")
    broken = raw[:separator + 40]
    report = parse_report(broken, model="m", mode="url", source="https://sagaraihub.com/", viewport="desktop", page_title="SagarAIhub")
    assert len(report.findings) == 10
    assert report.findings[9].status == "not_observed"


def test_parse_drops_duplicate_heuristic_id():
    payload = _report()
    payload["findings"][1]["heuristic_id"] = 1
    payload["findings"][1]["title"] = "Duplicate finding title"
    report = parse_report(json.dumps(payload), model="m", mode="screenshot", source="s", viewport="desktop", page_title=None)
    assert [finding.heuristic_id for finding in report.findings] == list(range(1, 11))
    assert report.findings[1].title == "Not assessed"
    assert report.findings[0].title != "Duplicate finding title"


def test_model_reads_provider_from_env(monkeypatch):
    monkeypatch.setenv("AUDIT_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5vl")
    model = Model()
    assert model.name == "ollama"
    assert model.model == "qwen2.5vl"


def test_model_accepts_a_direct_api_key():
    model = Model(provider="anthropic", model="claude-test", api_key="test-key")
    assert model.api_key == "test-key"
    assert model.id() == "claude-test"


def test_describe_model_reports_missing_ollama_model(monkeypatch):
    monkeypatch.setenv("AUDIT_PROVIDER", "ollama")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    info = describe_model()
    assert info["ready"] is False
    assert "OLLAMA_MODEL" in info["detail"]


def test_unknown_provider_is_rejected():
    with pytest.raises(ModelConfigError):
        Model(provider="mystery", model="x")


def test_ollama_sends_image_and_parses_report():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps(_report())}})

    model = Model(provider="ollama", model="llava", client=httpx.Client(transport=httpx.MockTransport(handler)))
    report = AuditAgent(model=model, root=ROOT).audit(b"png-bytes", "image/png", "screenshot", "Uploaded screenshot", "unknown", None, None)
    assert seen["body"]["model"] == "llava"
    assert seen["body"]["format"]["required"] == ["summary", "findings", "methodology_note"]
    assert seen["body"]["messages"][1]["images"]
    assert "Evaluate every heuristic" in seen["body"]["messages"][0]["content"]
    assert report.model == "ollama:llava"
    assert report.source == "Uploaded screenshot"


def test_ollama_sends_at_most_three_page_images():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "{}"}})

    model = Model(provider="ollama", model="gemma3:4b", client=httpx.Client(transport=httpx.MockTransport(handler)))
    model.complete("system", "user", b"a", "image/png", images=[b"a", b"b", b"c", b"d"])
    assert len(seen["body"]["messages"][1]["images"]) == 3


def test_ollama_retries_after_a_server_error():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, json={"error": "model runner has unexpectedly stopped"})
        return httpx.Response(200, json={"message": {"content": json.dumps(_report())}})

    model = Model(provider="ollama", model="gemma3:4b", client=httpx.Client(transport=httpx.MockTransport(handler)))
    report = model.complete("system", "user", b"not-an-image", "image/png")
    assert calls["count"] == 2
    assert "gemma3:4b" in report or report.startswith("{")


def test_ollama_reports_missing_model():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    model = Model(provider="ollama", model="missing-model", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ModelRequestError, match="ollama pull missing-model"):
        model.complete("system", "user", b"png", "image/png")


def test_openai_compatible_sends_data_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(_report())}}]})

    model = Model(provider="openai", model="llama3.2-vision", api_key="local", base_url="http://localhost:11434/v1", client=httpx.Client(transport=httpx.MockTransport(handler)))
    report = AuditAgent(model=model, root=ROOT).audit(b"abc", "image/jpeg", "url", "https://example.com", "desktop", "Example", {"title": "Example"})
    content = seen["body"]["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert seen["auth"] == "Bearer local"
    assert report.model == "openai:llama3.2-vision"
    assert report.audit_mode == "url"
