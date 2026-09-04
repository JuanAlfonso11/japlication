from typing import Optional

from pydantic import BaseModel


class AndroidUpdateInfo(BaseModel):
    """None fields mean "no update tracked" — the frontend just doesn't
    show the update banner rather than treating it as an error."""

    version_code: Optional[int] = None
    version_name: Optional[str] = None
    apk_url: Optional[str] = None
    notes: Optional[str] = None
