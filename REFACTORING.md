# Návrh refaktoringu projektu cro-dl

Tento dokument shrnuje analýzu stávajícího stavu projektu a navrhuje kroky k modernizaci kódu s důrazem na granularitu, objektově orientovaný přístup (OOP) a čistotu kódu (Clean Code). Analýza vychází zejména z rozpracovaných změn ve větvi `fix/program-classes`.

## Současný stav a záměr změn

Ve větvi `fix/program-classes` byla zahájena transformace z procedurálního/funkcionálního přístupu na více objektový. Mezi hlavní změny patří:
- Zavedení abstraktní bázové třídy `Content` pro sjednocení rozhraní stahovatelného obsahu.
- Využití `dataclasses` pro reprezentaci datových struktur (`Attributes`, `StreamLinks`, `Episodes`).
- Přejmenování nejednoznačných identifikátorů (např. `id` -> `uuid`).
- Snaha o zapouzdření logiky získávání dat z API do specializovaných tříd.

### Zjištěné nedostatky
1. **Nekonzistence:** Třída `AudioWork` (reprezentující jednu epizodu) dosud nedědí z `Content` a nepoužívá `dataclass`, na rozdíl od `Series` a `Show`.
2. **Duplicita logiky:** `Series` a `Show` řeší získávání seznamu epizod odlišným způsobem, i když jde o podobnou funkcionalitu.
3. **Vedlejší účinky v konstruktorech:** Metody `__init__` a `__post_init__` provádějí síťová volání, což ztěžuje testování a může vést k neočekávanému chování.
4. **Závislost na globálním stavu:** Široké využití globálního objektu `cro_session`.
5. **Nepřehledné parametry:** Používání `**kwargs` a `kwargs.pop` v `AudioWork` snižuje čitelnost a typovou bezpečnost.

---

## Návrh refaktoringu

### 1. Sjednocení hierarchie (OOP)
Všechny hlavní entity reprezentující stahovatelný obsah musí dědit z `Content`.

```python
class Content(ABC):
    url: str
    uuid: str
    title: str
    # ... společné vlastnosti
```

- **AudioWork:** Převést na `dataclass` a nechat dědit z `Content`. Odstranit `**kwargs` ve prospěch explicitních polí.
- **Series & Show:** Sjednotit rozhraní pro přístup k epizodám.

### 2. Granularita a separace odpovědnosti
Rozdělit třídy na čistě datové a logické/servisní.

- **Data Modely:** Použít `pydantic` nebo vylepšené `dataclasses` pro validaci dat z API.
- **Scraper/API Client:** Vytvořit dedikovanou třídu/modul pro komunikaci s API, která bude vracet instance datových modelů, namísto provádění síťových volání přímo v modelech.
- **Downloaders:** Streamovací logika (`DASH`, `HLS`, `MP3`) by měla být lépe oddělena od datových modelů programu.

### 3. Konzistentní správa epizod
Vytvořit jednotný mechanismus pro práci s kolekcemi epizod, který budou využívat jak `Series`, tak `Show`. Např. pomocí iterátoru nebo generátoru.

### 4. Dependency Injection
Namísto globálního `cro_session` předávat instanci session (nebo API klienta) do tříd, které ji potřebují. To umožní snadné mockování při testech.

### 5. Lazy Loading
Vlastnosti jako `description` nebo `audio_links` by měly být načítány až v případě potřeby (Lazy loading), aby se zbytečně nezatěžovalo API při pouhém výpisu informací.

---

## Architektura pro více rozhraní (CLI/GUI)

Aby bylo možné projekt využívat nejen jako CLI nástroj, ale v budoucnu i s grafickým rozhraním (GUI), je nutné striktně oddělit "Business Logic" (stahování, parsování) od "Presentation Layer" (terminál, okna).

### 1. Odstranění přímých IO operací z jádra
Třídy `AudioWork`, `Series` a `Show` nesmí obsahovat volání `print()` ani `input()`.
- **Výstup:** Jádro bude používat standardní `logging` a vlastní systém událostí/callbacků (např. přes `blinker` nebo jednoduché asynchronní hooky).
- **Vstup:** Rozhodování (např. "Pokračovat ve stahování? [a/n]") musí probíhat v CLI vrstvě (`main.py`). Jádro dostane pouze příkaz "stahuj".

### 2. Event-Driven Progress
Pro zobrazení postupu stahování v GUI nebo v `rich.progress` v CLI:
- Downloader bude přijímat volitelný callback `on_progress(current, total)`.
- GUI pak tento callback propojí s grafickým Progress Barem, zatímco CLI s animací v terminálu.

### 3. Service Layer (Fasáda)
Vytvoření hlavní třídy (např. `CroDL`), která bude sloužit jako jediný vstupní bod pro externí rozhraní.
```python
dl = CroDL(session=...)
info = await dl.get_info(url)  # Vrátí objekt, neprintuje
await dl.download(info, format="mp3", progress_callback=my_fn)
```

