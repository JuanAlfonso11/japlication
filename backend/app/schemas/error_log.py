from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClientErrorReport(BaseModel):
    """What the frontend sends when something breaks in the browser/WebView.

    Every field is length-capped: this endpoint is reachable by anything the
    app runs on, and an uncapped `stack` is a free way to fill the disk.
    """

    message: str = Field(min_length=1, max_length=2000)
    kind: Optional[str] = Field(default=None, max_length=200)
    stack: Optional[str] = Field(default=None, max_length=12000)
    #: Where in the app it happened. Path only — see the note in
    #: db/schema.sql about not logging query strings.
    url: Optional[str] = Field(default=None, max_length=1000)


class ErrorLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: str
    source: str
    level: str
    kind: Optional[str] = None
    message: str
    stack: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    user_agent: Optional[str] = None
    url: Optional[str] = None
    created_at: datetime
