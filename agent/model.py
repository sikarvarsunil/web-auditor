import base64
import os
from io import BytesIO

import httpx
from anthropic import Anthropic
from PIL import Image, UnidentifiedImageError

class ModelConfigError(RuntimeError):
    """Provider, model name, API key, or base URL is missing."""


class ModelRequestError(RuntimeError):
    """The configured model could not complete the request."""


# Unconstrained JSON mode lets small models answer with {}. A schema requires the audit fields.
_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "methodology_note": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heuristic_id": {"type": "integer"},
                    "heuristic_name": {"type": "string"},
                    "status": {"type": "string"},
                    "title": {"type": "string"},
                    "severity": {"type": "string"},
                    "confidence": {"type": "number"},
                    "user_impact": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "location": {"type": "string"},
                            },
                            "required": ["description"],
                        },
                    },
                    "limitations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heuristic_id", "title", "status", "severity"],
            },
        },
    },
    "required": ["summary", "findings", "methodology_note"],
}


class Model:
    """Swap the provider, model name, API key, or base URL without changing the agent."""

    def __init__(self, provider=None, model=None, api_key=None, base_url=None, client: httpx.Client | None = None):
        self.provider = (provider or os.getenv("AUDIT_PROVIDER", "anthropic")).strip().lower() or "anthropic"
        self.model = (model if model is not None else _env_model(self.provider)).strip()
        self.api_key = _env_key(self.provider) if api_key is None else api_key
        self.base_url = (base_url if base_url is not None else _env_base(self.provider)).rstrip("/")
        self.timeout = float(os.getenv("MODEL_TIMEOUT_SECONDS") or os.getenv("OLLAMA_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS") or "180")
        self.max_tokens = int(os.getenv("MODEL_MAX_TOKENS") or os.getenv("OLLAMA_NUM_PREDICT") or os.getenv("OPENAI_MAX_TOKENS") or "6500")
        self._client = client
        self._check()

    @property
    def name(self) -> str:
        if self.provider in {"anthropic", "claude"}:
            return "anthropic"
        if self.provider == "ollama":
            return "ollama"
        return "openai"

    def label(self) -> str:
        titles = {"anthropic": "Claude", "ollama": "Ollama", "openai": "OpenAI-compatible"}
        return f"{titles[self.name]} · {self.model}"

    def id(self) -> str:
        return self.model if self.name == "anthropic" else f"{self.name}:{self.model}"

    def complete(self, system: str, user: str, image: bytes, media_type: str, images: list[bytes] | None = None) -> str:
        fitted = [_fit_image(item, media_type) for item in (images or [image])[:3]]
        if self.name == "anthropic":
            return self._anthropic(system, user, fitted)
        if self.name == "ollama":
            return self._ollama(system, user, fitted)
        return self._openai(system, user, fitted)

    def _check(self):
        if self.provider in {"anthropic", "claude"}:
            if not self.api_key:
                raise ModelConfigError("Set ANTHROPIC_API_KEY, or pass api_key to Model.")
            self.model = self.model or "claude-sonnet-4-20250514"
        elif self.provider == "ollama":
            if not self.model:
                raise ModelConfigError("Set OLLAMA_MODEL, or pass model to Model.")
            self.base_url = self.base_url or "http://127.0.0.1:11434"
        elif self.provider in {"openai", "openai_compatible"}:
            if not self.base_url or not self.model:
                raise ModelConfigError("Set OPENAI_BASE_URL and OPENAI_MODEL, or pass base_url and model to Model.")
            self.api_key = self.api_key or "not-required"
        else:
            raise ModelConfigError("AUDIT_PROVIDER must be anthropic, ollama, or openai.")

    def _anthropic(self, system, user, images: list[tuple[bytes, str]]) -> str:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(image).decode("ascii")}}
            for image, media_type in images
        ]
        content.append({"type": "text", "text": user})
        response = Anthropic(api_key=self.api_key).messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = "\n".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
        if not text:
            raise ModelRequestError("Claude returned an empty response.")
        return text

    def _ollama(self, system, user, images: list[tuple[bytes, str]]) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "format": _AUDIT_SCHEMA,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user, "images": [base64.b64encode(image).decode("ascii") for image, _media in images]},
            ],
            "options": {"temperature": 0.2, "num_predict": min(self.max_tokens, 4096), "num_ctx": 8192},
        }
        response = self._post(f"{self.base_url}/api/chat", payload)
        if response.status_code >= 500:
            response = self._post(f"{self.base_url}/api/chat", payload)
        if response.status_code == 404:
            raise ModelRequestError(f"Ollama model '{self.model}' was not found. Pull it with: ollama pull {self.model}")
        self._raise_for_status(response)
        content = (_json(response).get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ModelRequestError(f"Ollama model '{self.model}' returned an empty response.")
        return content

    def _openai(self, system, user, images: list[tuple[bytes, str]]) -> str:
        content = [{"type": "text", "text": user}]
        content.extend(
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{base64.b64encode(image).decode('ascii')}"}}
            for image, media_type in images
        )
        response = self._post(
            f"{self.base_url}/chat/completions",
            {
                "model": self.model,
                "temperature": 0.2,
                "max_tokens": self.max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
            },
            {"Authorization": f"Bearer {self.api_key}"},
        )
        self._raise_for_status(response)
        try:
            content = _json(response)["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelRequestError(f"Model '{self.model}' returned an unexpected response.") from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelRequestError(f"Model '{self.model}' returned an empty response.")
        return content

    def _post(self, url, payload, headers=None) -> httpx.Response:
        try:
            if self._client is not None:
                return self._client.post(url, json=payload, headers=headers)
            with httpx.Client(timeout=self.timeout) as client:
                return client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ModelRequestError(f"Could not reach the model server at {self.base_url}.") from exc

    def _raise_for_status(self, response: httpx.Response):
        if response.status_code < 400:
            return
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict) and body.get("error"):
                detail = " " + str(body["error"]).strip().splitlines()[0][:300]
        except ValueError:
            detail = ""
        raise ModelRequestError(f"The model server returned HTTP {response.status_code} for '{self.model}'.{detail}")


def _fit_image(image: bytes, media_type: str) -> tuple[bytes, str]:
    """Keep screenshots inside the size local vision models can accept."""
    try:
        with Image.open(BytesIO(image)) as opened:
            opened = opened.convert("RGB")
            opened.thumbnail((1280, 1280))
            output = BytesIO()
            opened.save(output, format="JPEG", quality=80)
    except (UnidentifiedImageError, OSError):
        return image, media_type
    return output.getvalue(), "image/jpeg"


def describe_model() -> dict:
    provider = os.getenv("AUDIT_PROVIDER", "anthropic").strip().lower() or "anthropic"
    try:
        model = Model()
    except ModelConfigError as exc:
        return {"provider": provider, "model": None, "label": provider, "ready": False, "detail": str(exc)}
    return {"provider": model.name, "model": model.model, "label": model.label(), "ready": True, "detail": None}


def _env_model(provider: str) -> str:
    if provider in {"anthropic", "claude"}:
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL", "")
    if provider in {"openai", "openai_compatible"}:
        return os.getenv("OPENAI_MODEL", "")
    return ""


def _env_key(provider: str) -> str:
    if provider in {"anthropic", "claude"}:
        return os.getenv("ANTHROPIC_API_KEY", "")
    if provider in {"openai", "openai_compatible"}:
        return os.getenv("OPENAI_API_KEY", "")
    return ""


def _env_base(provider: str) -> str:
    if provider == "ollama":
        return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    if provider in {"openai", "openai_compatible"}:
        return os.getenv("OPENAI_BASE_URL", "")
    return ""


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise ModelRequestError("The model server returned a response that was not JSON.") from exc
    if not isinstance(body, dict):
        raise ModelRequestError("The model server returned a response that was not a JSON object.")
    return body