### 4. Asynchronní jádro
Vzhledem k tomu, že GUI aplikace (PyQt/Tkinter) běží v event loopu, musí být jádro plně asynchronní (`async/await`), aby neblokovalo vykreslování oken během síťových operací.

---

## Pokročilé OOP vzory a typová bezpečnost

Pro dosažení maximální čistoty a rozšiřitelnosti jádra navrhujeme využít moderní prvky Pythonu:

### 1. Strukturální typování pomocí `Protocol`
Místo rigidní dědičnosti z `Content` (ABC) definujeme rozhraní pomocí `Protocol`. Jakýkoliv objekt, který má `uuid` a metodu `download()`, je pro jádro validním cílem. To usnadňuje vytváření "Mock" objektů pro testy.

```python
class Downloadable(Protocol):
    uuid: str
    title: str
    async def download(self, format: AudioFormat, progress_cb: Optional[ProgressCB]) -> None:
        ...
```

### 2. Pattern: Content Resolver Registry
Aktuální `if is_show / elif is_series` v `main.py` je špatně udržovatelné. Lepší je registr:
- Každý typ obsahu (`Show`, `Series`, `Episode`) má svůj `Resolver`.
- Registr projde všechny resolvery a vybere ten, který URL odpovídá.
- Výsledkem je instance `Downloadable`.

### 3. Funkcionální ošetření chyb (Result Type)
Místo `try/except` bloků rozesetých po celém kódu může jádro vracet typ `Result[Data, Error]`. GUI pak může snadno reagovat na chybu zobrazením dialogu, aniž by padala celá aplikace.

### 4. Neměnné datové modely (Value Objects)
Všechny modely v `crodl/data/` by měly být `frozen=True`.
- Zajišťuje, že se data během životního cyklu objektu (např. během dlouhého stahování) omylem nezmění.
- Usnadňuje debugging a práci v multithreaded/async prostředí.

---

## Persistence a ukládání metadat (Databáze)

Aby bylo možné se staženými díly dále pracovat (např. ve webovém rozhraní nebo mobilní aplikaci), je nutné ukládat metadata z API do trvalého úložiště.

### 1. Metadata k uložení
U každého staženého "AudioWork" (epizody) budeme evidovat:
- `uuid`: Unikátní identifikátor z Rozhlasu (Primary Key).
- `title`: Název díla.
- `author` / `artist`: Autor nebo účinkující.
- `description`: Textový popis/obsah.
- `broadcast_at`: Datum a čas původního vysílání (`since`).
- `local_path`: Absolutní cesta k souboru na disku.
- `metadata`: JSON pole pro dodatečné info (bitrate, formát, tagy).

### 2. Návrh Tech-stacku

Navrhujeme dvě cesty v závislosti na budoucím využití:

#### Varianta A: Django (Robustní, prověřená cesta)
*Vhodné, pokud plánuješ plnohodnotnou webovou aplikaci s administrací.*
- **Pro:** Django ORM je extrémně výkonné, obsahuje migraci databáze a "zadarmo" získáš Admin rozhraní.
- **Proti:** Django je "těžké" pro malý CLI nástroj.
- **Implementace:** Použít Django v "standalone" módu pro CLI a později na stejnou DB namířit webový server.

#### Varianta B: SQLModel + FastAPI (Moderní, asynchronní cesta)
*Vhodné pro lehké jádro a moderní asynchronní GUI/Web API.*
- **Pro:** Kombinuje SQLAlchemy (výkonné ORM) a Pydantic (validace dat). Je nativně asynchronní, což sedí k našemu návrhu jádra.
- **Proti:** Vyžaduje manuální nastavení migrací (Alembic).
- **Implementace:** Ideální pro integraci s GUI v PySide/PyQt nebo lehkým webovým API.

### 3. Integrace přes Repository Pattern
Jádro nebude přímo volat SQL. Vytvoříme rozhraní:
```python
class MetadataRepository(Protocol):
    async def save_download(self, work: AudioWork, path: Path) -> None: ...
    async def get_all_downloads(self) -> List[AudioWork]: ...
```

---

## Plán implementace (v krocích)

1.  **Fáze 1: Core Clean-up & Hierarchy**
    - Sjednotit `AudioWork` s `Content`.
    - Odstranit `print()` z metod tříd a nahradit je logováním/návratovými hodnotami.
    - Vyčistit `__init__` metody od síťové logiky.

2.  **Fáze 2: Modelování dat & API Klient**
    - Implementovat robustní modely v `crodl/data/`.
    - Vytvořit `CroAPIClient` pro veškerou komunikaci se servery Rozhlasu.

3.  **Fáze 3: Abstraktní stahování**
    - Refaktorovat `crodl/streams/` tak, aby vracely stream dat nebo periodicky volaly progress callback.

4.  **Fáze 4: Rozhraní (CLI / GUI)**
    - Upravit `main.py` jako "tenkého klienta" nad novým jádrem.
    - (Volitelně) Připravit prototyp jednoduchého GUI pro ověření nezávislosti jádra.
