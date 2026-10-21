from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class UrlAuditRequest(BaseModel):
    url: HttpUrl
    viewport: Literal["desktop", "mobile"] = "desktop"
