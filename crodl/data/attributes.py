from dataclasses import dataclass, field

from crodl.settings import API_SERVER
from crodl.tools.scrap import cro_session, get_audio_link_of_preferred_format


@dataclass
class Attributes:
    title: str
    active: bool
    aired: bool
    description: str
    short_description: str


@dataclass
class Data:
    type: str
    uuid: str
    attributes: Attributes


# TODO: Episode class
# TODO: Support more attrs.


@dataclass
class Episodes:
    show_id: str
    count: int = field(init=False)
    data: list[dict] = field(init=False)

    def __post_init__(self):
        episodes_url = f"{API_SERVER}/shows/{self.show_id}/episodes"

        response = cro_session.get(episodes_url)
        response.raise_for_status()
        json_data = response.json()

        self.data = json_data["data"]
        self.count = json_data["meta"]["count"]

    @property
    def info(self) -> list[str]:
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
