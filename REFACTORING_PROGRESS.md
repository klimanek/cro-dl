# Log refaktoringu cro-dl (3. dubna 2026)

## 🎯 Cíl a výchozí stav
Projekt byl v přechodné fázi mezi procedurálním a objektovým přístupem. Hlavním cílem bylo:
*   Sjednotit hierarchii entit (`AudioWork`, `Series`, `Show`) pod bázovou třídu `Content`.
*   Odstranit síťová volání z konstruktorů (`__init__`).
*   Vytvořit dedikovaného API klienta a odstranit závislost na globálním `cro_session`.

## 🚧 Problémy a jejich řešení

### 1. Cloudflare a "403 Forbidden"
*   **Problém:** Při pokusu o spuštění CLI s reálnou URL nás Cloudflare odstřihl s chybou 403.
*   **Řešení:** Integrovali jsme tvou "obezličku" – knihovnu `cloudscraper`, která nahradila standardní `requests.Session`. Teď `CroAPIClient` automaticky řeší Cloudflare challenge.

### 2. Rozbité testy po pročištění kódu
*   **Problém:** Odstraněním starých funkcí (jako `get_attributes` přímo z `audiowork.py`) jsme rozbili přes 15 testů, které tyto funkce patchovaly.
*   **Řešení:** Refaktorovali jsme i testy. Místo patchování funkcí v modulech nyní testy podstrkují `Mock` verzi `CroAPIClient` přímo entitám. Architektura je teď mnohem lépe testovatelná (Dependency Injection).

### 3. Konzistence dat
*   **Problém:** Každá entita si tahala data trochu jinak a v jiném formátu.
*   **Řešení:** Všechny entity byly převedeny na `dataclasses` a data z API se nyní sjednoceně zpracovávají v `CroAPIClient`.

## 🏆 Co je výsledkem?
*   **Sjednocená architektura:** Vše jede přes `CroAPIClient` a bázovou třídu `Content`.
*   **Čistý kód:** Žádné `print()` ani síťová volání hluboko v logice. Vše je explicitní.
*   **Funkční CLI:** Reálné URL z mujrozhlas.cz se nyní stahují bez problémů.
*   **100% testy:** Všech 107 testů svítí zeleně.

## ⚡ Budoucí "bolesti" (Co nás čeká příště)
1.  **Sjednocení stahovačů (Downloader Abstraction):** Převést `AudioParts` na skutečnou abstraktní bázovou třídu (ABC) s definovaným rozhraním (metoda `download()`). Sjednotit inicializaci a zpracování chyb napříč `DASH`, `HLS` a `MP3`.
2.  **Plná asynchronizace:** Stahování MP3 a některé části parsování jsou stále synchronní. Pro budoucí GUI to bude chtít kompletní `async/await` cestu.
3.  **Lazy Loading:** Metadata by se měla načítat, až když jsou skutečně potřeba (např. popis pořadu).
4.  **Persistence:** Bude potřeba vybrat a implementovat databázi (SQLModel / Django) pro ukládání historie stahování.
5.  **Změny na straně Rozhlasu:** Cloudflare nebo struktura webu se může kdykoliv změnit, což bude vyžadovat údržbu škrabky v `CroAPIClient`.

---
*Hotovo pro dnešek. Dobrá práce!* 🎸
