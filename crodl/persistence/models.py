from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship


class Station(SQLModel, table=True):
    """Represents a radio station."""
    id: str = Field(primary_key=True)
    title: str


class Show(SQLModel, table=True):
    """Represents a program show (e.g., Radiokniha)."""
    id: str = Field(primary_key=True)
    title: str
    description: Optional[str] = None
    
    episodes: List["Episode"] = Relationship(back_populates="show")


class Series(SQLModel, table=True):
    """Represents a series (for multi-part programs)."""
    id: str = Field(primary_key=True)
    title: str
    description: Optional[str] = None
    
    episodes: List["Episode"] = Relationship(back_populates="series")


class Episode(SQLModel, table=True):
    """Main entity for a downloaded audio file."""
    id: str = Field(primary_key=True)  # uuid from CRo
    title: str
    short_title: Optional[str] = None
    description: Optional[str] = None
    since: Optional[datetime] = None
    duration: Optional[int] = None  # in seconds
    
    # File paths stored as strings for database compatibility
    local_path: str 
    image_path: Optional[str] = None
    
    # Relationships
    show_id: Optional[str] = Field(default=None, foreign_key="show.id")
    show: Optional[Show] = Relationship(back_populates="episodes")
    
    series_id: Optional[str] = Field(default=None, foreign_key="series.id")
    series: Optional[Series] = Relationship(back_populates="episodes")
    
    station_id: Optional[str] = Field(default=None, foreign_key="station.id")
    
    # Metadata
    downloaded_at: datetime = Field(default_factory=datetime.now)
    audio_format: str = "mp3"
