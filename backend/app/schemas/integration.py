from pydantic import BaseModel


class UpworkStatus(BaseModel):
    connected: bool
    configured: bool


class UpworkAuthorizeResponse(BaseModel):
    authorization_url: str
