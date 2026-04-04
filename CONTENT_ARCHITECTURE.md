# Architektura obsahu: Jednotka vs. Kolekce

Tento dokument vysvětluje filozofii rozdělení tříd v projektu `cro-dl` a reaguje na specifický rozdíl mezi `AudioWork` a entitami `Series` / `Show`.

## Motivace rozdělení (Proč AudioWork není jako ostatní)

Při analýze kódu je patrné, že `AudioWork` hraje v systému jinou roli než `Series` nebo `Show`. Zatímco bázová třída `Content` (tak, jak je aktuálně navržena pro `Series` a `Show`) slouží primárně jako datový deskriptor API zdroje, `AudioWork` je **orchestrátor stahování**.

### 1. Rozdílná podstata (Entity vs. Worker)
- **Series / Show (Kontejnery):** Jsou to v podstatě "mapy" k dalším zdrojům. Jejich hlavní zodpovědností je stránkování v API a agregace seznamu epizod. Nemají přímý vztah k audio streamu.
- **AudioWork (Výkonný prvek):** Je to koncový bod (leaf). Musí znát detaily o bitrate, formátech (MP3 vs. HLS vs. DASH) a nese v sobě stav stahování konkrétního souboru.

### 2. Komplexita inicializace
`AudioWork` vyžaduje mnohem dynamičtější inicializaci (často se vytváří v cyklu uvnitř `Series`), kde se mu předávají parametry jako `audiowork_dir`, `since` nebo prefixy názvů souborů. Použití striktní `dataclass` by zde mohlo vést k přílišné rigiditě, pokud by se musely všechny tyto parametry definovat předem.

---

## Návrh řešení: Diferenciace rozhraní

Abychom zachovali tvůj záměr "rozdílné podstaty" a přitom kód vyčistili, navrhuji zavést dvě specializovaná rozhraní (nebo abstrakce):

### A. Pattern "Unit vs. Collection"
Místo jedné obecné třídy `Content` rozdělit abstrakci na:
1.  **`DownloadableUnit` (pro AudioWork):** Rozhraní zaměřené na streamy, kvalitu a IO operace.
2.  **`ContentCollection` (pro Series/Show):** Rozhraní zaměřené na iteraci, metadata kolekce a vztahy k epizodám.

### B. Kompozice místo dědičnosti
Místo aby `AudioWork` *byl* obsahem (`is-a`), mohl by *obsahovat* data (`has-a`).
- `AudioWork` by byla čistá třída (Worker), která dostane do konstruktoru objekt `EpisodeMetadata` (který by byl `dataclass`).
- Tím se oddělí "to, co stahujeme" (data) od "toho, jak to stahujeme" (logika).

### C. Využití Protocol (Duck Typing)
Pokud chceme, aby CLI/GUI mohlo s oběma typy pracovat jednotně (např. zavolat `.download()`), je ideální použít `Protocol`. 
- `Series` implementuje `download()` jako "stáhni všechny mé členy".
- `AudioWork` implementuje `download()` jako "stáhni tento konkrétní stream".
Navenek se chovají stejně, ale uvnitř zůstávají zcela odlišné.

## Závěr
Současný stav, kdy `AudioWork` stojí "mimo" hlavní hierarchii, je z pohledu doménového modelu správný, protože jeho zodpovědnost je fundamentálně odlišná. Navržené změny by měly směřovat pouze k **vyčištění konstruktoru** (odstranění `kwargs.pop`) a **jasnějšímu definování rozhraní**, nikoliv k násilnému sjednocení pod jednu bázovou třídu.
