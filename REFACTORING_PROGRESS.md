# Log refaktoringu cro-dl (24. dubna 2026)

## 🎯 Cíl: Paralelní stahování a sjednocené UI (Bod 2 - dokončení)
Zajistit, aby seriály a pořady stahovaly více epizod naráz pro maximální efektivitu, při zachování přehledného UI v terminálu.

## 🚧 Provedené změny

### 1. Paralelní orchestrace v `Series` a `Show`
*   Zaveden `asyncio.gather` se semaforem (limit 3) pro stahování epizod.
*   Výrazné zrychlení stahování u vícedílných děl.

### 2. Sjednocené UI pro progres barů
*   Refaktorováno rozhraní `AudioParts.download`, které nyní přijímá volitelný objekt `Progress`.
*   Stahovače (`MP3`, `HLS`, `DASH`) nyní umí reportovat svůj stav do sdíleného `rich.progress` kontextu.
*   Vyřešen `LiveError` – nyní může v rámci jednoho seriálu běžet libovolný počet progress barů pod sebou.

### 3. Izolace temporary dat
*   `segments_path` je nyní unikátní pro každou epizodu (formát `.chunks-<audio_title>`).
*   Tím se předešlo "race conditions" při paralelním volání `ffmpeg` a přepisování `list.txt`.

## 🏆 Výsledek a ověření
*   **Verifikace:** Úspěšně otestováno paralelní stažení 5dílného seriálu o Josefu Čapkovi. 3 díly se stahovaly naráz, UI korektně zobrazovalo postupy všech běžících úloh.
*   **Stabilita:** Všech 107 testů je zelených.

## ⚡ Co nás čeká příště
1.  **Service Layer (Fasáda `CroDL`):** Vytvoření čistého API pro budoucí GUI a vyčištění `main.py` (Bod 3).
2.  **Persistence:** Implementace `SQLModel` pro ukládání historie a metadat (Bod 4).

---
*Hotovo. Seriály teď lítají jako blesk!* ⚡⚡⚡

