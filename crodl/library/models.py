"""SQLModel tables of the local library.

Column names mirror the field names of the Czech Radio content API
(`api.mujrozhlas.cz`): `shortTitle`, `part`, `since`, `description`,
`audioLinks[].duration`. See WEB_LIBRARY_DESIGN.md §7 for what is verified
against the API and what still needs modelling.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel


class Station(SQLModel, table=True):
    """A Czech Radio station (the broadcaster that aired a work)."""

    # Text identifier of the station.
    id: str = Field(primary_key=True)
    title: str

    episodes: List["Episode"] = Relationship(back_populates="station")


class Show(SQLModel, table=True):
    """A programme (show) that episodes belong to."""

    # UUID from the content API - the natural key (see design doc §7).
    uuid: str = Field(primary_key=True)
    title: str
    description: Optional[str] = None
    #: The genre of the whole work ("Pohádka", "Horor", ...), used for its tags.
    genre: Optional[str] = None

    episodes: List["Episode"] = Relationship(back_populates="show")


class Series(SQLModel, table=True):
    """A series a multi-part programme belongs to."""

    uuid: str = Field(primary_key=True)
    title: str
    description: Optional[str] = None
    #: The genre of the whole work ("Pohádka", "Horor", ...), used for its tags.
    genre: Optional[str] = None

    episodes: List["Episode"] = Relationship(back_populates="series")


class UpdateCheck(SQLModel, table=True):
    """
    What the last look for new parts found, by the state of the missing parts.

    Kept in the database so a badge survives a page or a restart. A part the
    library lacks is not necessarily news: the Czech Radio takes its streams
    down again after a while, and it announces parts before airing them - hence
    three counts rather than one.
    """

    # The work in the content API: a series' or a show's uuid.
    collection_id: str = Field(primary_key=True)
    collection_type: str
    checked_at: datetime = Field(default_factory=datetime.now)
    #: Parts that aired and are still streamable - worth fetching now.
    available: int = 0
    #: Parts the API announces but has not aired yet.
    upcoming: int = 0
    #: Parts whose streams have expired; they can no longer be fetched.
    expired: int = 0


class WorkLink(SQLModel, table=True):
    """
    The mujrozhlas.cz page a work came from, when a person supplied it.

    A work adopted from disk is keyed by a hash of its folder, so it has no
    Czech Radio identity of its own; the link (and the uuid it resolves to) is
    what lets the API be asked about it - it stays a *source*, not a new key.
    """

    # The work in the library (a series' or a show's key, hash or uuid).
    collection_id: str = Field(primary_key=True)
    collection_type: str
    source_url: str
    #: The uuid the page resolved to, remembered so it is looked up once.
    resolved_uuid: Optional[str] = None
    added_at: datetime = Field(default_factory=datetime.now)


class Episode(SQLModel, table=True):
    """One downloaded audio work kept in the local library."""

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
    # Set for files that were imported from disk rather than downloaded.
    is_manual: bool = False
    source_url: Optional[str] = None
    # Named `meta` on purpose: `metadata` is reserved by SQLAlchemy's declarative
    # base, so the "extra JSON" column from the design cannot use that name.
    meta: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    station_id: Optional[str] = Field(default=None, foreign_key="station.id")
    show_id: Optional[str] = Field(default=None, foreign_key="show.uuid")
    series_id: Optional[str] = Field(default=None, foreign_key="series.uuid")

    station: Optional[Station] = Relationship(back_populates="episodes")
    show: Optional[Show] = Relationship(back_populates="episodes")
    series: Optional[Series] = Relationship(back_populates="episodes")
