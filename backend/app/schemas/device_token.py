from pydantic import BaseModel, Field


class DeviceTokenRegister(BaseModel):
    token: str = Field(min_length=1, max_length=4096)
    platform: str = Field(default="android", max_length=32)
