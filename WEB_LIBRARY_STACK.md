# Webová knihovna — technologický stack

Doplněk k `WEB_LIBRARY_DESIGN.md`: vysvětluje, které knihovny webová část používá, **co v našem kódu
každá skutečně dělá** a proč je v závislostech i `greenlet`.

---

## Jak to do sebe zapadá

```
prohlížeč
   │ HTTP
   ▼
uvicorn            ← ASGI server: event loop + HTTP, spouští appku
   │ ASGI
   ▼
FastAPI            ← routy, dependency injection, Jinja2 šablony, JSON API
   │ volá
   ▼
SqliteLibraryRepository (crodl/library/repository.py)
   │
   ▼
SQLModel           ← modely (crodl/library/models.py)
   │ staví na
   ▼
SQLAlchemy (async) ← engine, session, dotazy; interně greenlet
   │ přes ovladač
   ▼
aiosqlite          ← asynchronní přístup k SQLite
   │
   ▼
~/Z Rozhlasu/library.db
```

Vedle toho jde **datový tok při stahování** (bez HTTP serveru):

```
cro-dl <url> → CroDL.download() → on_downloaded hook → LibraryService
             → artwork (image_downloader) + SqliteLibraryRepository.save_download() → DB
```

Díky tomu, že obě cesty končí ve stejném repozitáři, vidí web v knihovně i to, co stáhne CLI
(a naopak: `cro-dl --sync` naimportuje soubory, které na disku ležely před zavedením DB).

---

## SQLAlchemy — databázové jádro

Co u nás dělá (`crodl/library/database.py`, `repository.py`):

- **Async engine:** `create_async_engine(DATABASE_URL)` — připojení k `sqlite+aiosqlite:///…/library.db`.
  Vytváří se jednou při importu modulu a jen se připojuje, takže je levné ho držet.
- **Session:** `async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)`; každá operace
  si otevře vlastní `AsyncSession` (`async with self._session_factory() as session`) a po sobě zavře.
- **Dotazy:** `select(Episode).where(...).order_by(col(Episode.broadcast_at).desc())`,
  `await session.execute(...)`, `result.scalars().all()`, `await session.get(Episode, uuid)`.
- **Upsert:** `await session.merge(row)` = „vlož nebo přepiš podle primárního klíče". Proto stačí
  jedno `save_download()` a opakované stažení/sken nevyrábí duplicity.
- **Sloupec JSON:** `Column(JSON)` pro `Episode.meta` (dodatečná data bez vlastního schématu).
- **Transakce:** `await session.commit()`.

Proč to nebylo potřeba řešit ručně: SQLAlchemy je jediné místo, kde se v projektu mluví SQL; jádro
i CLI jdou přes repozitář (`LibraryRepository` / užší `DownloadStore`), takže „jádro nezná databázi".

---

## SQLModel — modely nad SQLAlchemy + Pydantic

Co přidává (`crodl/library/models.py`):

- **Deklarativní model:** `class Episode(SQLModel, table=True)` — Python třída, ze které se stane
  tabulka, a zároveň dataclass s `__init__`, `repr` a `==`.
- **Mapování polí na sloupce:** `Field(primary_key=True)`, `Field(default=None, foreign_key="show.uuid")`,
  `Optional[str]`, `Relationship(back_populates="episodes")` (vztahy `Station`/`Show`/`Series` ↔ `Episode`).
- **Validace a serializace přes Pydantic:** proto může server vrátit model rovnou jako odpověď
  (`response_model=Episode`) nebo si vyrobit slovník do šablony (`ep.model_dump()`), aniž bychom psali
  převodní kód.
- **Výchozí hodnoty:** `Field(default_factory=datetime.now)`, `Field(default_factory=dict)`.

Proč SQLModel a ne „čistý" SQLAlchemy: schéma se čte jako typované třídy, tabulky a vztahy vznikají
z anotací a stejné objekty se používají pro validaci i pro serializaci do JSON. Cena za to je pár
kompromisů, na které v kódu narazíte:

- `metadata` **nelze** použít jako jméno sloupce (rezervuje si ho SQLAlchemy) → máme `meta`.
- Na úrovni třídy je pole typované jako hodnota (`Episode.broadcast_at` je `datetime`), ne jako sloupec,
  takže pro `ORDER BY` se používá `sqlmodel.col(Episode.broadcast_at).desc()`.

---

## aiosqlite a pydantic — podpůrné vrstvy

- **aiosqlite** je asynchronní ovladač SQLite; SQLAlchemy ho použije podle schématu URL
  (`sqlite+aiosqlite://`). Díky němu dotazy neblokují event loop, na kterém běží i stahování.
- **pydantic** validuje a serializuje data (SQLModel je postavený na něm). V projektu se používá
  nepřímo přes modely — explicitně bychom ho potřebovali, až bychom validovali vstup z formulářů.

---

## greenlet — proč je v závislostech (a není to naše volba)

`greenlet` **nepoužíváme v našem kódu ani jednou**. Je to závislost **SQLAlchemy**, a to dvojím
způsobem (doloženo v metadatech balíčku, `.venv/.../sqlalchemy-*.dist-info/METADATA`):

