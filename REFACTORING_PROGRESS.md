# Log refaktoringu cro-dl (Duben 2026)

## 🏁 Celkový přehled
Projekt prošel transformací z procedurálního/synchronního přístupu na moderní asynchronní architekturu založenou na principech Clean Code a OOP.

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

## 📅 24. dubna 2026 (odpoledne): Service Layer / Fasáda (Bod 3)
**Cíl:** Oddělit logiku aplikace od CLI rozhraní a vyčistit typování.

### Provedené změny:
*   **Fasáda `CroDL`:** Vytvořena třída `crodl.facade.CroDL` jako jediný vstupní bod do logiky.
*   **Refaktoring `main.py`:** CLI je nyní pouze tenká slupka nad fasádou.
*   **Typová hygiena:** Opraveno 20+ chyb v typování (Pyright) a vyčištěn lint (Ruff).
*   **Exporty:** Sjednocen přístup k balíčku přes `from crodl import CroDL`.

---

## ⚡ Budoucí kroky
1.  **Persistence (Bod 4):** Implementace `SQLModel` (SQLite) pro ukládání historie stahování a metadat. (Vybráno jako moderní async alternativa k Djangu).

---
*Všechny dosavadní kroky byly úspěšně ověřeny reálným stahováním a 100% pokrytím testy.* 🚀
