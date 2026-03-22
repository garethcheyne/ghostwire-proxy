from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class SettingUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None


class SettingResponse(BaseModel):
    key: str
    value: Optional[str]
    description: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True


class SettingsBulkUpdate(BaseModel):
    settings: dict[str, str]  # {"key": "value", ...}