- `Requires-Dist: greenlet>=1; platform_machine == "aarch64" or … or "win32"` → na běžných
  architekturách (ARM64, x86_64, Windows) ho SQLAlchemy tahá **vždy**;
- `Requires-Dist: greenlet>=1; extra == "asyncio"` → navíc pro `sqlalchemy[asyncio]`.

Souvisí to s tím, že SQLAlchemy si pro asynchronní režim potřebuje „přepínat kontext" mezi svým
synchronním jádrem a `await` voláním ovladače — a to dělá právě greenletem (jeho `_concurrency_py3k.py`
a `ext/asyncio/session.py` ho importují).

**Odpovědi na tvé otázky:**

- *Bude se nám někde hodit?* Ne přímo. Naše souběžnost je `asyncio` + `aiohttp` (stahování) a asynchronní
  ovladač pro DB; greenlet je pouze vnitřek SQLAlchemy. Nepoužíváme ho ani nebudeme volat.
- *Není to pozůstatek rozhodování mezi asyncio a greenletem?* **Není.** Původně šlo o rozhodnutí
  SQLite vs. Django vs. SQLModel (`REFACTORING.md`), přičemž byl vybrán SQLModel. `greenlet` se objevil
  jako **tranzitivní požadavek** SQLAlchemy pro async režim, a je v `pyproject.toml` vypsaný i explicitně.
- *Přinesl by výhody?* Pro nás ne: greenlet umí levné přepínání korutin bez vláken, ale my žádné
  blokující volání „přemostit" nepotřebujeme — náš kód je nativně asynchronní od začátku. Přínos by měl
  jen tam, kde se míchá synchronní knihovna do async světa (což je přesně případ SQLAlchemy).

**Co s ním:** nechat být (a klidně s komentářem v `pyproject.toml`, že jde o požadavek SQLAlchemy).
Odebrat ho z `dependencies` by nic neušetřilo — SQLAlchemy si ho stáhne sám. Verzové rozmezí dává
smysl držet volné, ať si ho SQLAlchemy řídí.

---

## uvicorn — server, který to obsluhuje

Co dělá (`crodl/server/run.py`):

```python
uvicorn.run(
    "crodl.server.app:app",
    host=SERVER_HOST,
    port=SERVER_PORT,
    reload=True,
)
```

- **ASGI server:** vezme aplikaci (`crodl.server.app:app` — instance `FastAPI`), postaví kolem ní
  HTTP server a **event loop**. FastAPI samo o sobě nic neposlouchá, jen definuje aplikaci.
- **`SERVER_HOST` / `SERVER_PORT`** (`crodl/settings.py`): server je dostupný **jen z tohoto
  počítače**. To je záměr — knihovna je osobní (autorská práva) a nemá se vystavovat na LAN/WAN.
  Stejné hodnoty používá i CORS politika v `server/app.py`, aby se adresa nerozešla na dvou místech.
- **`reload=True`:** pro vývoj (při změně souboru se appka restartuje); v „produkci" na vlastním
  stroji klidně vypnout — ušetří to sledování souborů.

Před spuštěním serveru je potřeba mít tabulky (`init_db()`), což `run.py` dělá sám. Jak spustit:

```
uv run python -m crodl.server.run      # → http://127.0.0.1:8000
```

Nebo z nainstalovaného balíčku:

```
python -m crodl.server.run
```

## FastAPI a Jinja2 — co dělá aplikační vrstva

- **FastAPI:** routy (`@app.get("/")`, `@app.get("/detail/{ctype}/{id}")`), závislosti
  (`Depends(get_repo)` → čerstvý repozitář) a JSON API pod `/api` (`/api/episodes`, `/api/library-stats`).
  FastAPI z `response_model=Episode` vyrobí dokumentaci i serializaci.
- **Jinja2:** HTML šablony (`server/templates/index.html`, `detail.html`) — server-rendered stránky
  bez JS buildu; do budoucna se nad stejným JSON API dá postavit SPA.
- **Statické soubory:** stažená média jdou přes routu `/library/{path}` (`server/app.py`), která pustí
  jen soubory, jež knihovna zná (`LibraryService.media_file()` → allowlist z DB), a odpovídá
  `FileResponse` s podporou Range (přehrávač tak umí posouvat).

---

## Zbývá dořešit (návaznost na `WEB_LIBRARY_DESIGN.md` §4, fáze D)

Fáze D je **hotová**:

- ✅ Agregace kolekcí je v `LibraryService.overview()` / `detail()`; route handlery jen vykreslují.
- ✅ `StaticFiles` je pryč: média servíruje `/library/{path}` s allowlistem cest z DB (a `..`/absolutní
  cesty odmítá), takže `library.db`, logy ani segmentové složky nejsou přes HTTP dostupné.
- ✅ CORS je omezené na `127.0.0.1`/`localhost` na portu serveru, metody jen `GET`.
- ✅ `greenlet` má komentář v `pyproject.toml` (viz výše).
- ✅ Server se binduje jen na `127.0.0.1` (`SERVER_HOST`/`SERVER_PORT` v `settings.py`).

Zbývá **fáze E** (`WEB_LIBRARY_DESIGN.md` §4): dlouhé úlohy s progressem (polling/SSE) a UI pro
ruční metadata místo dnešního `crodl/library/manual_import.py`.
