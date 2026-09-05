from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HeartbeatRequest(BaseModel):
    job_name: str
    status: str = "ok"
    detail: Optional[str] = None


class HeartbeatInfo(BaseModel):
    model_config = {"from_attributes": True}

    job_name: str
    last_run_at: datetime
    last_status: str
    detail: Optional[str] = None
