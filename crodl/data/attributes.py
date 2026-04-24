from dataclasses import dataclass, field
from typing import Dict, Any

from crodl.tools.scrap import get_audio_link_of_preferred_format


@dataclass
class Attributes:
    title: str
    active: bool
    aired: bool
    description: str
    short_description: str


@dataclass
class Data:
    show_type: str
    uuid: str
    attributes: Attributes


@dataclass
class Episodes:
    show_title: str
    show_id: str
    json_data: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        if not self.json_data:
            # We should probably not fetch here, but to maintain compatibility
            # we might need to. However, we want to remove this.
            # For now, let's just use what's passed.
            self.data = []
            self.count = 0
            return

        self.data = self.json_data.get("data", [])
        self.count = self.json_data.get("meta", {}).get("count", 0)

    @property
    def info(self) -> list[dict]:
        info = []
        for _data in self.data:
            attrs = _data["attributes"]
            info.append(
                {
                    "uuid": _data["id"],
                    "title": attrs["title"],
                    "url": get_audio_link_of_preferred_format(attrs),
                    "since": attrs["since"],
                    "part": attrs["part"],
                }
            )

        return info

    # @property
    # def df(self) -> pds.DataFrame | str:
    #     dframe = pds.DataFrame(self.info)
    #     dframe = dframe.sort_values(
    #         ['since'],
    #         ascending=[
    #             False,
    #         ],
    #     )
    #     dframe = dframe.drop(['uuid', 'url'], axis=1).reset_index(drop=True)
    #     dframe.rename(columns={'title': 'Titul', 'since': 'Vysíláno', 'part': 'Díl'}, inplace=True)

    #     # Nahrazení NaN hodnot nulou
    #     dframe['Díl'] = dframe['Díl'].fillna(0)

    #     # Převod sloupce na integer
    #     dframe['Díl'] = dframe['Díl'].astype(int)
    #     # dframe = dframe[["Díl", "Titul", "Vysíláno"]]

    #     dframe = dframe.to_string(index=False)
    #     return dframe

    def __str__(self):
        return f"<Episodes of {self.show_title}>"

    def __repr__(self):
        return f"<Episodes of {self.show_title}>"
