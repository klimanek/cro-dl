from dataclasses import dataclass
from typing import Optional


@dataclass
class Mp3:
    url: str


@dataclass
class Hls:
    url: str


@dataclass
class Dash:
    url: str


@dataclass
class StreamLinks:
    mp3: Optional[Mp3] = None
    hls: Optional[Hls] = None
    dash: Optional[Dash] = None
