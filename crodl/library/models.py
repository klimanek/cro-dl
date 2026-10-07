from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Episode(SQLModel, table=True):
    """
    One downloaded audio work kept in the local library.

    Column names mirror the field names of the Czech Radio content API
    (`api.mujrozhlas.cz`): `shortTitle`, `part`, `since`, `description`,
    `audioLinks[].duration`. See WEB_LIBRARY_DESIGN.md for what is verified
    against the API and what is not.
    """

    # UUID from the Czech Radio API - the natural key of a work.
    uuid: str = Field(primary_key=True)
    title: str
    short_title: Optional[str] = None
    part: Optional[int] = None
    author: Optional[str] = None
    description: Optional[str] = None
    duration: Optional[int] = None
    broadcast_at: Optional[datetime] = None
    local_path: str
    image_path: Optional[str] = None
    audio_format: Optional[str] = None
    downloaded_at: datetime = Field(default_factory=datetime.now)
    # Named `meta` on purpose: `metadata` is reserved by SQLAlchemy's declarative
    # base, so the "extra JSON" column from the design cannot use that name.
    meta: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
