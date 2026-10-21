import pytest
from app.services.browser_capture import PAGE_LIMIT, blocked_page_message, browser_failure_message, internal_page_links, validate_public_url, UnsafeUrlError

def test_blocked_page_is_not_audited():
    assert "403" in blocked_page_message(403, "403 Forbidden")
    assert blocked_page_message(200, "403 Forbidden")
    assert blocked_page_message(200, "SagarAIhub") is None

def test_missing_browser_message():
    message = browser_failure_message(RuntimeError("BrowserType.launch: Executable doesn't exist at /tmp/chrome\nPlease run playwright install"))
    assert message.startswith("URL capture needs Chromium.")

def test_rejects_file_scheme():
    with pytest.raises(UnsafeUrlError):
        validate_public_url("file:///etc/passwd")

def test_rejects_localhost():
    with pytest.raises(UnsafeUrlError):
        validate_public_url("http://localhost:8000")

def test_internal_links_stay_on_the_same_site():
    links = [
        {"href": "/about"},
        {"href": "https://sagaraihub.com/services"},
        {"href": "https://www.sagaraihub.com/services"},
        {"href": "https://example.com/other"},
        {"href": "mailto:hello@sagaraihub.com"},
        {"href": "/guide.pdf"},
        {"href": "#pricing"},
    ]
    pages = internal_page_links("https://sagaraihub.com/", links)
    assert pages == ["https://sagaraihub.com/about", "https://sagaraihub.com/services"]
    assert PAGE_LIMIT == 3

def test_rejects_credentials():
    with pytest.raises(UnsafeUrlError):
        validate_public_url("https://user:pass@example.com")
