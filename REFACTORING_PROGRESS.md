# Log refaktoringu cro-dl (Duben 2026)

## 🏁 Celkový přehled
Projekt prošel transformací z procedurálního/synchronního přístupu na moderní asynchronní architekturu založenou na principech Clean Code a OOP. Je plně připraven pro webovou nadstavbu a lokální správu audio knihovny.

---

## 📅 23. dubna 2026: Abstrakce stahovačů (Bod 1)
**Cíl:** Sjednotit logiku stahování a převést ji do asynchronního režimu.

### Provedené změny:
*   **`AudioParts` -> ABC:** Vytvořena abstraktní bázová třída vynucující asynchronní rozhraní `.download()`.
*   **MP3 Downloader:** Kompletně přepsán na `async` pomocí `aiohttp`. Vyřešeny timeouty u velkých souborů.
*   **HLS & DASH Downloadery:** Sjednoceny s bázovou třídou, využívají asynchronní stahování segmentů.
*   **Testy:** Aktualizováno všech 107 testů pro podporu asynchronity a nových signatur.

---

## 📅 24. dubna 2026 (dopoledne): Paralelní stahování (Bod 2)
**Cíl:** Zrychlit stahování seriálů a sjednotit vizuální progres.

### Provedené změny:
*   **Paralelismus:** Zaveden `asyncio.gather` se semaforem (limit 3) v `Series` a `Show`.
*   **Sjednocené UI:** Refaktoring stahovačů pro podporu sdíleného `rich.progress` objektu. Vyřešen `LiveError`.
*   **Izolace dat:** Každá epizoda má nyní unikátní temporary složku pro kousky, čímž se eliminovaly kolize při paralelním volání `ffmpeg`.

---

## 📅 24. dubna 2026 (odpoledne): Service Layer a Persistence (Bod 3 & 4)
**Cíl:** Oddělit logiku aplikace od CLI, vyčistit typování a zavést ukládání metadat do databáze.

### Provedené změny:
*   **Fasáda `CroDL`:** Vytvořena třída `crodl.facade.CroDL` jako jediný vstupní bod do logiky.
*   **Persistence (SQLModel):** Implementována asynchronní SQLite databáze (`library.db`).
    *   Schéma obsahuje tabulky pro Epizody, Pořady, Seriály a Stanice.
    *   Automatické ukládání bohatých metadat z API po každém úspěšném stažení.
    *   Vyřešeny "race conditions" při paralelním zápisu do DB pomocí asynchronních zámků.
*   **Thumbnails:** Implementován automatický stahovač obrázků, které se ukládají k audio souborům pro budoucí webovou knihovnu.
*   **Typová hygiena:** Opraveno všech 20+ chyb v typování (Pyright) a vyčištěn lint (Ruff).

---

## 📅 25. dubna 2026: Webová knihovna (Bod 5)
**Cíl:** Vytvořit grafické rozhraní pro prohlížení a přehrávání staženého obsahu přímo v prohlížeči.

### Provedené změny:
*   **FastAPI Server:** Vytvořen balíček `crodl/server/` s asynchronním API.
*   **Webový Frontend:** Vytvořena moderní HTML5 šablona s Dark Mode designem a integrovaným přehrávačem.
*   **Statické soubory:** Server automaticky mapuje lokální složku `Z Rozhlasu` na URL `/library`, což umožňuje přehrávání přímo z disku.
*   **Integrace:** Přidán příkaz `uv run cro-dl-server` pro snadné spuštění.

---

## 🏆 Aktuální stav
Projekt je nyní robustní, asynchronní a datově orientovaný. Má jasně oddělené vrstvy a funkční webové rozhraní.

---
*Všechny cíle byly úspěšně splněny. cro-dl je nyní kompletní ekosystém pro audio archiv.* 🚀✨
